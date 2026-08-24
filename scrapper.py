from selenium.webdriver import Chrome
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
import csv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from pathlib import Path
import os
from selenium.webdriver.chrome.service import Service as ChromeService
from typing import Optional
import pyodbc
from scripts_db.fe_consultar import obtener_codigo_fe_por_rango
from scripts_db.fe_consultar import engine as engine_auren
import glob
from scripts_db.data_extraida import ver_fe_procesado, ver_fe_filtrado, clean_table
from dateutil.relativedelta import relativedelta
from migracion_masiva import parse_and_export
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

from date_parser import handler_data
from query_fe_filter import filter_query
from config import engine_toa, TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD
# Desactivar el proxy para ciertos dominios
no_proxy_domains = [
    'chromedriver.storage.googleapis.com',
    'telefonica-pe.etadirect.com',
]
os.environ['NO_PROXY'] = ','.join(no_proxy_domains)
os.environ['no_proxy'] = ','.join(no_proxy_domains) # Por compatibilidad

# Si tienes definido un proxy, también puedes limpiarlo así:
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('https_proxy', None)
os.environ.pop('http_proxy', None)

for var in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'ALL_PROXY']:
    os.environ.pop(var, None)



class BotTOA:
    def __init__(self, username, password):
        self.chrome_install = ChromeDriverManager().install()
        self.folder = os.path.dirname(self.chrome_install)
        self.chromedriver_path = os.path.join(self.folder, "chromedriver.exe")
        self.service = ChromeService(self.chromedriver_path)

        self.option = webdriver.ChromeOptions()
        self.option.add_argument("--window-size=1920,1080")
        self.option.add_argument("--headless")

        # self.option.add_argument('--no-proxy-server')
        proxy = None
        # self.option.add_argument(f'--proxy-server= {proxy}')
        # self.option.add_argument('--proxy-bypass-list=*')
        # self.option.add_argument('--proxy-server="direct://"')
        # self.option.add_argument('--disable-gpu')
        # self.option.add_argument('--disable-dev-shm-usage')
        self.option.add_argument('--no-sandbox')
        self.option.add_argument('--ignore-certificate-errors')
        self.option.add_argument('--ignore-ssl-errors')
        
        # Bloquear notificaciones de sitios web
        self.option.add_argument("--disable-notifications")

        # Bloquear solicitudes de permisos emergentes
        self.option.add_experimental_option(
            "prefs",
            {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_setting_values.media_stream": 2,
                "profile.default_content_setting_values.geolocation": 2,
                "profile.default_content_setting_values.popups": 2,
            },
        )

        # Configuraciones adicionales para un comportamiento más limpio
        self.option.add_argument("--no-sandbox")
        self.option.add_argument("--disable-dev-shm-usage")

        # Init serv
        self.driver = Chrome(service=self.service, options=self.option)
        # Esperar hasta que el elemento esté presente en el DOM
        self.wait = WebDriverWait(self.driver, 30)

        self.username = username
        self.password = password
        
        # Initialize DataFrame to store results
        self.df_resultados = None

    def login(self):
        self.driver.get("https://telefonica-pe.etadirect.com/")

        # Looking for login and click
        input_username = self.wait.until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        input_username.click()
        input_username.send_keys(self.username)

        input_password = self.wait.until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        input_password.click()
        input_password.send_keys(self.password)

        btn_login = self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "/html/body/div/div/div/div/form/div[2]/div[5]/button/div")
            )
        ).click()


        # Suprimir otras sesiones abiertas
        try:
            btn_detele_sessions = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "/html/body/div/div/div/div/form/div[2]/div[4]/div[1]/div[1]/span/span/input",
                    )
                )
            )
            btn_detele_sessions.click()

            input_password = self.wait.until(
                EC.presence_of_element_located((By.ID, "password"))
            )
            input_password.click()
            input_password.send_keys(self.password)
            btn_login = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "/html/body/div/div/div/div/form/div[2]/div[6]/button/div",
                    )
                )
            )
            btn_login.click()
        except:
            print("No hay otras sesiones; continuando...")


    def findFE(self, fe):
        from selenium.webdriver.common.action_chains import ActionChains

        search_field_selector = "input[placeholder='Buscar en actividades']"

        self.wait = WebDriverWait(self.driver, 30)
        # Limpiar campo de búsqueda y escribir el código
        search_field = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, search_field_selector))
        )

        actions = ActionChains(self.driver)
        actions.click(search_field)
        # actions.pause(0.1)
        for char in fe:
            actions.send_keys(char)
        actions.perform()
        time.sleep(5)
        try:
            fe_div = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//div[@aria-label="activity result item"]',
                    )
                )
            )
            # print("Elemento encontrado:", fe_div.text)
            self.fe = fe_div.text
            fe_div.click()
            time.sleep(3)
            # print("Se clickeo al FE")
            return True
        except:
            # Limpiar campo de búsqueda si no se encuentra
            actions = ActionChains(self.driver)
            actions.click(search_field)
            for _ in fe:
                actions.send_keys(Keys.BACK_SPACE).pause(0.1)
            actions.perform()
            print(f"Elemento no encontrado, {fe}")
            return False

    def scrapping_information(self, dni=None):
        # Definir todos los campos que queremos extraer con sus IDs
        dict_info_cod ={
            "indicador_brigada": "12",
            "work_order": "288",
            "codigo_cliente": "17",
            "nombre_cliente": "18",
            "tipo_documento": "19",
            "documento_identidad": "20",
            "empresa_bucket": "21",
            "ofertas_productos_servicios": "23",
            "dato_direccion": "33",
            "nombre_departamento": "38",
            "intervalo_tiempo": "880",
            "fecha_cita": "305",
            "respuesta_whatsapp_botmaker": "415",
            "hora_envio_mensaje_whatsapp": "417",
            "hora_respuesta_mensaje_whatsapp": "420",
            "numero_whatsapp_telefonica": "423",
            "usuario_agendamiento": "427",
            "fecha_agendamiento": "428",
            "franja_agendamiento": "429",
            "coordenada_tecnico_preform": "452",
            "persona_contacto_cierre": "528",
            "nombre_persona_recibe": "466",
            "dni_persona_recibe": "467",
            "motivo_liquidacion_instalacion": "500",
            "direccion_incorrecta": "476",
            "observaciones_cierre": "542",
            "codigos_cancelado": "",  # Falta
            "codigo_no_realizado_tecnicos": "",  # Falta
            "tipo_devolucion_instalaciones": "",  # Falta
            "motivo_no_realizado_instalacion": "514",
            "franja_postergacion": ""  # Falta
        }


        # Campos con selectores especiales
        special_selectors = {
                "numero_telefono": "[aria-describedby='index_34']",
                "observacion_datos_cita_legados": "[aria-describedby='index_310']",
                "observacion_datos_cita_toa": "[aria-describedby='index_311']",
                "descripcion_general": "div.page-header-description--text[data-ofsc-role='page-description-text']"
        }

        # Combinar todas las claves en una única lista para mantener el orden
        all_keys = list(dict_info_cod.keys()) + list(special_selectors.keys())
        resultado = {}
        
        # Establecer un tiempo de espera más corto para las búsquedas
        short_wait = WebDriverWait(self.driver, 0.3)
        
        # Extraer datos basados en IDs
        for key, value in dict_info_cod.items():
            try:
                if value:  # Si hay un ID válido
                    data = short_wait.until(
                        EC.presence_of_element_located((By.ID, f"id_index_{value}"))
                    )
                    resultado[key] = str(data.text)
                else:
                    resultado[key] = None  # Para campos sin ID
            except:
                resultado[key] = None
        
        # Extraer datos basados en selectores especiales
        for key, selector in special_selectors.items():
            try:
                data = short_wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                resultado[key] = str(data.text)
            except:
                resultado[key] = None
                
        # Campos adicionales
        # Agregar el campo "fuente" con valor "TOA"
        resultado["estado_general"]= self.fe.split(" - ")[2]
        resultado["fuente"] = "TOA"
        
        # Obtener la fecha y hora actual
        fecha_actual = datetime.now()

        # Formatear como string (día y hora)
        fecha_formateada = fecha_actual.strftime("%d/%m/%Y %H:%M:%S")
        
        resultado["fecha_actualizacion"] = fecha_formateada
        resultado["dni_vendedor"]= str(dni)
        
        fecha_ult_tratamiento = resultado["descripcion_general"]
        fecha_ult = fecha_ult_tratamiento.split(",")[1].strip()
        fecha_obj = datetime.strptime(fecha_ult, "%d/%m/%y")
        # Formatear a año de cuatro dígitos
        fecha_larga = fecha_obj.strftime("%d/%m/%Y")
        resultado["fecha_ult_tratamiento"] = fecha_larga
        
        # Actualizar la lista de todas las claves para incluir "fuente"
        all_keys.append("estado_general")
        all_keys.append("fuente")
        all_keys.append("fecha_actualizacion")
        all_keys.append("dni_vendedor")
        all_keys.append("fecha_ult_tratamiento")
        print("FECHA ULT", resultado["fecha_ult_tratamiento"])
        return resultado, all_keys

    def guardar_datos_en_csv(self, datos_extraidos, keys, carpeta, nombre_archivo):
        # Si es la primera iteración, crear un DataFrame con las columnas predefinidas
        if self.df_resultados is None:
            self.df_resultados = pd.DataFrame(columns=keys)
        
        # Crear un diccionario con los valores extraídos, manteniendo el orden de las columnas
        fila_datos = {}
        for key in keys:
            fila_datos[key] = datos_extraidos.get(key, "No hallado")
        
        # Convertir la columna al formato deseado
        # fila_datos["fecha_cita"] = pd.to_datetime(fila_datos["fecha_cita"], format="%d/%m/%y", errors="coerce").dt.strftime("%Y-%m-%d")
        # fila_datos["hora_envio_mensaje_whatsapp"] = pd.to_datetime(fila_datos["hora_envio_mensaje_whatsapp"], format="%d/%m/%Y %H:%M:%S", errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        # fila_datos["hora_respuesta_mensaje_whatsapp"] = pd.to_datetime(fila_datos["hora_respuesta_mensaje_whatsapp"], format="%d/%m/%Y ", errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
              
        # Agregar la fila al DataFrame
        nueva_fila = pd.DataFrame([fila_datos])
        self.df_resultados = pd.concat([self.df_resultados, nueva_fila], ignore_index=True)
        # Guardar el DataFrame completo en CSV
        carpeta = carpeta
        ruta_completa = os.path.join(carpeta, nombre_archivo)
        self.df_resultados.to_csv(ruta_completa, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")
        
        return self.df_resultados

    def save_to_database(self, df):
        try:
            df.to_sql(
                name="fija_data_toa",
                con=engine_toa(),
                schema="dbo",
                if_exists="append",
                index=False
            )
            print("🤖 datos exportados correctamente")
        except Exception as e:
            print(e)
            
def create_csv(archivo_csv):
    carpeta = 'extracciones/'
    archivo = archivo_csv
    ruta_completa = os.path.join(carpeta, archivo)

    # Crear carpeta si no existe
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)
        print(f"Carpeta creada: {carpeta}")

    # Crear archivo vacío si no existe
    if not os.path.exists(ruta_completa):
        with open(ruta_completa, 'w', encoding='utf-8') as f:
            pass  # crea el archivo en blanco
        print(f"Archivo CSV creado en blanco: {ruta_completa}")
    else:
        print(f"El archivo ya existe: {ruta_completa}")
    return carpeta, ruta_completa


def filtro_fe(engine, fecha_inicio, fecha_fin):
    # Leer el archivo CSV y crear un DataFrame
    # Reemplaza 'archivo.csv' con la ruta de tu archivo
    
    query_fe = obtener_codigo_fe_por_rango(engine, fecha_inicio, fecha_fin)
    
    fe_procesados = ver_fe_procesado()
    fe_procesados = fe_procesados.rename(columns={"work_order": "codigo_fe"})
    
    fe_en_proceso = ver_fe_filtrado()
    fe_en_proceso= fe_en_proceso.rename(columns={"work_order": "codigo_fe"})
    # FE- 123, "18-12-2025, 72698745"
    
    fe_pendientes = query_fe[~query_fe['codigo_fe'].isin(fe_procesados['codigo_fe'])]

    fe_pendientes_y_en_proceso = pd.concat([fe_pendientes, fe_en_proceso], ignore_index=True)

    lista_resultado = fe_pendientes_y_en_proceso[["codigo_fe", "dni_vendedor"]].values.tolist()
    
    return lista_resultado

def particionar_fe(lista_resultado):
    # Particionar datos en grupos de 1000
    tamaño_grupo = 300
    grupos = [
        lista_resultado[i:i + tamaño_grupo] 
        for i in range(0, len(lista_resultado), tamaño_grupo)
    ]
    return grupos

def start_bot():
    fe_filtered = filter_query()
    print("Total a extraer: ", len(fe_filtered))
    grupos = particionar_fe(fe_filtered)
    
    for grupo in grupos:
        ahora = datetime.now().time()
        if ahora >= datetime.strptime("06:30", "%H:%M").time() and ahora <= datetime.strptime("13:00", "%H:%M").time() or ahora >= datetime.strptime("14:00", "%H:%M").time() and ahora <= datetime.strptime("20:30", "%H:%M").time():
            try:
                bot_toa = BotTOA(TOA_PORTAL_USERNAME, TOA_PORTAL_PASSWORD)
                bot_toa.login()
                ahora = datetime.today()
                nombre_fecha = ahora.strftime("%Y-%m-%d-%H-%M-%S")
                CSV_NAME = f"{nombre_fecha}.csv"
                inicio_iteracion = time.time()
                try:
                    # Crecion de archivo
                    carpeta, ruta_completa = create_csv(CSV_NAME)
                    counter = 1
                    acierto = 0
                    errores = 0
                    arreglados= 0
                    for codigo_fe, dni_vendedor in grupo:
                        try:
                            if codigo_fe:
                                inicio = time.time()
                                if bot_toa.findFE(codigo_fe):
                                    data_extraida, keys = bot_toa.scrapping_information(dni=dni_vendedor)
                                    bot_toa.guardar_datos_en_csv(data_extraida, keys, carpeta,  CSV_NAME)
                                    fin = time.time()
                                    tiempo_total = fin - inicio
                                    
                                    df = handler_data(data_extraida)
                                    if codigo_fe in df["work_order"].values:
                                        acierto += 1
                                        print("Aciertos:", acierto)
                                    else:
                                        if df["work_order"][0].startswith("INS-"):
                                            df.loc[0, "work_order"] = df.loc[0, "work_order"].removeprefix("INS-")
                                            if df.loc[0, "work_order"] == codigo_fe:
                                                print("Se arreglo el ", df["work_order"][0])
                                                arreglados += 1
                                            else:
                                                print("Hubo un error")
                                                errores += 1
                                                print("Errores:", errores)
                                                continue
                                        else:
                                            print("Hubo un error")
                                            errores += 1
                                            print("Errores:", errores)
                                            continue        
                                    print("Elemento ", counter, "de ", len(grupo))
                                    print(f"Código FE: {codigo_fe}; vendedor: {dni_vendedor}")
                                    print("df a migrar: ", df["work_order"][0])
                                    
                                    bot_toa.save_to_database(df)
                                    print(f"Tiempo total para {codigo_fe}: {tiempo_total:.2f} segundos")
                                else:
                                    print(f"No se pudo encontrar {codigo_fe}")
                            else:
                                print("No se encontro:", codigo_fe)
                            counter += 1
                            print("Errores: ", errores," // ","Aciertos: ", acierto, " // ","Arreglados: ", arreglados )                                                
                        except:
                            print("Hubo un error sin manejar...")
                            continue    
                except Exception as e:
                    print(f"Error al buscar el FE o extraer datos: {e}")
                finally:
                    fin_iteracion = time.time()
                    tiempo_total_iteracion = fin_iteracion - inicio_iteracion
                    print(f"Tiempo total de iteración: {tiempo_total_iteracion:.2f} segundos")
                    bot_toa.driver.quit()
                    clean_table()
                    import random

                    tiempo_min = random.randint(600, 1000)
                    time.sleep(tiempo_min)
            except Exception as e:
                print(f"Error al iniciar el bot: {e}")
        else:
            if ahora <= datetime.strptime("20:00", "%H:%M").time():
                print("Fuera de horario")
                break
            else:
                time.sleep(3800)
                pass
if __name__ == '__main__':
    start_bot()