"""
Configuración centralizada del proyecto au_tl_bot.
Carga variables de entorno desde .env usando python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# Cargar variables de entorno desde .env
load_dotenv()

# ============================================================================
# SQL Server - eAuren (Fuente: FEs a procesar)
# ============================================================================
AUREN_SERVER = os.getenv('AUREN_SERVER', 'AUREN22\\AUREN')
AUREN_DB = os.getenv('AUREN_DB', 'eAuren')
AUREN_USER = os.environ['AUREN_USER']
AUREN_PASSWORD = os.environ['AUREN_PASSWORD']
AUREN_DRIVER = os.getenv('AUREN_DRIVER', 'ODBC Driver 17 for SQL Server')

# ============================================================================
# SQL Server - pbi2 (Destino: Datos extraídos de TOA)
# ============================================================================
TOA_SERVER = os.getenv('TOA_SERVER', 'AUREN22\\AUREN')
TOA_DB = os.getenv('TOA_DB', 'pbi2')
TOA_USER = os.environ['TOA_USER']
TOA_PASSWORD = os.environ['TOA_PASSWORD']
TOA_DRIVER = os.getenv('TOA_DRIVER', 'ODBC Driver 17 for SQL Server')

# ============================================================================
# Credenciales TOA Portal (login web)
# ============================================================================
TOA_PORTAL_USERNAME = os.getenv('TOA_PORTAL_USERNAME', '')
TOA_PORTAL_PASSWORD = os.getenv('TOA_PORTAL_PASSWORD', '')

# ============================================================================
# SQL Server - pbi2 Usuarios Telegram (mismo servidor que TOA, diferente user)
# ============================================================================
TG_USUARIOS_USER = os.environ['TG_USUARIOS_USER']
TG_USUARIOS_PASSWORD = os.environ['TG_USUARIOS_PASSWORD']

# ============================================================================
# Telegram Bot
# ============================================================================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')

# ============================================================================
# VENTORY (Google Sheet "Integratel-GrupoAuren", hoja REG_VTAS_BBDD) — LEGADO
# ============================================================================
# Reemplazado por VENTORY Postgres (ventas_db, ver bloque de abajo) como
# fuente de FEs en query_fe_filter.py y mantenimiento_continuo.py (migración
# 2026-08). Ya no es obligatorio: solo scripts_db/ventory_sheet.py (utilidad
# legado, sin uso en el flujo productivo) lo necesita. os.getenv sin default
# evita que CUALQUIER script que importe config.py truene al no tener estas
# variables — antes rompía incluso a consultar_estado_fe.py, que nunca usa
# el Sheet (confirmado 2026-08-24).
VENTORY_SHEET_ID = os.getenv('VENTORY_SHEET_ID')
_ventory_sheet_gid = os.getenv('VENTORY_SHEET_GID')
VENTORY_SHEET_GID = int(_ventory_sheet_gid) if _ventory_sheet_gid else None
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', str(Path(__file__).parent / 'credentials.json'))
GOOGLE_TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', str(Path(__file__).parent / 'token.json'))

# ============================================================================
# VENTORY Postgres (ventas_db) — fuente en tiempo real, distinta del Sheet.
# codigo_seguridad = FE, codigo_seguridad_2 = eAuren.peticion (puente
# confirmado cruzando datos reales, sesión 2026-08-19).
# ============================================================================
VENTORY_PG_HOST = os.getenv('host', '')
VENTORY_PG_PORT = os.getenv('port', '5433')
VENTORY_PG_DB = os.getenv('tabla', 'ventas_db')
VENTORY_PG_USER = os.getenv('user', '')
VENTORY_PG_PASSWORD = os.getenv('password', '')

# ============================================================================
# Motores SQLAlchemy - Funciones de conexión
# ============================================================================

def get_engine_auren():
    """Retorna motor de conexión a eAuren (base de datos fuente)."""
    params = quote_plus(
        f'DRIVER={AUREN_DRIVER};'
        f'SERVER={AUREN_SERVER};'
        f'DATABASE={AUREN_DB};'
        f'UID={AUREN_USER};'
        f'PWD={AUREN_PASSWORD}'
    )
    return create_engine(f'mssql+pyodbc:///?odbc_connect={params}')

def get_engine_toa():
    """
    Retorna motor de conexión a pbi2 (base de datos destino).

    pool_size=2, max_overflow=1: el default de SQLAlchemy (pool_size=5,
    max_overflow=10) permite hasta 15 conexiones simultáneas por proceso —
    cada consulta /estado del bot lanza un proceso Python nuevo
    (consultar_estado_fe.py vía execFile), así que ese default multiplicado
    por varios procesos concurrentes puede saturar el límite real de
    sesiones/logins concurrentes del login adminpbi2 en SQL Server. El DBA
    confirmó (2026-08-20) que hay que revisar cómo el cliente está
    consumiendo la conexión — este límite explícito acota la presión que
    el propio bot ejerce sobre esa cuenta, en vez de dejar que cada proceso
    abra tantas conexiones como SQLAlchemy permita por defecto.
    """
    params = quote_plus(
        f'DRIVER={TOA_DRIVER};'
        f'SERVER={TOA_SERVER};'
        f'DATABASE={TOA_DB};'
        f'UID={TOA_USER};'
        f'PWD={TOA_PASSWORD}'
    )
    return create_engine(
        f'mssql+pyodbc:///?odbc_connect={params}',
        pool_size=2,
        max_overflow=1,
        pool_timeout=10,
    )

# Instancias globales (lazy-loaded)
_engine_auren = None
_engine_toa = None

def engine_auren():
    """Retorna instancia global del motor eAuren."""
    global _engine_auren
    if _engine_auren is None:
        _engine_auren = get_engine_auren()
    return _engine_auren

def engine_toa():
    """Retorna instancia global del motor pbi2."""
    global _engine_toa
    if _engine_toa is None:
        _engine_toa = get_engine_toa()
    return _engine_toa

def get_engine_tg_usuarios():
    """Retorna motor de conexión a pbi2 para usuarios del bot de Telegram."""
    params = quote_plus(
        f'DRIVER={TOA_DRIVER};'
        f'SERVER={TOA_SERVER};'
        f'DATABASE={TOA_DB};'
        f'UID={TG_USUARIOS_USER};'
        f'PWD={TG_USUARIOS_PASSWORD}'
    )
    return create_engine(f'mssql+pyodbc:///?odbc_connect={params}')

_engine_tg_usuarios = None

def engine_tg_usuarios():
    """Retorna instancia global del motor de usuarios Telegram."""
    global _engine_tg_usuarios
    if _engine_tg_usuarios is None:
        _engine_tg_usuarios = get_engine_tg_usuarios()
    return _engine_tg_usuarios

def get_engine_ventory_pg():
    """Retorna motor de conexión al Postgres de VENTORY (ventas_db)."""
    params = quote_plus(VENTORY_PG_PASSWORD)
    return create_engine(
        f'postgresql+psycopg2://{VENTORY_PG_USER}:{params}@'
        f'{VENTORY_PG_HOST}:{VENTORY_PG_PORT}/{VENTORY_PG_DB}'
    )

_engine_ventory_pg = None

def engine_ventory_pg():
    """Retorna instancia global del motor de VENTORY Postgres."""
    global _engine_ventory_pg
    if _engine_ventory_pg is None:
        _engine_ventory_pg = get_engine_ventory_pg()
    return _engine_ventory_pg
