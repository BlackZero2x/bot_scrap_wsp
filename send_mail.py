import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
from dotenv import load_dotenv

load_dotenv()

def enviar_correo(remitente, contrasena_app, destinatario, asunto, cuerpo, archivos_adjuntos=None):
    """
    Función para enviar correos a través de Gmail
    
    Parámetros:
    remitente (str): Dirección de correo de Gmail del remitente
    contrasena_app (str): Contraseña de aplicación generada en la cuenta de Google
    destinatario (str): Dirección de correo del destinatario
    asunto (str): Asunto del correo
    cuerpo (str): Contenido del correo (puede ser HTML)
    archivos_adjuntos (list): Lista opcional de rutas de archivos para adjuntar
    """
    # Crear mensaje
    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    mensaje['To'] = destinatario
    mensaje['Subject'] = asunto
    
    # Agregar cuerpo del mensaje
    mensaje.attach(MIMEText(cuerpo, 'html'))
    
    
    try:
        # Conectar al servidor SMTP de Gmail
        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()  # Activar conexión segura
        
        # Iniciar sesión
        servidor.login(remitente, contrasena_app)
        
        # Enviar correo
        texto = mensaje.as_string()
        servidor.sendmail(remitente, destinatario, texto)
        
        # Cerrar conexión
        servidor.quit()
        
        print("¡Correo enviado con éxito!")
        return True
    
    except Exception as e:
        print(f"Error al enviar correo: {e}")
        return False

# Ejemplo de uso
if __name__ == "__main__":
    # Datos del remitente (tu cuenta de Gmail), vía .env — ver config.py
    # IMPORTANTE: Usar contraseña de aplicación, no la contraseña normal de la cuenta
    # Debes generarla en https://myaccount.google.com/security > Contraseñas de aplicaciones
    mi_correo = os.environ["GMAIL_REMITENTE"]
    mi_contrasena_app = os.environ["GMAIL_APP_PASSWORD"]

    # Datos del destinatario
    correo_destino = os.getenv("GMAIL_DESTINATARIO", mi_correo)
    
    # Datos del mensaje
    asunto_correo = "Bot TOA"
    
    # Puedes usar HTML para dar formato al cuerpo del correo
    cuerpo_correo = """
    <html>
        <body>
            <h1> Hola </h1>
        </body>
    </html>
    """
    
    
    # Enviar correo
    enviar_correo(mi_correo, mi_contrasena_app, correo_destino, asunto_correo, cuerpo_correo)