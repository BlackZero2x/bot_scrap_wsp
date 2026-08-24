import pyodbc
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import sys
from pathlib import Path

# Importar configuración centralizada
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import engine_toa, TOA_SERVER, TOA_DB, TOA_USER, TOA_PASSWORD

engine = engine_toa()
conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={TOA_SERVER};DATABASE={TOA_DB};UID={TOA_USER};PWD={TOA_PASSWORD}'

# Conexión pyodbc cruda, lazy — antes se abría a nivel de módulo como efecto
# secundario de importar este archivo, y quedaba viva toda la vida del
# proceso porque scrapper.py importa ver_fe_procesado/ver_fe_filtrado/
# clean_table (que usan engine.begin(), no esta conexión) sin nunca llamar
# a las únicas dos funciones que sí la cierran (ver_tablas2/verify2). Ahora
# solo se crea cuando una función que realmente la necesita (ver_tablas2,
# modificar_cancelados) la pide.
_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        _conn = pyodbc.connect(conn_str)
    return _conn


def ver_tablas2():
    global _conn
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    """)

    # Mostrar tablas
    print("Tablas en la base de datos:")
    for schema, table in cursor.fetchall():
        print(f"{schema}.{table}")

    cursor.close()
    conn.close()
    _conn = None  # se cerró — la próxima llamada a _get_conn() debe abrir una nueva
def ver_tabla():    
    with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
        # Verificar si la tabla existe antes de intentar eliminarla
        # result = conn.execute(check_query)
        table = "fija_data_toa"
        check_query = text(f"""
            SELECT * FROM dbo.{table}
        """)
        df = pd.read_sql(check_query, conn)
        # Pasar el df a Excel
        df.to_excel(f"{table}.xlsx", index=False)
        print("✅ DataFrame exportado a fija_data_toa.xlsx correctamente.")
    # Mostrar el DataFrame completo
    print(df)
        # print(df["estado_general"].unique())
def modificar_cancelados():
    update_query = """
        UPDATE dbo.fija_data_toa
        SET motivo_no_realizado_instalacion = 'Cancelado - Posible LCF'
        WHERE fuente = 'toa'
        AND motivo_no_realizado_instalacion IS NULL
        AND estado_general = 'Cancelado';
        """
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(update_query)
    conn.commit()
    print("Registros actualizados.")
        # Pasar el df a Excel
    print("✅ Campo cancelados modificados correctamente")    
def eliminar_tabla():
    # Eliminar registros donde fuente = 'TOA'
    delete_query = text("DELETE FROM fija_data_toa WHERE fuente = :fuente")

    with engine.begin() as conn:
        result = conn.execute(delete_query, {"fuente": "TOA"})
        print(f"✅ Registros eliminados: {result.rowcount}")

def resetear_tablas():
    try:
        with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
            # Verificar si la tabla ya existe para evitar errores
            check_query = text("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_data_toa'
            """)
            result = conn.execute(check_query)
            table_exists = result.fetchone()
            
            if table_exists:
                print("⚠️ La tabla ya existe. Eliminándola primero...")
                conn.execute(text("DROP TABLE dbo.fija_data_toa;"))
                print("✅ Tabla eliminada correctamente.")
            
            # Crear la tabla
            create_query = text(""" 
            CREATE TABLE fija_data_toa (
                indicador_brigada VARCHAR(255),
                work_order VARCHAR(255),
                codigo_cliente VARCHAR(255),
                nombre_cliente VARCHAR(255),
                tipo_documento VARCHAR(100),
                documento_identidad VARCHAR(100),
                empresa_bucket VARCHAR(255),
                ofertas_productos_servicios VARCHAR(255),
                dato_direccion VARCHAR(255),
                nombre_departamento VARCHAR(100),
                intervalo_tiempo NVARCHAR(100),
                fecha_cita DATETIME,
                respuesta_whatsapp_botmaker NVARCHAR(255),
                hora_envio_mensaje_whatsapp DATETIME,
                hora_respuesta_mensaje_whatsapp DATETIME,
                numero_whatsapp_telefonica NVARCHAR(50),
                usuario_agendamiento NVARCHAR(100),
                fecha_agendamiento VARCHAR(50),
                franja_agendamiento NVARCHAR(100),
                coordenada_tecnico_preform NVARCHAR(255),
                persona_contacto_cierre NVARCHAR(100),
                nombre_persona_recibe NVARCHAR(100),
                dni_persona_recibe NVARCHAR(50),
                motivo_liquidacion_instalacion NVARCHAR(255),
                direccion_incorrecta NVARCHAR(10),
                observaciones_cierre NVARCHAR(MAX),
                codigos_cancelado NVARCHAR(50),
                codigo_no_realizado_tecnicos NVARCHAR(50),
                tipo_devolucion_instalaciones NVARCHAR(255),
                motivo_no_realizado_instalacion NVARCHAR(255),
                franja_postergacion NVARCHAR(100),
                numero_telefono NVARCHAR(50),
                observacion_datos_cita_legados NVARCHAR(MAX),
                observacion_datos_cita_toa NVARCHAR(MAX),
                descripcion_general NVARCHAR(MAX),
                estado_general NVARCHAR(MAX),
                fecha_actualizacion DATETIME,
                fuente NVARCHAR(100),
                dni_vendedor VARCHAR(20)
            );
        """)

            conn.execute(create_query)
            
            # Verificar que la tabla se haya creado correctamente
            verify_query = text("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_data_toa'
            """)
            result = conn.execute(verify_query)
            if result.fetchone():
                print("✅ Tabla creada correctamente y verificada.")
            else:
                print("❌ La tabla no aparece después de crearla.")
            
    except Exception as e:
        print(f"❌ Error al crear la tabla: {str(e)}")

def ver_fe_filtrado():    
    with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
        # Verificar si la tabla existe antes de intentar eliminarla
        check_query = text("""
            SELECT work_order, dni_vendedor FROM dbo.fija_data_toa 
            WHERE estado_general NOT IN ('Completado', 'Cancelado');
        """)
        df = pd.read_sql(check_query, conn)
        return df
def ver_fe_procesado():    
    with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
        # Verificar si la tabla existe antes de intentar eliminarla
        check_query = text("""
            SELECT work_order FROM dbo.fija_data_toa;
        """)
        df = pd.read_sql(check_query, conn)
        return df


def verify2():
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Consultar opciones de sesión, incluyendo formato de fecha
        query = """
        DBCC USEROPTIONS;
        SELECT 
            @@LANGUAGE AS 'Idioma',
            @@DATEFIRST AS 'PrimerDiaSemana';
        """
        
        cursor.execute(query)
        
        # Obtener los resultados de DBCC USEROPTIONS
        print("Opciones de sesión:")
        columns = [desc[0] for desc in cursor.description]
        options = cursor.fetchall()
        
        for row in options:
            print(row)

        # Saltar al siguiente resultado (SELECT @@LANGUAGE y @@DATEFIRST)
        while cursor.nextset():
            result = cursor.fetchone()
            if result:
                print("\nConfiguración adicional:")
                print(f"Idioma: {result[0]}")
                print(f"Primer día de la semana (1=Lun, 7=Dom): {result[1]}")

    except pyodbc.Error as e:
        print("Error al ejecutar la consulta:", e)

    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()
def verify():
    from sqlalchemy import inspect

    # Crear un inspector
    inspector = inspect(engine)

    # Obtener información de columnas
    columns = inspector.get_columns('fija_data_toa')

    # Mostrar información
    print("Estructura de la tabla fija_data_toa:")
    for column in columns:
        print(f"Nombre: {column['name']}")
        print(f"Tipo: {column['type']}")
        print(f"Nullable: {column['nullable']}")
        print(f"Longitud máxima: {column.get('length', 'N/A')}")
        print("---")
# verify()
# resetear_tablas()
# # ver_tablas2()
# ver_tabla()

# ver_fe_filtrado()
from sqlalchemy import text
from datetime import datetime
import re

from sqlalchemy import text
from datetime import datetime
import re

import re

def extract_date(descripcion):
    # Patrón mejorado para capturar día, mes y año por separado
    match = re.search(r'(\d{2})/(\d{2})/(\d{2,4})', descripcion)
    if match:
        day, month, year = match.groups()
        year = int(year)
        # Manejo de años de dos dígitos
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        return f"{day}/{month}/{year}"
    return None

def crear_ult_fecha():
    with engine.begin() as conn:
        # Consulta más segura para obtener registros
        select_query = text("""
            SELECT 
                work_order,
                descripcion_general,
                %%physloc%% AS row_id
            FROM dbo.fija_data_toa 
            WHERE fuente = 'TOA' 
            AND descripcion_general IS NOT NULL
            AND (fecha_ult_tratamiento IS NULL OR fecha_ult_tratamiento = '')
            AND descripcion_general LIKE '%/%/%'  -- Filtro más básico para eficiencia
        """)
        
        results = conn.execute(select_query).fetchall()
        
        updated = 0
        errors = 0
        for row in results:
            try:
                date = extract_date(row.descripcion_general)
                if date:
                    update_query = text("""
                        UPDATE dbo.fija_data_toa
                        SET fecha_ult_tratamiento = :date
                        WHERE work_order = :work_order
                        AND descripcion_general = :descripcion
                        AND (fecha_ult_tratamiento IS NULL OR fecha_ult_tratamiento = '')
                    """)
                    conn.execute(update_query, {
                        'date': date,
                        'work_order': row.work_order,
                        'descripcion': row.descripcion_general
                    })
                    updated += 1
                else:
                    errors += 1
            except Exception as e:
                print(f"Error procesando registro: {row.work_order} - {str(e)}")
                errors += 1
        
        print("\nResumen de ejecución:")
        print(f"Registros encontrados: {len(results)}")
        print(f"Registros actualizados correctamente: {updated}")
        print(f"Registros con formato no reconocido: {errors}")

        # Opcional: Guardar registros no procesados para análisis
        if errors > 0:
            print("\nEjemplos de registros no procesados:")
            for row in results:
                if not extract_date(row.descripcion_general):
                    print(f"WO: {row.work_order} - Descripción: {row.descripcion_general}")
def clean_table():
    with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
        # Verificar si la tabla existe antes de intentar eliminarla
        check_query = text("""
        -- PRIMERO: Verificar qué registros se eliminarán
        WITH CTE_Duplicados AS (
            SELECT 
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY work_order, estado_general 
                    ORDER BY fecha_actualizacion DESC
                ) AS RowNum
            FROM 
                fija_data_toa
            WHERE 
                fuente = 'TOA'
        )
        SELECT *
        FROM CTE_Duplicados
        WHERE RowNum > 1
        ORDER BY work_order, estado_general, fecha_actualizacion DESC;

        -- SEGUNDO: Eliminar los duplicados (ejecutar solo después de verificar)
        WITH CTE_Duplicados AS (
            SELECT 
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY work_order, estado_general 
                    ORDER BY fecha_actualizacion DESC
                ) AS RowNum
            FROM 
                fija_data_toa
            WHERE 
                fuente = 'TOA'
        )
        DELETE FROM CTE_Duplicados
        WHERE RowNum > 1;
                

                """)
        df = pd.read_sql(check_query, conn)
        # Pasar el df a Excel
        print("✅ Tabla limpiada correctamente")
if __name__ == '__main__':
    modificar_cancelados()
    ver_tabla()   
    # eliminar_tabla()