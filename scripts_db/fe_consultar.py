# Conexión a la base de datos
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
import pyodbc
import pandas as pd
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys
from pathlib import Path

# Importar configuración centralizada
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import engine_auren

engine = engine_auren()

def obtener_codigo_fe_por_rango(engine, 
                               fecha_inicio=datetime.now() - relativedelta(months=2), 
                               fecha_fin=datetime.now()):
    if isinstance(fecha_inicio, str):
        fecha_inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
    if isinstance(fecha_fin, str):
        fecha_fin = datetime.strptime(fecha_fin, "%Y-%m-%d")

    query = text("""
        SELECT codigo_fe, dni_vendedor
        FROM dbo.fija_controlnet_detallado
        WHERE fecha >= :fecha_inicio
          AND fecha < DATEADD(DAY, 1, :fecha_fin)
          AND codigo_fe IS NOT NULL
        ORDER BY fecha ASC;
    """)

    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin})
            rows = result.fetchall()

        df = pd.DataFrame(rows, columns=["codigo_fe", "dni_vendedor"])
        return df
    except Exception as e:
        print(f"Error ejecutando consulta: {str(e)}")
        return pd.DataFrame()

def obtener_valores_codigo_fe(engine):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT codigo_fe
            FROM dbo.fija_controlnet_detallado;
        """))
        rows = result.fetchall()

    # Convertir a DataFrame
    df = pd.DataFrame(rows, columns=["codigo_fe"])
    return df
def obtener_codigo_fe_df(engine):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_controlnet_detallado';
        """))
        columns = result.fetchall()

    # Convertir a DataFrame
    df = pd.DataFrame(columns, columns=["COLUMN_NAME", "DATA_TYPE", "CHARACTER_MAXIMUM_LENGTH"])
    
    # Filtrar por la columna 'codigo_fe'
    df_filtrado = df[df["COLUMN_NAME"] == "codigo_fe"]

    return df_filtrado

def crear_tablas():
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
            CREATE TABLE dbo.fija_data_toa (
                indicador_brigada NVARCHAR(255),
                work_order NVARCHAR(255),
                codigo_cliente NVARCHAR(255),
                nombre_cliente NVARCHAR(255),
                tipo_documento NVARCHAR(100),
                documento_identidad NVARCHAR(100),
                empresa_bucket NVARCHAR(255),
                ofertas_productos_servicios NVARCHAR(255),
                dato_direccion NVARCHAR(255),
                nombre_departamento NVARCHAR(100),
                intervalo_tiempo NVARCHAR(100),
                fecha_cita VARCHAR(50),
                respuesta_whatsapp_botmaker NVARCHAR(255),
                hora_envio_mensaje_whatsapp VARCHAR(50),
                hora_respuesta_mensaje_whatsapp VARCHAR(50),
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
                fecha_actualizacion VARCHAR(50),
                fuente NVARCHAR(100)
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

def ver_tablas():
    try:
        with engine.connect() as conn:
            result = conn.execute(text(""" 
                SELECT TABLE_SCHEMA, TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """))
            tablas = result.fetchall()
            if tablas:
                print(f"📋 Se encontraron {len(tablas)} tablas:")
                for row in tablas:
                    print(f"  • {row.TABLE_SCHEMA}.{row.TABLE_NAME}")
            else:
                print("❌ No se encontraron tablas.")
    except Exception as e:
        print(f"❌ Error al listar tablas: {str(e)}")

def ver_permisos():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT permission_name, state_desc
                FROM sys.database_permissions
                WHERE grantee_principal_id = USER_ID()
                ORDER BY permission_name;
            """))
            permisos = result.fetchall()
            if permisos:
                print(f"🔑 Permisos del usuario actual:")
                for perm in permisos:
                    print(f"  • {perm.permission_name}: {perm.state_desc}")
            else:
                print("⚠️ No se encontraron permisos específicos para el usuario.")
    except Exception as e:
        print(f"❌ Error al consultar permisos: {str(e)}")

def probar_conexion_directa():
    try:
        conn_str = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"✅ Conexión directa exitosa. Versión del servidor: {version}")
        conn.close()
    except Exception as e:
        print(f"❌ Error en conexión directa: {str(e)}")

def ver_columnas():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_controlnet_detallado';
        """))
        columns = result.fetchall()
    for col in columns:
        print(col)
def eliminar_tabla():
    """
    Elimina la tabla fija_data_toa si existe en la base de datos.
    """
    try:
        with engine.begin() as conn:  # Usar begin() para manejar transacciones automáticamente
            # Verificar si la tabla existe antes de intentar eliminarla
            check_query = text("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_data_toa'
            """)
            result = conn.execute(check_query)
            table_exists = result.fetchone()
            
            if table_exists:
                print("🔍 Tabla fija_data_toa encontrada. Procediendo a eliminarla...")
                drop_query = text("DROP TABLE dbo.fija_data_toa;")
                conn.execute(drop_query)
                
                # Verificar que la tabla se haya eliminado correctamente
                verify_query = text("""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_data_toa'
                """)
                result = conn.execute(verify_query)
                if not result.fetchone():
                    print("✅ Tabla fija_data_toa eliminada correctamente.")
                else:
                    print("❌ Error: La tabla sigue existiendo después del intento de eliminación.")
            else:
                print("ℹ️ La tabla fija_data_toa no existe, no es necesario eliminarla.")
                
    except Exception as e:
        print(f"❌ Error al eliminar la tabla: {str(e)}")

def ver_datos_tabla(limit=100):
    """
    Muestra los datos de la tabla fija_data_toa.
    
    Args:
        limit (int): Número máximo de filas a mostrar. Por defecto 100.
    
    Returns:
        DataFrame: Un DataFrame de pandas con los datos de la tabla.
    """
    try:
        import pandas as pd
        
        with engine.connect() as conn:
            # Verificar si la tabla existe antes de intentar consultarla
            check_query = text("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'fija_data_toa'
            """)
            result = conn.execute(check_query)
            table_exists = result.fetchone()
            
            if not table_exists:
                print("❌ La tabla fija_data_toa no existe en la base de datos.")
                return None
            
            # Consultar los datos de la tabla con un límite
            query = text(f"SELECT TOP {limit} * FROM dbo.fija_data_toa")
            
            # Alternativa para obtener el total de registros primero
            count_query = text("SELECT COUNT(*) FROM dbo.fija_data_toa")
            count_result = conn.execute(count_query).scalar()
            
            # Ejecutar la consulta principal
            result = conn.execute(query)
            
            # Convertir el resultado a un DataFrame de pandas
            df = pd.DataFrame(result.fetchall())
            
            # Si hay resultados, asignar los nombres de las columnas
            if not df.empty:
                df.columns = result.keys()
            
            # Mostrar información sobre los resultados
            print(f"✅ Consulta completada. Total de registros en la tabla: {count_result}")
            print(f"ℹ️ Mostrando {min(limit, len(df))} de {count_result} registros.")
            
            return df
            
    except Exception as e:
        print(f"❌ Error al consultar los datos: {str(e)}")
        return None

def ver_datos_df():
    df = ver_datos_tabla(10)  # Ver solo 10 filas
    if df is not None:
        print(df)  # Mostrar el DataFrame
        # O para ver más información sobre los datos:
        print(df.info())
        print(df.describe())
if __name__ == '__main__':
    fecha_inicio = datetime.now() - relativedelta(months=2)
    data_filtrada = obtener_codigo_fe_por_rango(engine)
    print(data_filtrada)
    # crear_tablas()
    # eliminar_tabla()
    # ver_columnas()
    # print("🔍 Probando conexión directa...")
    # probar_conexion_directa()
    
    # print("\n🔍 Verificando permisos de usuario...")
    # ver_permisos()
    
    # print("\n🔍 Creando la tabla...")
    # crear_tablas()
    # ver_datos_df()
    
    # # Esperar un momento para asegurarse de que la transacción se complete
    # time.sleep(1)
    
    # print("\n🔍 Verificando todas las tablas...")
    # ver_tablas()