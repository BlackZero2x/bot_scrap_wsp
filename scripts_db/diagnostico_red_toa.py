"""
Script de diagnóstico (uso manual, no forma parte del pipeline productivo).

Hace login en TOA (Selenium propio, igual que BotTOA) y busca una lista de
FEs de prueba, uno por uno, con pausas variables entre cada búsqueda para
imitar un ritmo de uso humano (no ráfagas). Para cada FE encontrado, captura
la llamada de red interna (?m=sync&a=write) que trae el detalle de la
actividad en JSON, y guarda solo el registro de `Activity` correspondiente
a ese FE (no el payload completo, que incluye datos de muchos otros
recursos ajenos a la búsqueda).

Objetivo: acumular una muestra de payloads reales de distintos estados de
FE (Completado, Cancelado, Suspendido, etc.) para tabular qué campos trae
cada uno y poder mapearlos contra dict_info_cod de scrapper.py.

Uso:
    python scripts_db/diagnostico_red_toa.py pruebas_FE_13082026.txt --max 100

Salida (incremental, se reescribe tras cada FE procesado):
    diagnostico_red_toa_muestra.json — {fe: {encontrado, estado, activity}}
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from selenium.webdriver import Chrome
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

from config import TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD

SALIDA = Path(__file__).parent.parent / "diagnostico_red_toa_muestra.json"
SALIDA_LABELS = Path(__file__).parent.parent / "diagnostico_labels_formdata.json"


def _crear_driver():
    chrome_install = ChromeDriverManager().install()
    folder = Path(chrome_install).parent
    chromedriver_path = folder / "chromedriver.exe"
    service = ChromeService(str(chromedriver_path))

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--disable-notifications")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    return Chrome(service=service, options=options)


def login(driver, username, password):
    wait = WebDriverWait(driver, 30)
    driver.get("https://telefonica-pe.etadirect.com/")

    input_username = wait.until(EC.presence_of_element_located((By.ID, "username")))
    input_username.click()
    input_username.send_keys(username)

    input_password = wait.until(EC.presence_of_element_located((By.ID, "password")))
    input_password.click()
    input_password.send_keys(password)

    wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "/html/body/div/div/div/div/form/div[2]/div[5]/button/div")
        )
    ).click()

    try:
        btn_delete_sessions = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div/div/div/form/div[2]/div[4]/div[1]/div[1]/span/span/input")
            )
        )
        btn_delete_sessions.click()
        input_password = wait.until(EC.presence_of_element_located((By.ID, "password")))
        input_password.click()
        input_password.send_keys(password)
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div/div/div/form/div[2]/div[6]/button/div")
            )
        ).click()
    except Exception:
        print("No hay otras sesiones; continuando...")

    try:
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Buscar en actividades']"))
        )
        time.sleep(6)  # margen para que la app termine de cargar recursos en background
        print("Login OK — buscador de actividades visible.")
    except Exception:
        diag_dir = Path(__file__).parent.parent
        driver.save_screenshot(str(diag_dir / "diagnostico_login_fallo.png"))
        (diag_dir / "diagnostico_login_fallo.html").write_text(driver.page_source, encoding="utf-8")
        print(f"FALLO AL CARGAR APP TRAS LOGIN. URL actual: {driver.current_url}")
        raise


def _campo_busqueda_visible(driver):
    candidatos = driver.find_elements(By.CSS_SELECTOR, "input[aria-label='Buscar en actividades']")
    for c in candidatos:
        if c.is_displayed():
            return c
    candidatos = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Buscar en actividades']")
    for c in candidatos:
        if c.is_displayed():
            return c
    raise Exception("No se encontró un campo de búsqueda visible")


def buscar_fe(driver, fe):
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Buscar en actividades']")))

    search_field = _campo_busqueda_visible(driver)
    search_field.click()
    search_field.send_keys(Keys.CONTROL, "a")
    search_field.send_keys(Keys.BACKSPACE)

    actions = ActionChains(driver)
    for char in fe:
        actions.send_keys(char)
        actions.pause(random.uniform(0.03, 0.09))  # cadencia de tecleo humana
    actions.perform()
    time.sleep(random.uniform(3.5, 6))

    try:
        fe_div = wait.until(
            EC.presence_of_element_located((By.XPATH, '//div[@aria-label="activity result item"]'))
        )
        fe_div.click()
        time.sleep(random.uniform(3, 5))
        return True
    except Exception:
        return False


def capturar_html_actividad(driver, fe):
    """Guarda el HTML completo del panel de detalle actualmente abierto,
    para inspeccionar manualmente la estructura de labels/id_index_N."""
    diag_dir = Path(__file__).parent.parent
    (diag_dir / f"diagnostico_dom_{fe}.html").write_text(driver.page_source, encoding="utf-8")


def listar_todas_las_urls(driver):
    """Lista TODAS las URLs de red vistas hasta el momento (sin filtrar por
    keyword), para identificar manualmente bundles de configuración/labels
    (forms, layouts, plugin) que la app carga al iniciar sesión."""
    logs = driver.get_log("performance")
    urls = []
    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if message.get("method") == "Network.responseReceived":
            params = message.get("params", {})
            response = params.get("response", {})
            urls.append({
                "url": response.get("url", ""),
                "mime": response.get("mimeType", ""),
                "status": response.get("status"),
            })
    return urls


def capturar_payload_completo_y_metadata(driver, fe):
    """Guarda el payload JSON completo de sync (no solo delta.Activity) y
    busca además recursos .js/.json de configuración cargados por la app que
    puedan contener el diccionario de propiedades/labels de OFSC
    (translations, capacityCategories, form definitions, etc.)."""
    diag_dir = Path(__file__).parent.parent
    logs = driver.get_log("performance")

    responses = {}  # requestId -> {url, mime}
    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if message.get("method") == "Network.responseReceived":
            params = message.get("params", {})
            response = params.get("response", {})
            responses[params.get("requestId")] = {
                "url": response.get("url", ""),
                "mime": response.get("mimeType", ""),
            }

    payload_completo_guardado = False
    candidatos_metadata = []

    for request_id, info in responses.items():
        url = info["url"]
        mime = info["mime"]
        es_json = "json" in mime
        es_js = "javascript" in mime or url.endswith(".js")

        if not (es_json or es_js):
            continue

        try:
            resultado = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            body = resultado.get("body")
            if not body:
                continue
        except Exception:
            continue

        if es_json and "sync" in url and not payload_completo_guardado:
            try:
                parsed = json.loads(body)
                if parsed.get("delta", {}).get("Activity"):
                    (diag_dir / f"diagnostico_sync_completo_{fe}.json").write_text(
                        json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    payload_completo_guardado = True
                    print(f"  Payload completo de sync guardado ({len(body)} chars)")
            except Exception:
                pass

        # Heurística: buscar en cualquier respuesta JSON/JS palabras clave de
        # metadata de propiedades/labels (sin descargar todo el bundle a ciegas)
        palabras_clave = ["translation", "capacityCateg", "propertyLabel", "displayLabel",
                          "fieldLabel", "XA_USER_AGENDA", "A_IND_BRIGADA", "customer_number"]
        if any(kw in body for kw in palabras_clave) and "sync" not in url:
            candidatos_metadata.append({"url": url, "mime": mime, "size": len(body)})
            nombre_archivo = url.split("/")[-1].split("?")[0] or f"recurso_{request_id}"
            nombre_archivo = "".join(c if c.isalnum() or c in "._-" else "_" for c in nombre_archivo)[:80]
            (diag_dir / f"diagnostico_meta_{nombre_archivo}.txt").write_text(body, encoding="utf-8")

    if candidatos_metadata:
        print(f"  {len(candidatos_metadata)} recursos candidatos a metadata guardados:")
        for c in candidatos_metadata:
            print(f"    {c['url']} ({c['mime']}, {c['size']} chars)")
    else:
        print("  Ningún recurso JS/JSON adicional con palabras clave de metadata encontrado en este ciclo.")


_GRUPOS_FORMDATA_IGNORAR = {"section", "page_header", "form_submit_link_pdf", "section_column_manager"}


def _extraer_labels_de_formdata(form_data_dict):
    """A partir de delta.FormData, devuelve {campo_id: {label, form_label}}
    parseando el JSON embebido en cada form_data (definición del formulario
    dinámico submitted, con título visible de cada campo)."""
    mapeos = {}
    for _, meta in (form_data_dict or {}).items():
        form_label = meta.get("form_label", "")
        raw = meta.get("form_data")
        if not raw:
            continue
        try:
            fd = json.loads(raw)
        except Exception:
            continue
        elements = fd.get("__snapshot", {}).get("elements", [])
        for el in elements:
            field_id = el.get("i", {}).get("i")
            titulo = el.get("t")
            grupo = el.get("g")
            if field_id and titulo and grupo not in _GRUPOS_FORMDATA_IGNORAR:
                mapeos[str(field_id)] = {"label": titulo, "form": form_label}
    return mapeos


def extraer_activity_y_labels(driver, fe):
    """Busca en el performance log la respuesta de sync que contenga la
    Activity cuyo appt_number coincide con el FE buscado. Devuelve
    (activity, labels_formdata) — labels_formdata son los pares
    campo_id->label extraídos de cualquier FormData presente en el mismo
    payload (formularios dinámicos submitted para esa actividad)."""
    logs = driver.get_log("performance")
    request_ids_json = []

    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue

        if message.get("method") == "Network.responseReceived":
            params = message.get("params", {})
            response = params.get("response", {})
            if "json" in (response.get("mimeType") or "") and "sync" in response.get("url", ""):
                request_ids_json.append(params.get("requestId"))

    activity_encontrada = None
    labels_acumulados = {}

    for request_id in request_ids_json:
        try:
            resultado = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            body = resultado.get("body")
            if not body:
                continue
            parsed = json.loads(body)
            delta = parsed.get("delta", {})

            labels_acumulados.update(_extraer_labels_de_formdata(delta.get("FormData")))

            if activity_encontrada is None:
                for _, act in delta.get("Activity", {}).items():
                    if act.get("appt_number") == fe:
                        activity_encontrada = act
                        break
        except Exception:
            continue

    return activity_encontrada, labels_acumulados


def cargar_fes(path_archivo, maximo):
    lineas = Path(path_archivo).read_text(encoding="utf-8").splitlines()
    fes = [l.strip() for l in lineas if l.strip().startswith("FE-")]
    return fes[:maximo]


def cargar_resultado_previo():
    if SALIDA.exists():
        return json.loads(SALIDA.read_text(encoding="utf-8"))
    return {}


def guardar(resultado):
    SALIDA.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")


def cargar_labels_previos():
    if SALIDA_LABELS.exists():
        return json.loads(SALIDA_LABELS.read_text(encoding="utf-8"))
    return {}


def guardar_labels(labels):
    SALIDA_LABELS.write_text(json.dumps(labels, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _crear_sesion_con_login():
    driver = _crear_driver()
    for intento in range(1, 4):
        try:
            print(f"Login en TOA (intento {intento}/3)...")
            login(driver, TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD)
            return driver
        except Exception as e:
            print(f"  Falló el login: {e}")
            if intento == 3:
                driver.quit()
                raise
            time.sleep(10)
            driver.get("https://telefonica-pe.etadirect.com/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archivo_fes")
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--capturar-dom", action="store_true", dest="capturar_dom",
                         help="Guarda el HTML del panel del primer FE encontrado (para inspeccionar labels)")
    args = parser.parse_args()
    dom_capturado = [False]

    fes = cargar_fes(args.archivo_fes, args.max)
    resultado = cargar_resultado_previo()
    labels_globales = cargar_labels_previos()

    max_reinicios_sesion = 30
    reinicios = 0

    while True:
        pendientes = [fe for fe in fes if fe not in resultado]
        print(f"Total: {len(fes)} | procesados: {len(fes) - len(pendientes)} | pendientes: {len(pendientes)}")

        if not pendientes:
            print("Nada pendiente.")
            break

        print("Iniciando Chrome headless...")
        try:
            driver = _crear_sesion_con_login()
        except Exception as e:
            print(f"No se pudo iniciar sesión tras 3 intentos: {e}")
            break

        sesion_rota = False
        try:
            for i, fe in enumerate(pendientes, start=1):
                print(f"[{i}/{len(pendientes)}] Buscando {fe}...")
                driver.get_log("performance")  # limpiar acumulado

                try:
                    encontrado = buscar_fe(driver, fe)
                except Exception as e:
                    print(f"  ERROR de sesión: {e}")
                    sesion_rota = True
                    break

                if not encontrado:
                    resultado[fe] = {"encontrado": False, "estado": None, "activity": None}
                    print("  no encontrado")
                else:
                    if args.capturar_dom and not dom_capturado[0]:
                        capturar_html_actividad(driver, fe)
                        capturar_payload_completo_y_metadata(driver, fe)
                        dom_capturado[0] = True
                        print(f"  DOM y metadata capturados para {fe}")

                    act, labels_fe = extraer_activity_y_labels(driver, fe)
                    if labels_fe:
                        nuevos = [k for k in labels_fe if k not in labels_globales]
                        labels_globales.update(labels_fe)
                        if nuevos:
                            print(f"  +{len(nuevos)} labels nuevas de FormData (total acumulado: {len(labels_globales)})")

                    if act:
                        resultado[fe] = {"encontrado": True, "estado": act.get("astatus"), "activity": act}
                        print(f"  OK — estado: {act.get('astatus')}, campos: {len(act)}")
                    else:
                        resultado[fe] = {"encontrado": True, "estado": None, "activity": None}
                        print("  encontrado pero sin payload de Activity")

                guardar(resultado)
                guardar_labels(labels_globales)

                if i < len(pendientes):
                    if random.random() < 0.12:
                        espera = random.uniform(25, 55)
                    else:
                        espera = random.uniform(8, 20)
                    time.sleep(espera)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        if not sesion_rota:
            break  # se completaron todos los pendientes sin caídas

        reinicios += 1
        if reinicios >= max_reinicios_sesion:
            print(f"Se alcanzó el máximo de reinicios de sesión ({max_reinicios_sesion}). Deteniendo.")
            break
        print(f"Reiniciando sesión (reinicio {reinicios}/{max_reinicios_sesion})...")
        time.sleep(15)

    encontrados = sum(1 for v in resultado.values() if v.get("encontrado") and v.get("activity"))
    print(f"\nTotal con Activity capturada: {encontrados}/{len(resultado)}")
    print(f"Total labels campo->título acumuladas (vía FormData): {len(labels_globales)}")
    print(f"Guardado en: {SALIDA} y {SALIDA_LABELS}")


if __name__ == "__main__":
    main()
