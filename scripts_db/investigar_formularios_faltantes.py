"""
Script de investigación (uso manual, no forma parte del pipeline productivo).

Abre FEs en distintos estados (completado, cancelado/no realizado) con
Playwright para que la SPA descargue los formularios JS asociados a esas
pantallas, descarga cada URL de formulario detectada, y extrae los pares
campo->título con el mismo patrón usado en la investigación original
(new I("NOMBRE_TECNICO","KEY_JSON",N) ... "t":"Titulo" ... "g":"grupo").

Objetivo: ampliar mapeo_campos_clasicos.json con los campos que aún faltan
(persona_contacto_cierre, direccion_incorrecta, codigos_cancelado,
codigo_no_realizado_tecnicos, tipo_devolucion_instalaciones,
motivo_no_realizado_instalacion, observacion_datos_cita_legados,
observacion_datos_cita_toa, descripcion_general, intervalo_tiempo).

Uso:
    python scripts_db/investigar_formularios_faltantes.py FE-completado FE-cancelado ...
"""
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from config import TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD

DIR_SALIDA = Path(__file__).parent.parent
RUTA_FORMULARIOS = DIR_SALIDA / "formularios_descargados"


def login(page, username, password):
    page.goto("https://telefonica-pe.etadirect.com/")
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
        pass

    page.wait_for_selector("input[placeholder='Buscar en actividades']", timeout=60000)
    page.wait_for_timeout(4000)
    print("Login OK.")


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


def buscar_y_abrir_fe(page, fe):
    campo = campo_busqueda_visible(page)
    campo.click()
    campo.press("Control+A")
    campo.press("Backspace")
    for char in fe:
        campo.type(char, delay=random.uniform(30, 90))
    page.wait_for_timeout(int(random.uniform(3500, 6000)))

    try:
        resultado = page.wait_for_selector(
            "xpath=//div[@aria-label='activity result item']", timeout=20000
        )
        resultado.click()
        page.wait_for_timeout(int(random.uniform(4000, 6000)))
        return True
    except Exception:
        return False


def main():
    fes = sys.argv[1:]
    if not fes:
        print("Uso: python scripts_db/investigar_formularios_faltantes.py FE-1 FE-2 ...")
        sys.exit(1)

    RUTA_FORMULARIOS.mkdir(exist_ok=True)
    urls_formularios_vistas = set()
    archivos_descargados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disk-cache-size=1"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            bypass_csp=True,
        )
        context.route("**/*.js", lambda route: route.continue_())  # forzar que pasen por la red, no caché
        page = context.new_page()

        def on_response(response):
            url = response.url
            if "/form/" in url and url.endswith(".js") and url not in urls_formularios_vistas:
                urls_formularios_vistas.add(url)
                try:
                    body = response.text()
                except Exception:
                    return
                # nombre de archivo derivado del label en la query string, si existe
                m = re.search(r"[?&]label=([^&]+)", url)
                nombre = m.group(1) if m else url.split("/")[-1].replace(".js", "")
                nombre = re.sub(r"[^a-zA-Z0-9_.-]", "_", nombre)[:80]
                ruta = RUTA_FORMULARIOS / f"{nombre}.js"
                ruta.write_text(body, encoding="utf-8", errors="replace")
                archivos_descargados.append(ruta)
                print(f"  Formulario descargado: {nombre}.js ({len(body)} chars)")

        page.on("response", on_response)

        try:
            print("Login en TOA (Playwright)...")
            login(page, TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD)

            for i, fe in enumerate(fes):
                print(f"\n[{i+1}/{len(fes)}] Abriendo {fe}...")
                encontrado = buscar_y_abrir_fe(page, fe)
                print(f"  {'encontrado' if encontrado else 'NO encontrado'}")
                if i < len(fes) - 1:
                    page.wait_for_timeout(int(random.uniform(8000, 15000)))
        finally:
            browser.close()

    print(f"\nTotal formularios descargados: {len(archivos_descargados)}")
    for r in archivos_descargados:
        print(f"  {r.name}")


if __name__ == "__main__":
    main()
