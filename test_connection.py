#!/usr/bin/env python
"""
Script de prueba para verificar la conectividad de bases de datos.
Valida que todas las conexiones SQL Server estén funcionando correctamente.
"""
import sys
from pathlib import Path

# Añadir raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    engine_auren, engine_toa,
    AUREN_SERVER, AUREN_DB, AUREN_USER,
    TOA_SERVER, TOA_DB, TOA_USER
)

def test_connection(engine, name, server, database, username):
    """Prueba una conexión a SQL Server."""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT @@VERSION")
            version = result.scalar()
        print(f"✅ {name}")
        print(f"   Servidor: {server}")
        print(f"   Base de datos: {database}")
        print(f"   Usuario: {username}")
        print(f"   Versión SQL: {version[:60]}...")
        return True
    except Exception as e:
        print(f"❌ {name}")
        print(f"   Error: {str(e)}")
        return False

def main():
    print("=" * 70)
    print("PRUEBA DE CONECTIVIDAD - au_tl_bot")
    print("=" * 70)
    print()

    # Prueba eAuren
    print("1. Conectando a eAuren (Base de datos fuente)...")
    test_auren = test_connection(
        engine_auren(),
        "eAuren",
        AUREN_SERVER,
        AUREN_DB,
        AUREN_USER
    )
    print()

    # Prueba pbi2
    print("2. Conectando a pbi2 (Base de datos destino)...")
    test_toa = test_connection(
        engine_toa(),
        "pbi2",
        TOA_SERVER,
        TOA_DB,
        TOA_USER
    )
    print()

    # Resumen
    print("=" * 70)
    if test_auren and test_toa:
        print("✅ Todas las conexiones están funcionando correctamente.")
        print("   El bot está listo para ejecutarse.")
        return 0
    else:
        print("❌ Algunas conexiones fallaron. Revisa la configuración de .env")
        return 1

if __name__ == '__main__':
    sys.exit(main())
