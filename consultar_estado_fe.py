"""
Cascada de resolución de "/estado FE-..." para el bot de WhatsApp (Yugi
Backoffice). Implementa el diseño de arquitectura acordado (sesión
2026-08-19/20): VENTORY Postgres es el gate de acceso, eAuren resuelve
Cerrado/Cancelado directo (con D-1 de lag), y pbi2.fija_data_toa resuelve
Pendiente/Enviado y el motivo de cancelación.

El paso 3 (pbi2.fija_data_toa) lee de un CACHÉ LOCAL (cache_toa.py,
SQLite) en vez de consultar SQL Server en vivo — pbi2 (usuario adminpbi2)
tiene fallos intermitentes de conexión (SQL Server 18456) confirmados en
producción (2026-08-20/21) que, sin este caché, se transmitían directo al
vendedor cada vez que su consulta coincidía con una ventana de
degradación. refrescar_cache_toa.py mantiene el caché al día cada
5-10 min, en un proceso separado del camino de respuesta.

Este módulo es una cascada de solo LECTURA — no tiene conocimiento de TOA
ni de HTTP. El paso 3b (búsqueda puntual cuando el FE nunca fue buscado en
TOA) vive enteramente en wa_toa_listener.js: cuando consultar_estado_fe()
devuelve MSG_SIN_RASTRO_TOA, el listener hace un POST a
toa_servicio_busqueda.py --http (puerto 8004) — ese servicio SÍ escribe
directo a pbi2 (guarda el resultado de la búsqueda real en TOA), y
refrescar_cache_toa.py lo recoge en su siguiente corrida periódica.

Uso:
    python consultar_estado_fe.py FE-1128653298
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SATimeoutError

from config import engine_auren, engine_ventory_pg
from cache_toa import cache_desactualizado, obtener_fila_cache

# Solo estos tipos representan fallos transitorios de conexión/red que
# tiene sentido reintentar (timeouts, login fallido intermitente como el
# 18456 de SQL Server, pool agotado). Cualquier otra excepción (SQL mal
# formado, columna renombrada, TypeError de parámetros) es un bug de
# código real y debe propagarse de inmediato — reintentarla 15 veces solo
# retrasa la respuesta ~45s antes de fallar igual, y esconde el bug real
# detrás de un mensaje de "FE no encontrado en TOA".
ERRORES_TRANSITORIOS = (OperationalError, DBAPIError, SATimeoutError, ConnectionError, TimeoutError)

PATRON_FE = re.compile(r"^FE-\d+$", re.IGNORECASE)

MSG_NO_EN_VENTORY = "La FE no está registada en VENTORY, porfa registralo, espera unos minutos y vuelve a intentarlo"
MSG_SIN_RASTRO_TOA = "FE aun no pasa a TOA"

# Objetivo del proyecto (2026-08-22, palabras del usuario): "lo mas
# importante es darle información correcta confiable y la mas actualizada
# al vendedor, no importa tanto responder en 1 o 2 segundos mas que eso".
# Consecuencia directa: el vendedor NUNCA debe ver un mensaje que delate una
# dificultad técnica (timeout, conexión caída, servicio caído) — eso genera
# desconfianza hacia Yugi. Un fallo de conexión real (tras agotar
# reintentos) se trata igual que "el dato aún no está disponible": se
# responde MSG_SIN_RASTRO_TOA, nunca un mensaje de error explícito.
#
# Reintentos: backoff EXPONENCIAL, no intervalo fijo. El diseño anterior
# (15 intentos x 3s para pbi2) generaba hasta 15 logins seguidos contra
# adminpbi2 por cada llamada — el DBA confirmó (2026-08-20) que es plausible
# que esa ráfaga de logins fuera la causa (o agravante) de la propia
# degradación que se intentaba sobrevivir, no solo una reacción a ella
# (muchas políticas de SQL Server bloquean temporalmente una cuenta tras
# varios intentos fallidos seguidos). Con backoff exponencial, MAX_REINTENTOS
# reintentos consumen 2^MAX_REINTENTOS - 1 segundos de espera antes del
# último intento — con 6 reintentos son 63s, dentro del presupuesto de ~60s
# que el vendedor ya tolera para la búsqueda puntual en TOA (paso 3b).
MAX_REINTENTOS = 6
ESPERA_BASE_SEG = 1.0  # backoff: 1s, 2s, 4s, 8s, 16s, 32s


class ErrorConsultaFE(Exception):
    """
    Fallo de conexión real (no de datos) tras agotar los reintentos. Se
    distingue de "no encontrado" a nivel de código/logs, pero de cara al
    vendedor el llamador la trata igual que un dato aún no disponible
    (MSG_SIN_RASTRO_TOA) — nunca se expone un mensaje de error técnico.
    """


def _con_reintento(fn, *args, reintentos=MAX_REINTENTOS, **kwargs):
    """
    Ejecuta fn(*args, **kwargs) con hasta `reintentos` intentos y backoff
    EXPONENCIAL (1s, 2s, 4s, 8s...) entre cada uno — no un intervalo fijo.
    Un fallo de conexión real (SQL Server 18456 intermitente) se reintenta
    con pocos intentos espaciados en vez de muchos intentos en ráfaga, para
    no presionar el login mientras está degradado (ver nota arriba).

    Solo reintenta ERRORES_TRANSITORIOS — un error de programación (SQL mal
    formado, TypeError de parámetros) se propaga de inmediato en vez de
    agotar los reintentos disfrazado de "fallo de conexión".
    """
    ultimo_error = None
    for intento in range(1, reintentos + 1):
        try:
            return fn(*args, **kwargs)
        except ERRORES_TRANSITORIOS as e:
            ultimo_error = e
            if intento < reintentos:
                time.sleep(ESPERA_BASE_SEG * (2 ** (intento - 1)))
    raise ErrorConsultaFE(str(ultimo_error)) from ultimo_error


def _validar_formato_fe(fe: str) -> bool:
    return bool(PATRON_FE.match(fe.strip()))


def _paso1_ventory(fe: str):
    """
    Gate de acceso: existe en VENTORY (Postgres, ventas_db.ventas), filtrando
    por mes actual + mes anterior. Devuelve la petición (codigo_seguridad_2,
    puente confirmado hacia eAuren.peticion) o None si no existe.

    Levanta ErrorConsultaFE (tras reintentos agotados) si la conexión falla
    — no hay "último dato conocido" razonable para un gate de acceso, así
    que un fallo de conexión real se propaga en vez de reportarse como
    "no está en VENTORY" (sería engañoso: sí puede estar, no se pudo verificar).
    """
    query = """
        SELECT codigo_seguridad_2 AS peticion
        FROM ventas
        WHERE codigo_seguridad = %(fe)s
          AND fecha_registro >= (date_trunc('month', now()) - interval '1 month')
        ORDER BY fecha_registro DESC
        LIMIT 1
    """
    df = _con_reintento(pd.read_sql, query, engine_ventory_pg(), params={"fe": fe})
    if df.empty:
        return None
    return df.iloc[0]["peticion"]


def _paso2_eauren(peticion: str):
    """
    eAuren (D-1): fija_registros_totales LEFT JOIN fija_altas por peticion.
    Devuelve un dict con el estado resuelto, o None si no está (aún no
    replicado por el lag D-1, o nunca llegó a este par de tablas) o si el
    estado es Enviado (no definitivo, se resuelve en el paso 3).

    Levanta ErrorConsultaFE tras reintentos agotados — mismo criterio que
    _paso1_ventory: sin dato previo confiable que ofrecer en este paso.
    """
    query = """
        SELECT
            rt.desc_estado_peticion AS estado_registro,
            fa.desc_estado_peticion AS estado_alta,
            fa.fecha_alta,
            fa.fechacambioestado
        FROM dbo.fija_registros_totales rt
        LEFT JOIN dbo.fija_altas fa ON rt.peticion = fa.peticion
        WHERE rt.peticion = ?
    """
    df = _con_reintento(pd.read_sql, query, engine_auren(), params=(peticion,))
    if df.empty:
        return None

    fila = df.iloc[0]
    estado_alta = fila["estado_alta"]
    estado_registro = fila["estado_registro"]

    if estado_alta == "Cerrado" or estado_registro == "Cerrado":
        fecha = fila["fecha_alta"] if pd.notna(fila["fecha_alta"]) else fila["fechacambioestado"]
        return {"estado": "Cerrado", "fecha": fecha}

    if estado_registro == "Cancelado":
        # eAuren no tiene campo de motivo — se resuelve en pbi2.fija_data_toa (paso 3)
        return {"estado": "Cancelado"}

    # Enviado, o cualquier otro estado no definitivo: se resuelve con TOA
    return None


def _paso3_toa_con_estado(work_order: str):
    """
    Lee del CACHÉ LOCAL (cache_toa.py, SQLite) — no toca pbi2 en vivo.
    Devuelve (fila_o_None, cache_desactualizado_flag).

    cache_desactualizado_flag es True solo si el proceso de refresco
    periódico (refrescar_cache_toa.py) lleva más de 20 min sin correr —
    señal de que ALGO está mal con el refresco en sí (tarea programada
    caída, pbi2 inalcanzable por horas), no de que este FE puntual tenga
    un dato viejo. Se sigue devolviendo la fila cacheada de todos modos
    (mejor un dato quizá desactualizado que ningún dato), pero el
    llamador puede optar por avisar según el caso (ver _armar_mensaje_cancelado).
    """
    fila = obtener_fila_cache(work_order)
    desactualizado = cache_desactualizado()
    return fila, desactualizado


def _paso3_toa(work_order: str):
    """Atajo sobre _paso3_toa_con_estado() para llamadores que no
    necesitan saber si el caché está desactualizado."""
    fila, _desactualizado = _paso3_toa_con_estado(work_order)
    return fila


def _formatear_fecha(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    # pbi2.fija_data_toa guarda algunas fechas como NVARCHAR (ISO YYYY-MM-DD)
    # en vez de DATETIME — parsear antes de mostrar en formato DD/MM/YYYY.
    parsed = pd.to_datetime(str(valor), errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%d/%m/%Y")
    return str(valor)


def _armar_mensaje_cerrado(fecha) -> str:
    return f"Instalada el {_formatear_fecha(fecha)}"


def _armar_mensaje_cancelado(motivo: str | None) -> str:
    motivo = motivo or "sin especificar"
    return f"Cancelado, Motivo: {motivo}"


def _armar_mensaje_iniciada(fecha_agenda, franja_agenda, intervalo_tiempo) -> str:
    """
    fecha_agendamiento + franja_agendamiento (AM/PM) + intervalo_tiempo
    (rango horario, ej. "09-13") — el máximo detalle real disponible en
    pbi2.fija_data_toa. No hay hora puntual exacta (ej. "11:42 AM"): ese
    campo (ETA en el JSON crudo de TOA) nunca se mapeó a ninguna columna.

    fila_toa viene del caché local (sqlite3.Row) — valores nativos Python
    (str o None), nunca pandas.NaN, así que basta un chequeo simple de
    truthiness sin pd.isna().
    """
    if not fecha_agenda:
        return "Iniciada, sin agenda"

    partes = [_formatear_fecha(fecha_agenda)]
    if franja_agenda:
        partes.append(str(franja_agenda))
    if intervalo_tiempo:
        partes.append(f"({intervalo_tiempo}h)")
    return f"Iniciada, Agenda {' '.join(partes)}"


def consultar_estado_fe(fe: str) -> str:
    """
    Ejecuta la cascada de LECTURA (VENTORY -> eAuren -> pbi2.fija_data_toa) y
    devuelve el mensaje final para el vendedor. Nunca lanza excepciones hacia
    el llamador ni expone un mensaje de error técnico — un fallo de conexión
    real (tras agotar reintentos en cada paso) se traduce en
    MSG_SIN_RASTRO_TOA, el mismo mensaje que "el dato aún no está
    disponible" (ver nota de objetivo del proyecto junto a MAX_REINTENTOS).

    Si el resultado es MSG_SIN_RASTRO_TOA (el FE nunca fue buscado en TOA),
    el llamador (wa_toa_listener.js) es quien decide disparar el paso 3b —
    POST a toa_servicio_busqueda.py --http (puerto 8004) — y, si encuentra
    algo, volver a llamar a esta función para releer el dato ya guardado.
    Este módulo se mantiene deliberadamente sin conocimiento de TOA/HTTP:
    solo lee lo que ya existe en las 3 fuentes.
    """
    fe = fe.strip().upper()
    if not _validar_formato_fe(fe):
        return MSG_NO_EN_VENTORY

    try:
        peticion = _paso1_ventory(fe)
    except ErrorConsultaFE:
        # Fallo de conexión real tras agotar reintentos — nunca se expone al
        # vendedor, se trata como dato aún no disponible (ver nota arriba).
        return MSG_SIN_RASTRO_TOA
    if peticion is None:
        return MSG_NO_EN_VENTORY

    try:
        resultado_eauren = _paso2_eauren(str(peticion))
    except ErrorConsultaFE:
        return MSG_SIN_RASTRO_TOA
    if resultado_eauren is not None:
        if resultado_eauren["estado"] == "Cerrado":
            return _armar_mensaje_cerrado(resultado_eauren["fecha"])
        # Cancelado: eAuren confirma el estado, pero el motivo viene del
        # caché local de TOA (lectura SQLite, no toca pbi2 en vivo — ver
        # cache_toa.py). Si nunca se cacheó nada para este FE, se responde
        # sin motivo en vez de fallar: eAuren ya confirmó que SÍ está
        # cancelado, solo falta el detalle del motivo.
        fila_toa = _paso3_toa(fe)
        motivo = fila_toa["motivo_no_realizado_instalacion"] if fila_toa is not None else None
        return _armar_mensaje_cancelado(motivo)

    # Enviado / no encontrado en eAuren (lag D-1): resolver con pbi2.fija_data_toa
    fila_toa = _paso3_toa(fe)
    if fila_toa is None:
        return MSG_SIN_RASTRO_TOA

    estado_general = fila_toa["estado_general"]
    if estado_general in ("Completado", "Cerrado"):
        return _armar_mensaje_cerrado(fila_toa["fecha_actualizacion"])
    if estado_general in ("Cancelado", "No Realizada"):
        return _armar_mensaje_cancelado(fila_toa["motivo_no_realizado_instalacion"])

    # Iniciado / Pendiente / Enviado / Suspendido: aun no instalada
    return _armar_mensaje_iniciada(
        fila_toa["fecha_agendamiento"], fila_toa["franja_agendamiento"], fila_toa["intervalo_tiempo"]
    )


def main():
    if len(sys.argv) < 2:
        print("Uso: python consultar_estado_fe.py FE-XXXXXXXXXX")
        sys.exit(1)
    fe = sys.argv[1]
    print(consultar_estado_fe(fe))


if __name__ == "__main__":
    main()
