"""
Cliente híbrido para TOA (Oracle Field Service): login con Playwright (una
sola vez por sesión) + llamadas HTTP directas (requests) para buscar FEs y
extraer su detalle, sin necesitar navegador para cada búsqueda.

Reemplaza la estrategia de scrapper.py::BotTOA, que abría el DOM y leía cada
uno de los ~35 campos con selectores CSS/XPath por cada FE. En su lugar:

1. Login con Playwright, capturando de una request real hacia el endpoint
   de sync los parámetros de sesión que la SPA reutiliza sin cambios durante
   toda la sesión (cookies, trust, x-ofs-csrf-secure, dv, u).
2. Por cada FE: POST a /index.php?m=search&a=search (HTTP puro) para
   resolver el código FE al ID interno de actividad (aid) + fecha.
3. Con ese aid: POST a /?m=sync&a=write (HTTP puro) con requestedAid +
   requestedDate, que devuelve el detalle completo de la actividad en
   delta.Activity y delta.FormData — igual que hoy captura
   scripts_db/diagnostico_red_toa.py vía logs de red de Selenium, pero sin
   necesitar navegador abierto en este paso.

Investigación que sustenta este diseño (sesión de trabajo previa, ver
diagnostico_request_sync.json): los tokens `trust` y `x-ofs-csrf-secure` no
rotan por request — se generan una vez al iniciar sesión y se reutilizan
igual en todas las llamadas subsiguientes. El endpoint de búsqueda no lleva
la telemetría de comportamiento que sí trae `sync` en sus otras llamadas.
"""
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD

TOA_BASE_URL = "https://telefonica-pe.etadirect.com"
TOA_LOGIN_URL = f"{TOA_BASE_URL}/"

# El entorno tiene un proxy corporativo que exige autenticación (407) y no
# está whitelisteado para telefonica-pe.etadirect.com. Limpiar las
# variables de entorno NO alcanza: requests además consulta la
# configuración de proxy del sistema operativo (WinINET, vía
# urllib.request.getproxies()) — netsh winhttp la reporta "sin proxy" pero
# es una fuente distinta que persiste aunque se borren HTTP_PROXY/
# HTTPS_PROXY del proceso. Se limpian las env vars por prolijidad, pero el
# fix real es trust_env=False en la sesión (ver _crear_sesion_http()).
for _var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_var, None)


def _crear_sesion_http() -> requests.Session:
    """
    trust_env=False evita que requests consulte proxies de entorno O del
    sistema operativo (WinINET) — necesario porque TOA no está whitelisteado
    en el proxy corporativo y devuelve 407 Proxy Authentication Required.
    """
    s = requests.Session()
    s.trust_env = False
    return s

_DEBUG = False

# Mismo dominio sin proxy que ya usa scrapper.py (líneas 29-44) — el entorno
# tiene un proxy corporativo que hay que ignorar explícitamente para TOA.
NO_PROXY_DOMAINS = ["telefonica-pe.etadirect.com", "chromedriver.storage.googleapis.com"]

# Campos donde buscar el texto ingresado (nombre -> incluido en la búsqueda).
# Valores tal cual los envía la SPA real (ver diagnostico_request_sync.json,
# request índice 215) — "1994" va en false, el resto en true.
SEARCH_FIELDS = {
    "137": "true", "309": "true", "341": "true", "368": "true",
    "1053": "true", "1088": "true", "1204": "true", "1847": "true",
    "1994": "false", "2570": "true",
    "appt_number": "true", "customer_number": "true", "cname": "true",
    "cphone": "true", "ccell": "true", "caddress": "true",
}


@dataclass
class SesionTOA:
    """Parámetros de sesión capturados tras el login, reutilizables en cada
    llamada HTTP posterior sin volver a abrir navegador."""
    cookies: dict
    trust: str
    csrf: str
    dv: str
    usuario: str
    pid: str = "0"
    session: requests.Session = field(default_factory=_crear_sesion_http)

    def headers_base(self):
        return {
            "x-platform": "1",
            "x-ofs-csrf-secure": self.csrf,
            "x-requested-with": "XMLHttpRequest",
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/x-www-form-urlencoded",
            "referer": TOA_LOGIN_URL,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
            ),
        }


def _extraer_parametros_sesion(request_body: str, headers: dict) -> dict:
    """Extrae trust, dv y u del body de una request de sync ya capturada."""
    def _campo(nombre, body):
        m = re.search(rf"(?:^|[&;\n]|name=\"{nombre}\"\r?\n\r?\n)([^\r\n&]*)", body)
        return m

    parametros = {}
    # Body puede venir como x-www-form-urlencoded o multipart; parseamos ambos casos.
    if "Content-Disposition" in request_body:
        partes = re.split(r"------\S+\r?\n", request_body)
        for parte in partes:
            m = re.match(r'Content-Disposition: form-data; name="([^"]+)"\r?\n\r?\n(.*)', parte, re.DOTALL)
            if m:
                nombre, valor = m.group(1), m.group(2).strip()
                parametros[nombre] = valor
    else:
        for par in request_body.split("&"):
            if "=" in par:
                k, v = par.split("=", 1)
                parametros[k] = v

    return {
        "trust": parametros.get("trust", ""),
        "dv": parametros.get("dv", ""),
        "u": parametros.get("u", ""),
        "pid": parametros.get("pid", "0"),
        "csrf": headers.get("x-ofs-csrf-secure", ""),
    }


def login_y_obtener_sesion(username: str = None, password: str = None, max_intentos: int = 3) -> SesionTOA:
    """
    Hace login en TOA con Playwright y devuelve una SesionTOA con los
    parámetros necesarios para llamar a search/sync por HTTP puro de ahí
    en adelante. El navegador se cierra al terminar — no queda abierto.
    """
    username = username or TOA_PORTAL_USERNAME
    password = password or TOA_PORTAL_PASSWORD

    for intento in range(1, max_intentos + 1):
        try:
            return _intentar_login(username, password)
        except Exception as e:
            print(f"  Falló el login (intento {intento}/{max_intentos}): {e}")
            if intento == max_intentos:
                raise
            time.sleep(10)


def _intentar_login(username: str, password: str) -> SesionTOA:
    capturado = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        posts_vistos = []

        def on_request(request):
            if request.url.startswith(TOA_BASE_URL) and request.method == "POST":
                headers = dict(request.headers)
                csrf_val = headers.get("x-ofs-csrf-secure")
                if _DEBUG:
                    posts_vistos.append((request.url[:70], csrf_val))
                if "csrf" in capturado:
                    return
                if csrf_val:
                    body = request.post_data or ""
                    extraido = _extraer_parametros_sesion(body, headers)
                    if _DEBUG:
                        print(f"  [debug login] POST con csrf: {request.url[:70]} -> trust={'SI' if extraido['trust'] else 'NO'} dv={'SI' if extraido['dv'] else 'NO'} u={'SI' if extraido['u'] else 'NO'}")
                    # Solo aceptar si logramos extraer también trust/dv/u —
                    # algunas requests POST no llevan esos parámetros.
                    if extraido["trust"] and extraido["dv"] and extraido["u"]:
                        capturado.update(extraido)

        page.on("request", on_request)

        try:
            page.goto(TOA_LOGIN_URL)
            page.wait_for_selector("#username", timeout=30000)
            page.click("#username")
            page.fill("#username", username)
            page.click("#password")
            page.fill("#password", password)
            page.click("xpath=/html/body/div/div/div/div/form/div[2]/div[5]/button/div")

            try:
                btn_delete = page.wait_for_selector(
                    "xpath=/html/body/div/div/div/div/form/div[2]/div[4]/div[1]/div[1]/span/span/input",
                    timeout=8000,
                )
                btn_delete.click()
                page.click("#password")
                page.fill("#password", password)
                page.click("xpath=/html/body/div/div/div/div/form/div[2]/div[6]/button/div")
            except Exception:
                pass  # no había otras sesiones activas

            page.wait_for_selector("input[placeholder='Buscar en actividades']", timeout=60000)

            # El token csrf/trust real aparece recién en requests posteriores a
            # la carga inicial (no en las primeras llamadas de sync tras el
            # login, que a veces van con csrf vacío) — dar margen a que la SPA
            # termine de cargar recursos en background y dispare esas llamadas.
            # Se usa page.wait_for_timeout (ligado al loop de eventos de
            # Playwright) en vez de time.sleep para no perder eventos de red
            # que lleguen justo al borde del último chequeo.
            espera = 0
            while "csrf" not in capturado and espera < 40:
                page.wait_for_timeout(1000)
                espera += 1

            # Última red de seguridad: dar un respiro final por si la request
            # decisiva quedó en vuelo justo cuando se cumplió el límite.
            if "csrf" not in capturado:
                page.wait_for_timeout(3000)

            if "csrf" not in capturado:
                if _DEBUG:
                    print(f"  [debug login] Total POSTs vistos: {len(posts_vistos)}")
                    for url, csrf_val in posts_vistos:
                        print(f"    {url} csrf={'(vacio)' if not csrf_val else csrf_val[:20]}")
                raise RuntimeError("No se pudo capturar el token de sesión (csrf/trust) tras el login")

            cookies = {c["name"]: c["value"] for c in context.cookies()}

        finally:
            browser.close()

    return SesionTOA(
        cookies=cookies,
        trust=capturado["trust"],
        csrf=capturado["csrf"],
        dv=capturado["dv"],
        usuario=capturado["u"],
        pid=capturado.get("pid", "0"),
    )


def buscar_fe(sesion: SesionTOA, fe: str) -> Optional[dict]:
    """
    Resuelve un código FE al registro de búsqueda de OFSC (con aid, pid,
    date, astatus) vía POST a /index.php?m=search&a=search. Devuelve None
    si no se encuentra.
    """
    url = f"{TOA_BASE_URL}/index.php?m=search&a=search"

    payload = {
        "from": "",
        "size": "60",
        "searchValue": fe,
        "searchDate": "at_all",
        "skip_delta": "0",
        "__protocol": "7",
        "dv": sesion.dv,
        "pid": sesion.pid,
        "u": sesion.usuario,
        "f": "json",
        "pids": "[]",
        "aids": "[]",
        "restriction": "0",
        "fakeIds": "{}",
        "trust": sesion.trust,
        "fakeIdsClean": "0",
        "limitActivitiesByPool[notscheduled]": "5",
    }
    for campo, valor in SEARCH_FIELDS.items():
        payload[f"searchFields[{campo}]"] = valor

    resp = sesion.session.post(
        url, data=payload, headers=sesion.headers_base(), cookies=sesion.cookies, timeout=30
    )
    if _DEBUG:
        print(f"  [debug] status={resp.status_code} len={len(resp.text)} body={resp.text!r}")
    resp.raise_for_status()
    resultados = resp.json()

    for entrada in resultados:
        if isinstance(entrada, dict) and entrada.get("key") == "appt_number":
            rows = entrada.get("value", {}).get("rows", [])
            if rows:
                return rows[0]

    if _DEBUG:
        print(f"  [debug] búsqueda sin resultados para {fe!r}. Respuesta parseada: {json.dumps(resultados)[:800]}")
    return None


def obtener_detalle_actividad(sesion: SesionTOA, aid: int, fecha: str, pid: int) -> Optional[dict]:
    """
    Con el aid, fecha y pid (provider id del recurso, devuelto por
    buscar_fe()) ya resueltos, pide el detalle completo de la actividad vía
    POST a /?m=sync&a=write. Devuelve el dict de delta.Activity[aid] tal
    cual, o None si no aparece en la respuesta.

    Importante: el "pid" que espera este endpoint es el del recurso/técnico
    dueño de la actividad (viene en la fila de resultados de buscar_fe()),
    NO el pid genérico "0" de la sesión recién logueada — usar el de sesión
    aquí hace que el servidor devuelva delta.Activity vacío.
    """
    url = f"{TOA_BASE_URL}/?m=sync&a=write&ajax=1"

    payload = {
        "__protocol": "7",
        "dv": sesion.dv,
        "pid": str(pid),
        "u": sesion.usuario,
        "f": "json",
        "pids": "[]",
        "aids": "[]",
        "restriction": "0",
        "qid": "undefined",
        "fakeIds": "{}",
        "trust": sesion.trust,
        "fakeIdsClean": "0",
        "dq": fecha,
        "date": fecha,
        "dispatcher": "1",
        "requestedAid": str(aid),
        "requestedDate": fecha,
        "skip_delta": "0",
    }

    resp = sesion.session.post(
        url, data=payload, headers=sesion.headers_base(), cookies=sesion.cookies, timeout=30
    )
    if _DEBUG:
        print(f"  [debug sync] status={resp.status_code} len={len(resp.text)} aid_buscado={aid} fecha={fecha}")
        print(f"  [debug sync] body={resp.text[:1500]!r}")
    resp.raise_for_status()
    resultado = resp.json()

    actividades = resultado.get("delta", {}).get("Activity", {})
    # delta.Activity puede venir como dict {aid_str: {...}} o como lista de
    # actividades, según el estado del delta (full sync vs incremental).
    if isinstance(actividades, dict):
        iterable = actividades.values()
    else:
        iterable = actividades

    for act in iterable:
        if isinstance(act, dict) and act.get("aid") == aid:
            return act

    if _DEBUG:
        print(f"  [debug sync] no se encontró aid={aid} en delta.Activity. Tipo de actividades: {type(actividades)}, cantidad: {len(actividades) if hasattr(actividades, '__len__') else 'N/A'}")
    return None


def buscar_y_extraer_fe(sesion: SesionTOA, fe: str) -> Optional[dict]:
    """Combina buscar_fe() + obtener_detalle_actividad() en un solo paso."""
    resultado_busqueda = buscar_fe(sesion, fe)
    if not resultado_busqueda:
        return None
    aid = resultado_busqueda["aid"]
    fecha = resultado_busqueda["date"]
    pid = resultado_busqueda["pid"]
    return obtener_detalle_actividad(sesion, aid, fecha, pid)


if __name__ == "__main__":
    fes = sys.argv[1:] or ["FE-1128653298"]
    print("Iniciando sesión (login con Playwright)...")
    sesion = login_y_obtener_sesion()
    print("Sesión obtenida. Procesando FEs por HTTP puro...")

    for fe in fes:
        print(f"\n{fe}...")
        act = buscar_y_extraer_fe(sesion, fe)
        if act:
            print(f"  OK — estado: {act.get('astatus')}, campos: {len(act)}")
        else:
            print("  no encontrado")
        time.sleep(random.uniform(1, 3))
