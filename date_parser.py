import pandas as pd
def handler_data(data):
    df = pd.DataFrame([data])
    df = df.astype(str)
    # Fecha_cita: de DD/MM/YY a YYYY-MM-DD
    df["fecha_cita"] = pd.to_datetime(df["fecha_cita"], format="%d/%m/%y", errors="coerce").dt.strftime("%d-%m-%Y")

    # Hora_envio_mensaje_whatsapp: de DD/MM/YYYY HH:MM:SS a YYYY-MM-DD HH:MM:SS
    df["hora_envio_mensaje_whatsapp"] = pd.to_datetime(
        df["hora_envio_mensaje_whatsapp"], 
        format="%d/%m/%Y %H:%M:%S", 
        errors="coerce"
    ).dt.strftime("%d/%m/%Y %H:%M:%S")

    # Hora_respuesta_mensaje_whatsapp: puede tener formato DD/MM/YYYY o DD/MM/YYYY HH:MM:SS
    df["hora_respuesta_mensaje_whatsapp"] = pd.to_datetime(
        df["hora_respuesta_mensaje_whatsapp"], 
        format="%d/%m/%Y %H:%M:%S", 
        errors="coerce"
    ).dt.strftime("%d/%m/%Y %H:%M:%S")
       # Reemplazar cualquier 'None' (str) por None (NoneType) en todo el DataFrame
    df = df.replace("None", None)
    return df
    