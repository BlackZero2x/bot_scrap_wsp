"""
Script de investigación (uso manual, no forma parte del pipeline productivo).

Usa Playwright (no Selenium) para hacer login en TOA y buscar unos FEs de
prueba, capturando la REQUEST completa (no solo la respuesta) hacia el
endpoint interno de sincronización (?m=sync&a=write): método HTTP, headers,
cookies y body de la petición.

Objetivo: determinar si esa llamada se puede reproducir con un cliente HTTP
puro (requests/httpx) fuera del navegador — es decir, si el patrón híbrido
completo (login con navegador + HTTP directo por cada FE) es viable, o si
depende de un token/estado interno de la SPA que solo el navegador conoce.

Uso:
    python scripts_db/investigar_request_sync.py FE-1128820197 FE-1129056718 FE-1128653298

Salida:
    diagnostico_request_sync.json — lista de requests capturadas hacia el
    endpoint de sync, con método, headers, cookies y body.
"""
import json
import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from config import TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD

SALIDA = Path(__file__).parent.parent / "diagnostico_request_sync.json"


def login(page, username, password):
    page.goto("https://telefonica-pe.etadirect.com/")

    page.wait_for_selector("#username", timeout=30000)
    page.click("#username")
    page.fill("#username", username)

    page.click("#password")
    page.fill("#password", password)

    page.click("xpath=/html/body/div/div/div/div/form/div[2]/div[5]/button/div")

    # Manejo de "eliminar otras sesiones", igual que scrapper.py::login()
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
        print("No hay otras sesiones; continuando...")

    page.wait_for_selector("input[placeholder='Buscar en actividades']", timeout=60000)
    time.sleep(6)
    print("Login OK — buscador de actividades visible.")


def campo_busqueda_visible(page):
    candidatos = page.query_selector_all("input[aria-label='Buscar en actividades']")
    for c in candidatos:
        if c.is_visible():
            return c
    candidatos = page.query_selector_all("input[placeholder='Buscar en actividades']")
    for c in candidatos:
        if c.is_visible():
            return c
    raise Exception("No se encontró un campo de búsqueda visible")


def buscar_fe(page, fe):
    campo = campo_busqueda_visible(page)
    campo.click()
    campo.press("Control+A")
    campo.press("Backspace")

    for char in fe:
        campo.type(char, delay=random.uniform(30, 90))
    time.sleep(random.uniform(3.5, 6))

    try:
        resultado = page.wait_for_selector(
            "xpath=//div[@aria-label='activity result item']", timeout=20000
        )
        resultado.click()
        time.sleep(random.uniform(3, 5))
        return True
    except Exception:
        return False


def main():
    fes = sys.argv[1:] or ["FE-1128820197", "FE-1129056718", "FE-1128653298"]

    capturas = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        todas_las_requests = []

        def on_request(request):
            try:
                body = request.post_data
            except Exception:
                body = None
            entrada = {
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": body,
                "resource_type": request.resource_type,
            }
            todas_las_requests.append(entrada)
            if "m=sync" in request.url and "a=write" in request.url:
                capturas.append(entrada)
                print(f"  Capturada request sync: {request.method} {request.url[:80]}...")

        page.on("request", on_request)

        respuestas_search = []

        def on_response(response):
            if "m=search" in response.url and "a=search" in response.url:
                try:
                    body_text = response.text()
                except Exception:
                    body_text = None
                respuestas_search.append({
                    "url": response.url,
                    "status": response.status,
                    "body": body_text,
                })
                print(f"  Capturada RESPUESTA de search: status={response.status}")

        page.on("response", on_response)

        try:
            print("Login en TOA (Playwright)...")
            login(page, TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD)

            for fe in fes:
                marca_inicio = len(todas_las_requests)
                print(f"\nBuscando {fe}... (request index inicial: {marca_inicio})")
                encontrado = buscar_fe(page, fe)
                marca_fin = len(todas_las_requests)
                print(f"  {'encontrado' if encontrado else 'NO encontrado'} (requests {marca_inicio}-{marca_fin})")
                if fe != fes[-1]:
                    time.sleep(random.uniform(8, 15))

            # Capturar también las cookies de la sesión (para probar réplica HTTP)
            cookies = context.cookies()

        finally:
            browser.close()

    salida = {
        "capturas_sync": capturas,
        "todas_las_requests": todas_las_requests,
        "respuestas_search": respuestas_search,
        "cookies_sesion": cookies,
        "user_agent": None,
    }

    SALIDA.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(capturas)} requests hacia sync capturadas.")
    print(f"{len(cookies)} cookies de sesión capturadas.")
    print(f"Guardado en: {SALIDA}")

    if capturas:
        print("\n=== Primera request capturada (resumen) ===")
        c = capturas[0]
        print(f"Método: {c['method']}")
        print(f"URL: {c['url']}")
        print(f"Headers: {json.dumps(c['headers'], indent=2)}")
        print(f"Body: {c['post_data'][:500] if c['post_data'] else '(sin body)'}")


if __name__ == "__main__":
    main()
