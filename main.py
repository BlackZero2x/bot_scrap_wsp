import time
from datetime import datetime
from scrapper import init_bot
def mi_funcion():
    print(f"[{datetime.now()}] Ejecutando función...")

def esta_dentro_del_horario():
    ahora = datetime.now().time()
    # Rango mañana
    if datetime.strptime("08:00", "%H:%M").time() <= ahora < datetime.strptime("13:00", "%H:%M").time():
        return True
    # Rango tarde
    if datetime.strptime("14:00", "%H:%M").time() <= ahora < datetime.strptime("19:30", "%H:%M").time():
        return True
    return False

while True:
    ahora = datetime.now().time()

    # Salir si pasa de las 7:30 PM
    if ahora >= datetime.strptime("19:30", "%H:%M").time():
        print(f"[{datetime.now()}] Fuera del horario final. Cerrando script.")
        break

    if esta_dentro_del_horario():
        
        max_intentos = 3
        for intento in range(1, max_intentos + 1):
            try:
                print(f"Intento {intento}")


                print("¡Función ejecutada con éxito!")
                break  # Si funciona, salimos del bucle
            except Exception as e:
                print(f"Error en intento {intento}: {e}")
                time.sleep(600)
                if intento == max_intentos:
                    # Enviar alerta!
                    print("Se alcanzó el número máximo de intentos. Abortando...")
    else:
        print(f"[{datetime.now()}] Pausa programada. Esperando reanudación...")

    time.sleep(60)  # Ejecuta cada minuto (ajustable)
