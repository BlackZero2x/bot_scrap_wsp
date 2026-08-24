"""
Script auxiliar invocado por wa_toa_server.js para enviar alertas por correo
cuando el servidor WhatsApp (Yugi Backoffice) detecta un error crítico de sesión.

Réplica de AVANCE_MOVISTAR/whatsapp_server/notify_error.py, con el envío de
correo inlineado (GmailHelper) en vez de depender de modules.shared, que es
específico de ese otro proyecto y no vive en au_tl_bot. Reutiliza el
token.json/credentials.json propios de au_tl_bot, que ya tienen los mismos
scopes (gmail.modify + drive) usados por scripts_db/ventory_sheet.py.

Uso (desde Node via child_process):
    python notify_error.py --tipo "Promise was collected" --detalle "..."
"""
import os
import sys
import argparse
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


def _autenticar_gmail():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = BASE_DIR / "token.json"
    scopes = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive",
    ]

    if not token_path.exists():
        print(f"[notify_error] token.json no encontrado en {token_path}", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _enviar_correo_simple(service, destinatario, asunto, cuerpo):
    message = MIMEMultipart()
    message["to"] = destinatario
    message["subject"] = asunto
    message.attach(MIMEText(cuerpo, "plain"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tipo", required=True, help="Tipo de error detectado")
    parser.add_argument("--detalle", default="", help="Descripción adicional del error")
    parser.add_argument(
        "--destinatario",
        default=os.getenv("NOTIFY_ERROR_DESTINATARIO", ""),
        help="Correo al que enviar la alerta (default: env var NOTIFY_ERROR_DESTINATARIO)",
    )
    args = parser.parse_args()

    asunto = f"[Yugi Backoffice] Alerta WhatsApp: {args.tipo}"
    cuerpo = f"""Se detectó un error en el servidor WhatsApp del bot TOA (Yugi Backoffice,
+51 946 149 539).

TIPO DE ERROR
=============
{args.tipo}

DETALLE
=======
{args.detalle}

El servidor intentará reiniciarse automáticamente. Si los errores continúan
después de 5 minutos, es necesario intervención manual.

QUÉ HACER SI EL PROBLEMA PERSISTE
===================================
1. Abrir PowerShell y ejecutar:
       Stop-Process -Name node -Force
   (ojo: esto también detiene otras instancias de Node.js corriendo en la
   misma máquina, incluida la de AVANCE_MOVISTAR si convive en el mismo servidor)
2. Esperar 5 segundos y reiniciar:
       cd C:\\proyectos\\au_tl_bot\\whatsapp_server
       node wa_toa_server.js
3. Si sigue fallando (aparece QR de nuevo):
       - Escanear el QR con el celular del número +51 946 149 539
       - Esperar hasta ver "Cliente WhatsApp listo" en la consola

LOGS
====
Ruta: C:\\proyectos\\au_tl_bot\\whatsapp_server\\logs\\

Este correo fue enviado automáticamente por wa_toa_server.js.
"""

    try:
        service = _autenticar_gmail()
        _enviar_correo_simple(service, args.destinatario, asunto, cuerpo)
        print(f"[notify_error] Alerta enviada a {args.destinatario}")
    except Exception as e:
        print(f"[notify_error] Error inesperado: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
