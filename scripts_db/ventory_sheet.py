"""
Lectura de la hoja REG_VTAS_BBDD del Google Sheet "Integratel-GrupoAuren".
Fuente de origen VENTORY: registro de ventas (codigo_fe, peticion) hecho por
los vendedores en la app VENTORY de AUREN.

Reemplaza a eAuren.dbo.fija_controlnet_detallado como origen de FEs a procesar.
"""
import sys
from pathlib import Path

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    VENTORY_SHEET_ID,
    VENTORY_SHEET_GID,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

COLUMNAS = ["fecha_registro", "dni_vendedor", "codigo_fe", "peticion"]


def _autenticar():
    creds = None
    token_path = Path(GOOGLE_TOKEN_PATH)
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("sheets", "v4", credentials=creds)


def _resolver_gid_a_nombre(service, sheet_id):
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return {
        sheet["properties"]["sheetId"]: sheet["properties"]["title"]
        for sheet in meta.get("sheets", [])
    }


def obtener_ventas_ventory() -> pd.DataFrame:
    """
    Lee la hoja REG_VTAS_BBDD (identificada por VENTORY_SHEET_GID) y devuelve
    un DataFrame con columnas [fecha_registro, dni_vendedor, codigo_fe, peticion].
    """
    service = _autenticar()

    gid_map = _resolver_gid_a_nombre(service, VENTORY_SHEET_ID)
    nombre_hoja = gid_map.get(VENTORY_SHEET_GID)
    if not nombre_hoja:
        raise ValueError(f"No se encontró ninguna pestaña con gid {VENTORY_SHEET_GID} en el Sheet VENTORY.")

    result = service.spreadsheets().values().get(
        spreadsheetId=VENTORY_SHEET_ID,
        range=f"{nombre_hoja}!A1:D",
    ).execute()
    filas = result.get("values", [])

    if not filas:
        return pd.DataFrame(columns=COLUMNAS)

    df = pd.DataFrame(filas[1:], columns=COLUMNAS)
    df = df[df["codigo_fe"].notna() & (df["codigo_fe"] != "")]
    df = df.drop_duplicates(subset=["codigo_fe"])
    return df.reset_index(drop=True)


if __name__ == "__main__":
    df = obtener_ventas_ventory()
    print(f"Total registros VENTORY: {len(df)}")
    print(df.head())
