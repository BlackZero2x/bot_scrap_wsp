from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from sqlalchemy import text
import os
from telegram.request import HTTPXRequest
from datetime import datetime, timedelta
from config import engine_auren, engine_toa, engine_tg_usuarios, TELEGRAM_TOKEN

for var in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'NO_PROXY', 'no_proxy']:
    os.environ.pop(var, None)

MESSAGES = {
    "bienvenida": "🔐 *Acceso restringido*\nPara realizar consultas, primero inicia sesión usando /start.",
    "menu": "🤖 Ya puedes acceder a las consultas. Utiliza el comando /menu o el atajo rápido para iniciar!",
}

request = HTTPXRequest(proxy=None)

# Estados del flujo de conversación
DNI, CLAVE, NUEVA_CLAVE, CONFIRMAR_CLAVE = range(4)
MENU_PRINCIPAL, CODIGO_FE, CODIGO_OMS, CODIGO_FE_LISTA = range(4, 8)

engine_net = engine_auren()
engine_usuarios = engine_tg_usuarios()
engine_fe = engine_toa()

sesiones_activas = {}


# ============================================================================
# Helpers
# ============================================================================

def _esta_autenticado(chat_id: int) -> bool:
    return sesiones_activas.get(chat_id, {}).get("logged_in", False)

def _obtener_nombre_usuario(dni: str) -> str:
    with engine_usuarios.connect() as conn:
        row = conn.execute(
            text("SELECT nombre FROM fija_usuario_telegram WHERE usuario = :dni"),
            {"dni": dni}
        ).fetchone()
    return row.nombre if row else "Usuario"


# ============================================================================
# Autenticación
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    context.user_data.clear()
    sesiones_activas.pop(chat_id, None)
    await update.message.reply_text("👤 Por favor, ingresa tu DNI:")
    return DNI


async def recibir_dni(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["dni"] = update.message.text.strip()
    await update.message.reply_text("🔑 Ahora ingresa tu contraseña:")
    return CLAVE


async def recibir_clave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    dni = context.user_data["dni"]
    clave = update.message.text.strip()
    chat_id = update.effective_chat.id

    with engine_usuarios.connect() as conn:
        row = conn.execute(
            text("SELECT cambio_contrasena FROM fija_usuario_telegram WHERE usuario = :dni AND contrasena = :clave"),
            {"dni": dni, "clave": clave}
        ).fetchone()

    if not row:
        await update.message.reply_text("❌ DNI o contraseña incorrecta. Intenta nuevamente con /start")
        return ConversationHandler.END

    if row.cambio_contrasena == "1":
        sesiones_activas[chat_id] = {"dni": dni, "logged_in": True}
        context.user_data["logged_in"] = True
        nombre = _obtener_nombre_usuario(dni)
        await update.message.reply_text(f"✅ Bienvenido al sistema, {nombre}.")
        await update.message.reply_text(MESSAGES["menu"])
        return ConversationHandler.END

    await update.message.reply_text("🛠 Debes cambiar tu contraseña. Ingresa una nueva:")
    return NUEVA_CLAVE


async def recibir_nueva_clave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["nueva_clave"] = update.message.text.strip()
    await update.message.reply_text("🔁 Confirma tu nueva contraseña:")
    return CONFIRMAR_CLAVE


async def confirmar_clave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    confirmacion = update.message.text.strip()
    nueva_clave = context.user_data["nueva_clave"]
    chat_id = update.effective_chat.id

    if confirmacion != nueva_clave:
        await update.message.reply_text("❌ Las contraseñas no coinciden. Intenta nuevamente con /start")
        return ConversationHandler.END

    dni = context.user_data["dni"]
    with engine_usuarios.begin() as conn:
        conn.execute(
            text("UPDATE fija_usuario_telegram SET contrasena = :clave, cambio_contrasena = 1 WHERE usuario = :dni"),
            {"clave": nueva_clave, "dni": dni}
        )

    sesiones_activas[chat_id] = {"dni": dni, "logged_in": True}
    context.user_data["logged_in"] = True
    await update.message.reply_text("✅ Contraseña actualizada. ¡Bienvenido!")
    await update.message.reply_text(MESSAGES["menu"])
    return ConversationHandler.END


# ============================================================================
# Menú principal
# ============================================================================

async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id

    if not _esta_autenticado(chat_id):
        await update.message.reply_text(MESSAGES["bienvenida"], parse_mode="Markdown")
        return ConversationHandler.END

    keyboard = [
        ["Consultar FE 🔎"],
        ["Consultar lista FE 🧾"],
        ["Consultar OMS 🔍"],
        ["Cerrar sesión 🏃‍♂️"],
    ]
    await update.message.reply_text(
        "Selecciona una opción del menú:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return MENU_PRINCIPAL


async def comando_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await mostrar_menu(update, context)


async def cerrar_sesion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sesiones_activas.pop(update.effective_chat.id, None)
    context.user_data.clear()
    await update.message.reply_text("🚪 Sesión cerrada. Usa /start para iniciar sesión nuevamente.")
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END


# ============================================================================
# Consulta FE individual
# ============================================================================

async def consultar_fe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _esta_autenticado(update.effective_chat.id):
        await update.message.reply_text(MESSAGES["bienvenida"], parse_mode="Markdown")
        return ConversationHandler.END

    await update.message.reply_text("🤖 Por favor ingresa el código FE:")
    await update.message.reply_text("⚠ Solo ingresa dígitos. Ejemplo: 1083152147")
    return CODIGO_FE


def _buscar_fe_en_bd(codigo_fe: str, dni: str):
    """
    Retorna la fila de fija_data_toa si existe y pertenece al vendedor,
    o una cadena de error: 'no-autorizado', 'no-procesado', 'error'.
    """
    with engine_fe.connect() as conn:
        row = conn.execute(
            text("""
                SELECT estado_general, dni_vendedor, motivo_no_realizado_instalacion,
                       fecha_agendamiento, franja_agendamiento
                FROM dbo.fija_data_toa
                WHERE work_order = :codigo_fe
                ORDER BY fecha_actualizacion DESC
            """),
            {"codigo_fe": codigo_fe}
        ).fetchone()

    if row:
        return row if row.dni_vendedor == dni else "no-autorizado"

    # No está en fija_data_toa — verificar en controlnet
    with engine_net.connect() as conn:
        row_net = conn.execute(
            text("SELECT codigo_fe, dni_vendedor FROM dbo.fija_controlnet_detallado WHERE codigo_fe = :codigo_fe"),
            {"codigo_fe": codigo_fe}
        ).fetchone()

    if not row_net:
        return "error"
    return "no-procesado" if row_net.dni_vendedor == dni else "no-autorizado"


async def recibir_codigo_fe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    codigo_fe = update.message.text.strip()

    if not codigo_fe.isdigit() or len(codigo_fe) < 10:
        await update.message.reply_text("❌ El código ingresado no es válido. Intenta nuevamente.")
        return await mostrar_menu(update, context)

    await update.message.reply_text("⚙️ Consultando datos para el Código FE...")

    codigo_fe_completo = f"FE-{codigo_fe}"
    dni = context.user_data.get("dni")
    resultado = _buscar_fe_en_bd(codigo_fe_completo, dni)

    if isinstance(resultado, str):
        # Casos de error
        if resultado == "no-autorizado":
            await update.message.reply_text("🚷 Este FE no está registrado con tu DNI. Solo puedes consultar tus propias ventas.")
        elif resultado == "no-procesado":
            hora_disponible = (datetime.now() + timedelta(hours=4)).strftime("%H:%M")
            await update.message.reply_text(f"😌 FE en proceso. Intenta nuevamente a partir de las {hora_disponible}.")
        elif resultado == "error":
            await update.message.reply_text("❗ La FE no está registrada en el controlnet. Registra tu venta para consultar el estado.")
    else:
        estado = resultado.estado_general
        if estado == "Completado":
            with engine_fe.connect() as conn:
                row = conn.execute(
                    text("SELECT FECHA_ALTA FROM dbo.T_COMERCIAL WHERE CMS_CODSRV = :codigo_fe"),
                    {"codigo_fe": codigo_fe_completo}
                ).fetchone()
            fecha = row[0] if row else "fecha no disponible"
            await update.message.reply_text(f"✅ Instalada - {fecha}")

        elif estado == "Pendiente":
            await update.message.reply_text(f"⌛ Estado: {estado}")

        elif estado == "Cancelado":
            with engine_fe.connect() as conn:
                row = conn.execute(
                    text("SELECT MOTIVO_CANCELACION2 FROM dbo.T_CONVERTIBILIDAD WHERE CODREQ = :codigo_fe"),
                    {"codigo_fe": codigo_fe_completo}
                ).fetchone()
            motivo = row[0] if row else "Posible LCF"
            await update.message.reply_text(f"❌ Cancelado - {motivo}")

        elif estado == "No Realizada":
            await update.message.reply_text(f"😢 Cancelada - {resultado.motivo_no_realizado_instalacion}")

        elif estado == "Suspendido":
            await update.message.reply_text(f"⚠ Estado: {estado}")

        elif estado == "Iniciado":
            await update.message.reply_text("🦾 Estado: EN ATENCIÓN")

    return await mostrar_menu(update, context)


# ============================================================================
# Consulta lista de FEs
# ============================================================================

async def consultar_lista_fe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _esta_autenticado(update.effective_chat.id):
        await update.message.reply_text(MESSAGES["bienvenida"], parse_mode="Markdown")
        return ConversationHandler.END

    dni = context.user_data.get("dni")
    if not dni:
        await update.message.reply_text("No se encontró tu DNI en la sesión. Inicia sesión nuevamente.")
        return ConversationHandler.END

    await update.message.reply_text("Buscando tus órdenes de trabajo, por favor espera...")

    resultados = _buscar_lista_fe(dni)
    await _mostrar_resultados_fe(update, resultados)
    return await mostrar_menu(update, context)


def _buscar_lista_fe(dni: str):
    with engine_fe.connect() as conn:
        return conn.execute(
            text("""
                WITH UltimoRegistro AS (
                    SELECT
                        work_order,
                        estado_general,
                        fecha_actualizacion,
                        ROW_NUMBER() OVER (PARTITION BY work_order ORDER BY fecha_actualizacion DESC) AS row_num
                    FROM dbo.fija_data_toa
                    WHERE dni_vendedor = :dni
                )
                SELECT work_order, estado_general, fecha_actualizacion
                FROM UltimoRegistro
                WHERE row_num = 1
                ORDER BY fecha_actualizacion DESC
            """),
            {"dni": dni}
        ).fetchall()


async def _mostrar_resultados_fe(update: Update, resultados) -> None:
    if not resultados:
        await update.message.reply_text("No se encontraron órdenes de trabajo asociadas a tu DNI.")
        return

    ESTADO_LABELS = {"Completado": "Instalada", "No Realizada": "Cancelada"}
    lineas = []
    for row in resultados:
        estado = ESTADO_LABELS.get(row[1], row[1])
        lineas.append(f"📌 {row[0]} - {estado}")

    await update.message.reply_text(
        "📋 *Tus órdenes de trabajo:*\n\n" + "\n".join(lineas),
        parse_mode="Markdown"
    )


# ============================================================================
# Consulta OMS
# ============================================================================

async def consultar_oms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _esta_autenticado(update.effective_chat.id):
        await update.message.reply_text(MESSAGES["bienvenida"], parse_mode="Markdown")
        return ConversationHandler.END

    await update.message.reply_text("✍️ Por favor, ingresa el Código OMS que quieres consultar:")
    await update.message.reply_text("⚠ Solo ingresa dígitos. Ejemplo: 1083152147")
    return CODIGO_OMS


async def recibir_codigo_oms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    codigo_oms = update.message.text.strip()

    if not codigo_oms.isdigit() or len(codigo_oms) < 10:
        await update.message.reply_text("❌ El código ingresado no es válido. Intenta nuevamente.")
        return await mostrar_menu(update, context)

    await update.message.reply_text("⚙️ Consultando datos para el Código OMS...")

    codigo_oms_completo = f"OMS-{codigo_oms}"
    with engine_fe.connect() as conn:
        row = conn.execute(
            text("SELECT estado_general FROM dbo.fija_data_toa WHERE work_order = :codigo_oms"),
            {"codigo_oms": codigo_oms_completo}
        ).fetchone()

    resultado = row[0] if row else "El documento solicitado no ha sido procesado"
    await update.message.reply_text(f"✅ Resultado para Código OMS: {resultado}")
    return await mostrar_menu(update, context)


# ============================================================================
# Configuración del bot
# ============================================================================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

conv_handler_auth = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        DNI: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_dni)],
        CLAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_clave)],
        NUEVA_CLAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nueva_clave)],
        CONFIRMAR_CLAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_clave)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar)],
    name="auth_conversation",
)

conv_handler_menu = ConversationHandler(
    entry_points=[
        CommandHandler("menu", comando_menu),
        CommandHandler("consulta", comando_menu),
        # Catch-all de texto libre — restaurado (ver historial de este
        # archivo): sin esto, un usuario sin conversación activa, o que
        # volvió a MENU_PRINCIPAL tras cualquier consulta (cuyo estado solo
        # lista 4 botones con Regex exacto), no tiene ningún handler que le
        # responda si escribe texto plano en vez de tocar un botón.
        MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: mostrar_menu(update, context)),
    ],
    states={
        MENU_PRINCIPAL: [
            MessageHandler(filters.Regex("^Consultar FE 🔎$"), consultar_fe),
            MessageHandler(filters.Regex("^Consultar lista FE 🧾$"), consultar_lista_fe),
            MessageHandler(filters.Regex("^Consultar OMS 🔍$"), consultar_oms),
            MessageHandler(filters.Regex("^Cerrar sesión 🏃‍♂️$"), cerrar_sesion),
        ],
        CODIGO_FE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_codigo_fe)],
        CODIGO_OMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_codigo_oms)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar)],
    name="menu_conversation",
)

app.add_handler(conv_handler_auth)
app.add_handler(conv_handler_menu)

print("🤖 Bot en ejecución...")
app.run_polling()
