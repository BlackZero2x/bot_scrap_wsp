"""
Script de diagnóstico puntual: hace login en TOA (sin buscar ningún FE) y
vuelca TODAS las URLs de red vistas hasta ese momento, para identificar
manualmente bundles de configuración/formularios (forms, layouts, plugin)
que la app carga al iniciar sesión — candidatos al "diccionario completo de
campos" que describe el Data Engineer.

Uso:
    python scripts_db/diagnostico_urls_login.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from diagnostico_red_toa import _crear_sesion_con_login, listar_todas_las_urls
from config import TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD

sys.path.insert(0, str(Path(__file__).parent))


def main():
    driver = _crear_sesion_con_login()
    try:
        time.sleep(8)  # dar tiempo extra a que carguen recursos diferidos
        urls = listar_todas_las_urls(driver)

        salida = Path(__file__).parent.parent / "diagnostico_urls_login.txt"
        with open(salida, "w", encoding="utf-8") as f:
            for u in urls:
                f.write(f"[{u['status']}] {u['mime']:30} {u['url']}\n")

        print(f"\n{len(urls)} URLs capturadas. Guardado en: {salida}")

        candidatas = [u for u in urls if any(
            kw in u["url"].lower() for kw in ["form", "layout", "plugin", "propert", "label", "translat", "cache-"]
        )]
        print(f"\n{len(candidatas)} candidatas a bundle de config/formularios:")
        for c in candidatas:
            print(f"  [{c['status']}] {c['mime']:25} {c['url']}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
