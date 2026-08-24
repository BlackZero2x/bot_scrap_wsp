"""
Cliente Python que se comunica con el servidor Node.js wa_toa_server.js
(instancia dedicada al bot "Yugi Backoffice", puerto 8003).

Réplica de AVANCE_MOVISTAR/whatsapp_server/wa_client.py apuntando a esta
instancia — misma API HTTP, mismo formato de respuesta. Se omite
send_daily_reports() porque es específico del orquestador de ese otro
proyecto y no aplica aquí.

Uso desde el bot /estado (futuro):
    from wa_client import WhatsAppClient
    wa = WhatsAppClient()
    wa.send_text("Grupo Chimbote", "Instalada el 18/08/2026")

Uso como test independiente:
    python wa_client.py --test
    python wa_client.py --list-groups
    python wa_client.py --list-contacts "nombre"
"""

import requests
import json
import time
import argparse
import sys
import os
from datetime import datetime


class WhatsAppClient:
    """Cliente HTTP para el servidor wa_toa_server.js (whatsapp-web.js)."""

    def __init__(self, host="localhost", port=8003, config_path=None, max_retries=3):
        self.base_url = f"http://{host}:{port}"
        self.max_retries = max_retries
        self.retry_delay = 5  # segundos entre reintentos
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "config.json",
        )
        self.config = self._load_config()

    def _load_config(self):
        """Carga la configuración desde config.json."""
        try:
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[WARN] config.json no encontrado en {self.config_path}")
            return {"groups": {}, "contacts": {}, "messages": {}, "my_number": ""}

    def _request(self, method, endpoint, **kwargs):
        """Hace una petición HTTP con reintentos."""
        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if method == "GET":
                    resp = requests.get(url, params=kwargs.get("params"), timeout=30)
                else:
                    resp = requests.post(url, json=kwargs.get("json"), timeout=60)

                # Intentar parsear JSON
                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = {}

                # Validar HTTP 200 pero también verificar si hay "error" en el JSON.
                # /list-groups y /list-contacts devuelven una lista JSON en éxito
                # (no un dict), así que .get() solo aplica cuando resp_json es dict —
                # una lista nunca trae "error" incrustado.
                if resp.status_code == 200:
                    # Si el servidor devolvió un error en el body (incluso con HTTP 200)
                    if isinstance(resp_json, dict) and resp_json.get("error"):
                        error_msg = resp_json.get("error")
                        # Detectar errores de Puppeteer específicos
                        if "Promise was collected" in error_msg or "Protocol error" in error_msg:
                            last_error = f"Servidor puppeteer inestable: {error_msg[:100]}"
                            print(f"  [Intento {attempt}/{self.max_retries}] {last_error}")
                            if attempt < self.max_retries:
                                time.sleep(self.retry_delay * attempt * 2)  # espera más larga para Puppeteer
                                continue
                        return {"success": False, "error": error_msg, "status": 200}
                    return {"success": True, "data": resp_json}
                elif resp.status_code == 503:
                    error_msg = resp_json.get("error", "")
                    if "Cola llena" in error_msg:
                        # Cola saturada — esperar poco, se libera en segundos
                        print(f"  [Intento {attempt}/{self.max_retries}] {error_msg} Reintentando en 8s...")
                        time.sleep(8)
                    else:
                        # Servidor no listo (reconectando) — esperar más
                        print(f"  [Intento {attempt}/{self.max_retries}] WhatsApp no esta listo, esperando {self.retry_delay * attempt}s...")
                        time.sleep(self.retry_delay * attempt)
                    continue
                else:
                    error_data = resp_json if resp_json else {"error": resp.text}
                    return {"success": False, "error": error_data.get("error", resp.text), "status": resp.status_code}

            except requests.ConnectionError:
                last_error = "No se puede conectar al servidor WhatsApp. ¿Está corriendo wa_toa_server.js?"
                print(f"  [Intento {attempt}/{self.max_retries}] {last_error}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
            except requests.Timeout:
                last_error = "Timeout esperando respuesta del servidor WhatsApp"
                print(f"  [Intento {attempt}/{self.max_retries}] {last_error}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
            except Exception as e:
                last_error = str(e)
                print(f"  [Intento {attempt}/{self.max_retries}] Error: {last_error}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

        return {"success": False, "error": last_error or "Máximo de reintentos alcanzado"}

    # ==========================================================
    # MÉTODOS PÚBLICOS
    # ==========================================================

    def is_ready(self):
        """Verifica si el servidor WhatsApp está listo."""
        result = self._request("GET", "/health")
        if result["success"]:
            return result["data"].get("status") == "ready"
        return False

    def send_text(self, to, message):
        """
        Envía un mensaje de texto.
        Args:
            to: Nombre del grupo/contacto (de config.json) o ID directo
            message: Texto del mensaje
        """
        print(f"[WA] Enviando texto a '{to}'...")
        result = self._request("POST", "/send-text", json={"to": to, "message": message})
        if result["success"]:
            print(f"[WA] [OK] Texto enviado a '{to}'")
        else:
            print(f"[WA] [ERROR] Error enviando a '{to}': {result['error']}")
        return result

    def send_image(self, to, image_path, caption=""):
        """
        Envía una imagen desde una ruta local.
        Args:
            to: Nombre del grupo/contacto (de config.json) o ID directo
            image_path: Ruta absoluta a la imagen en la PC
            caption: Texto opcional debajo de la imagen
        """
        if not os.path.exists(image_path):
            error = f"Archivo no encontrado: {image_path}"
            print(f"[WA] [ERROR] {error}")
            return {"success": False, "error": error}

        print(f"[WA] Enviando imagen a '{to}': {os.path.basename(image_path)}...")
        result = self._request(
            "POST",
            "/send-image",
            json={"to": to, "image_path": image_path, "caption": caption},
        )
        if result["success"]:
            print(f"[WA] [OK] Imagen enviada a '{to}'")
        else:
            print(f"[WA] [ERROR] Error enviando imagen a '{to}': {result['error']}")
        return result

    def send_link(self, to, url, description=""):
        """
        Envía un link con descripción.
        Args:
            to: Nombre del grupo/contacto (de config.json) o ID directo
            url: URL del link
            description: Texto que acompaña al link
        """
        print(f"[WA] Enviando link a '{to}'...")
        result = self._request(
            "POST",
            "/send-link",
            json={"to": to, "url": url, "description": description},
        )
        if result["success"]:
            print(f"[WA] [OK] Link enviado a '{to}'")
        else:
            print(f"[WA] [ERROR] Error enviando link a '{to}': {result['error']}")
        return result

    def send_file(self, to, file_path, caption=""):
        """
        Envía un archivo (Excel, PDF, etc.) desde una ruta local.
        Args:
            to: Nombre del grupo/contacto (de config.json) o ID directo
            file_path: Ruta absoluta al archivo
            caption: Texto opcional junto al archivo
        """
        if not os.path.exists(file_path):
            error = f"Archivo no encontrado: {file_path}"
            print(f"[WA] [ERROR] {error}")
            return {"success": False, "error": error}

        print(f"[WA] Enviando archivo a '{to}': {os.path.basename(file_path)}...")
        result = self._request(
            "POST",
            "/send-file",
            json={"to": to, "file_path": file_path, "caption": caption},
        )
        if result["success"]:
            print(f"[WA] [OK] Archivo enviado a '{to}'")
        else:
            print(f"[WA] [ERROR] Error enviando archivo a '{to}': {result['error']}")
        return result

    def send_mention(self, to, message, mentions=None):
        """
        Envía un mensaje con menciones a un grupo.
        Args:
            to: Nombre del grupo (de config.json) o ID directo
            message: Texto con @numero para mencionar
            mentions: Lista de IDs a mencionar (ej. ["51900000000@c.us"])
        """
        print(f"[WA] Enviando mensaje con menciones a '{to}'...")
        payload = {"to": to, "message": message}
        if mentions:
            payload["mentions"] = mentions
        result = self._request("POST", "/send-mention", json=payload)
        if result["success"]:
            print(f"[WA] [OK] Mensaje con menciones enviado a '{to}'")
        else:
            print(f"[WA] [ERROR] Error enviando menciones a '{to}': {result['error']}")
        return result

    def list_groups(self):
        """Lista todos los grupos de WhatsApp con sus IDs."""
        result = self._request("GET", "/list-groups")
        if result["success"]:
            return result["data"]
        print(f"[WA] [ERROR] Error listando grupos: {result['error']}")
        return []

    def list_contacts(self, name):
        """Busca contactos por nombre."""
        result = self._request("GET", "/list-contacts", params={"name": name})
        if result["success"]:
            return result["data"]
        print(f"[WA] [ERROR] Error buscando contactos: {result['error']}")
        return []


# ==============================================================
# CLI PARA TESTING
# ==============================================================
def main():
    parser = argparse.ArgumentParser(description="WhatsApp Client (Yugi Backoffice) - Testing CLI")
    parser.add_argument("--test", action="store_true", help="Enviar mensaje de prueba a tu propio número")
    parser.add_argument("--test-image", type=str, help="Enviar imagen de prueba (ruta al archivo)")
    parser.add_argument("--test-file", type=str, help="Enviar archivo de prueba (ruta al archivo)")
    parser.add_argument("--test-link", type=str, help="Enviar link de prueba")
    parser.add_argument("--list-groups", action="store_true", help="Listar todos los grupos")
    parser.add_argument("--list-contacts", type=str, help="Buscar contactos por nombre")
    parser.add_argument("--send-to", type=str, help="Enviar a un destino específico (nombre o ID)")
    parser.add_argument("--message", type=str, help="Mensaje a enviar con --send-to")
    parser.add_argument("--health", action="store_true", help="Verificar estado del servidor")

    args = parser.parse_args()
    wa = WhatsAppClient()

    if args.health:
        ready = wa.is_ready()
        print(f"Servidor WhatsApp (Yugi Backoffice): {'[OK] Listo' if ready else '[ERROR] No disponible'}")
        sys.exit(0 if ready else 1)

    if args.list_groups:
        groups = wa.list_groups()
        if groups:
            print(f"\n{'Nombre':<45} {'ID':<35} {'Miembros'}")
            print("-" * 90)
            for g in groups:
                nombre = g['name'].encode('cp1252', errors='replace').decode('cp1252')
                print(f"{nombre:<45} {g['id']:<35} {g.get('participants', '?')}")
        else:
            print("No se encontraron grupos o el servidor no está disponible.")
        sys.exit(0)

    if args.list_contacts:
        contacts = wa.list_contacts(args.list_contacts)
        if contacts:
            print(f"\n{'Nombre':<30} {'Push Name':<20} {'Número':<15} {'ID'}")
            print("-" * 85)
            for c in contacts:
                print(f"{c['name']:<30} {c['pushname']:<20} {c['number']:<15} {c['id']}")
        else:
            print(f"No se encontraron contactos con '{args.list_contacts}'")
        sys.exit(0)

    if args.test:
        my_number = wa.config.get("my_number", "")
        if not my_number:
            print("[ERROR] Configura 'my_number' en config.json primero")
            sys.exit(1)
        result = wa.send_text(my_number, f"[Yugi] Test de automatizacion - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        sys.exit(0 if result.get("success") else 1)

    if args.test_image:
        my_number = wa.config.get("my_number", "")
        if not my_number:
            print("[ERROR] Configura 'my_number' en config.json primero")
            sys.exit(1)
        result = wa.send_image(my_number, args.test_image, caption="Test de imagen automatizada")
        sys.exit(0 if result.get("success") else 1)

    if args.test_file:
        my_number = wa.config.get("my_number", "")
        if not my_number:
            print("[ERROR] Configura 'my_number' en config.json primero")
            sys.exit(1)
        result = wa.send_file(my_number, args.test_file, caption="Test de archivo automatizado")
        sys.exit(0 if result.get("success") else 1)

    if args.test_link:
        my_number = wa.config.get("my_number", "")
        if not my_number:
            print("[ERROR] Configura 'my_number' en config.json primero")
            sys.exit(1)
        result = wa.send_link(my_number, args.test_link, "Test de link automatizado")
        sys.exit(0 if result.get("success") else 1)

    if args.send_to and args.message:
        result = wa.send_text(args.send_to, args.message)
        sys.exit(0 if result.get("success") else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
