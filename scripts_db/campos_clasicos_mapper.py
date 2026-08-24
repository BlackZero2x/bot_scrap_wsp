"""
Arma los ~35 campos clásicos de pbi2.dbo.fija_data_toa (los que ya existían
antes de las 137 columnas nuevas) a partir del JSON de actividad obtenido
por toa_client.py — equivalente al trabajo que hace
scrapper.py::BotTOA.scrapping_information() leyendo el DOM, pero por HTTP.

Usa mapeo_campos_clasicos.json (raíz del proyecto) para los campos con
equivalencia confirmada. Los campos sin equivalencia confiable en el JSON
de sync (persona_contacto_cierre, observacion_datos_cita_legados,
observacion_datos_cita_toa, intervalo_tiempo, respuesta_whatsapp_botmaker,
hora_envio_mensaje_whatsapp, hora_respuesta_mensaje_whatsapp,
direccion_incorrecta, codigos_cancelado, codigo_no_realizado_tecnicos,
tipo_devolucion_instalaciones, motivo_no_realizado_instalacion,
descripcion_general, fecha_ult_tratamiento) quedan en None — no se inventan
valores. numero_telefono usa la key 570 ("Teléfono de Contacto"), candidato
razonable pero no confirmado con el mismo rigor que el resto.
"""
import json
from datetime import datetime
from pathlib import Path

_RUTA_MAPEO = Path(__file__).parent.parent / "mapeo_campos_clasicos.json"

_mapeo = None


def _cargar_mapeo():
    global _mapeo
    if _mapeo is None:
        with open(_RUTA_MAPEO, encoding="utf-8") as f:
            _mapeo = json.load(f)
    return _mapeo


ESTADO_LABEL = {
    "complete": "Completado",
    "cancelled": "Cancelado",
    "notdone": "No Realizada",
    "pending": "Pendiente",
    "suspended": "Suspendido",
    "started": "Iniciado",
}

# Campo adicional no confirmado con el mismo rigor (candidato único, sin
# verificación cruzada) — se documenta aparte para que sea fácil de revisar.
_CAMPOS_ADICIONALES = {
    "numero_telefono": "570",
}


def _normalizar_work_order(appt_number: str, fe_buscado: str) -> str:
    """
    Replica la lógica de "auto-reparación" de scrapper.py::start_bot()
    (líneas 425-434): si el work_order devuelto por TOA no coincide con el
    FE buscado pero tiene el prefijo "INS-", se limpia ese prefijo. Si aun
    así no coincide, se conserva el FE buscado (es la clave real de
    negocio, más confiable que un valor inesperado del JSON).
    """
    if not fe_buscado or appt_number == fe_buscado:
        return appt_number
    if appt_number and appt_number.startswith("INS-"):
        limpio = appt_number.removeprefix("INS-")
        if limpio == fe_buscado:
            return limpio
    return fe_buscado


def mapear_campos_clasicos(activity_json: dict, dni_vendedor: str = None, fe_buscado: str = None) -> dict:
    """
    Devuelve un dict con los nombres de columna clásicos de fija_data_toa
    (work_order, nombre_cliente, estado_general, fuente, etc.), tomando los
    valores del JSON de actividad cuando hay equivalencia confirmada.

    fe_buscado: código FE que se usó para buscar esta actividad — si se
    provee, se usa para normalizar work_order ante el prefijo "INS-" que a
    veces trae TOA (ver _normalizar_work_order).
    """
    mapeo = _cargar_mapeo()
    resultado = {}

    for columna, key_json in mapeo.items():
        if key_json and key_json in activity_json:
            valor = activity_json[key_json]
            resultado[columna] = valor if valor not in (None, "") else None
        else:
            resultado[columna] = None

    for columna, key_json in _CAMPOS_ADICIONALES.items():
        valor = activity_json.get(key_json)
        resultado[columna] = valor if valor not in (None, "") else None

    # Campos calculados, no vienen de mapeo_campos_clasicos.json
    appt_number = activity_json.get("appt_number")
    resultado["work_order"] = _normalizar_work_order(appt_number, fe_buscado)
    astatus = activity_json.get("astatus")
    resultado["estado_general"] = ESTADO_LABEL.get(astatus, astatus)
    resultado["fuente"] = "TOA"
    # Formato DD/MM/YYYY, igual que scrapper.py::scrapping_information() —
    # la sesión SQL Server de esta instancia espera DATETIME en formato DMY;
    # un ISO YYYY-MM-DD produce "valor fuera de intervalo" (pyodbc 22007).
    resultado["fecha_actualizacion"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    resultado["dni_vendedor"] = str(dni_vendedor) if dni_vendedor else None

    return resultado
