import pyodbc
import csv
from datetime import datetime
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import TOA_SERVER, TOA_DB, TOA_USER, TOA_PASSWORD, TOA_DRIVER

def parse_and_export(csv_path):
    conn_str = f'DRIVER={{{TOA_DRIVER}}};SERVER={TOA_SERVER};DATABASE={TOA_DB};UID={TOA_USER};PWD={TOA_PASSWORD}'
    conn = pyodbc.connect(conn_str)
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # 2. RUTA DEL CSV
    ruta_csv = csv_path  # Reemplaza con la ruta real
    # 1. LEER EL CSV CON DELIMITADOR ,
    df = pd.read_csv(
        ruta_csv,
        delimiter=",",
        engine="python",  # Necesario para delimitadores complejos
        quoting=csv.QUOTE_ALL,
        escapechar="\\"
    )

    # 2. CONVERTIR CAMPOS DE FECHA AL FORMATO SQL SERVER
    def convertir_fecha(columna, formato_entrada):
        """Convierte una columna de fechas al formato YYYY-MM-DD HH:MM:SS"""
        return pd.to_datetime(df[columna], format=formato_entrada, errors="coerce")

    # Fecha_cita: de DD/MM/YY a YYYY-MM-DD
    df["fecha_cita"] = pd.to_datetime(df["fecha_cita"], format="%d/%m/%y", errors="coerce").dt.strftime("%Y-%m-%d")

    # Hora_envio_mensaje_whatsapp: de DD/MM/YYYY HH:MM:SS a YYYY-MM-DD HH:MM:SS
    df["hora_envio_mensaje_whatsapp"] = pd.to_datetime(
        df["hora_envio_mensaje_whatsapp"], 
        format="%d/%m/%Y %H:%M:%S", 
        errors="coerce"
    ).dt.strftime("%Y-%m-%d %H:%M:%S")

    # Hora_respuesta_mensaje_whatsapp: puede tener formato DD/MM/YYYY o DD/MM/YYYY HH:MM:SS
    df["hora_respuesta_mensaje_whatsapp"] = pd.to_datetime(
        df["hora_respuesta_mensaje_whatsapp"], 
        dayfirst=True, 
        errors="coerce"
    ).dt.strftime("%Y-%m-%d %H:%M:%S")

    # 3. GUARDAR CAMBIOS EN EL MISMO ARCHIVO
    df.to_csv(
        ruta_csv,
        sep=",",
        index=False,
        quoting=csv.QUOTE_ALL,
        escapechar="\\"
    )
    # 3. FUNCIONES DE APOYO
    def parse_fecha(fecha_str):
        """Convierte una fecha a formato SQL Server DATETIME"""
        if not fecha_str or fecha_str.strip() in ('', '-', 'None', 'NULL'):
            return None
        formatos = [
            "%d/%m/%y",           # Ej: 30/04/25
            "%Y-%m-%d",           # Ej: 2025-04-30
            "%Y-%m-%d %H:%M:%S",  # Ej: 2025-04-30 18:30:00
            "%d/%m/%Y",           # Ej: 30/04/2025
            "%m/%d/%Y",           # Ej: 04/30/2025
            "%m/%d/%y"            # Ej: 04/30/25
        ]
        for fmt in formatos:
            try:
                return datetime.strptime(fecha_str.strip(), fmt)
            except ValueError:
                continue
        print(f"⚠️ Fecha inválida: {fecha_str}")
        return None

    def limpiar_valor(valor):
        """Limpia valores vacíos o nulos"""
        valor = valor.strip('"').strip()
        return None if valor.lower() in ('', 'nan', 'none', 'null') else valor

    # 4. LEER EL CSV Y PROCESAR FILAS
    try:
        with open(ruta_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=',', quotechar='"', escapechar='\\', quoting=csv.QUOTE_ALL)
            lineas = list(reader)
        
        # Extraer encabezados y validar número de columnas
        encabezados = [limpiar_valor(col) for col in lineas[0]]
        num_columnas = len(encabezados)
        print(f"🔢 Número esperado de columnas: {num_columnas}")
        
        # Preparar consulta de inserción
        columnas_sql = ', '.join(encabezados)
        placeholders = ', '.join(['?'] * num_columnas)
        query_insert = f"INSERT INTO fija_data_toa ({columnas_sql}) VALUES ({placeholders})"
        
        # Campos de fecha/hora que deben convertirse a DATETIME
        campos_fecha = {
            'fecha_cita': "%d/%m/%y",
            'hora_envio_mensaje_whatsapp': "%Y-%m-%d %H:%M:%S",
            'hora_respuesta_mensaje_whatsapp': "%Y-%m-%d %H:%M:%S",
            'fecha_actualizacion': "%Y-%m-%d %H:%M:%S"
        }

        # Procesar cada fila
        for i, fila in enumerate(lineas[1:], start=2):
            try:
                # Validar y corregir número de columnas
                if len(fila) < num_columnas:
                    print(f"⚠️ Fila {i} incompleta: {len(fila)} campos de {num_columnas}")
                    fila += [None] * (num_columnas - len(fila))
                elif len(fila) > num_columnas:
                    print(f"⚠️ Fila {i} tiene más campos: {len(fila)}")
                    fila = fila[:num_columnas-1] + ['¬'.join(fila[num_columnas-1:])]

                # Limpiar y convertir valores
                fila = [limpiar_valor(val) for val in fila]
                
                # Convertir campos de fecha/hora
                for campo_fecha, fmt in campos_fecha.items():
                    if campo_fecha in encabezados:
                        idx = encabezados.index(campo_fecha)
                        if fila[idx]:
                            fila[idx] = parse_fecha(fila[idx])

                # Ejecutar inserción
                cursor.execute(query_insert, fila)
                
                conn.commit()
            
            except Exception as e:
                print(f"❌ Error en fila {i}: {str(e)}")
                print("Fila:", fila)
                conn.rollback()
                continue

        # Confirmar cambios restantes
        conn.commit()
        print("✅ Inserción completada exitosamente. Archivo procesado: ", csv_path)

    except Exception as e:
        print("❌ Error general:", str(e))
        conn.rollback()

    finally:
        cursor.close()
        conn.close()

if __name__=='__main__':
    parse_and_export("extracciones/2025-05-02-11-40-39.csv")