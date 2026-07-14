import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv, set_key

# Scopes para Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    print("Iniciando flujo de autenticación de Google...")
    # Usar credenciales de desktop
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials_calendar.json', SCOPES
    )
    
    # Esto abrirá el navegador en la PC del usuario en el puerto 8085
    creds = flow.run_local_server(port=8085)
    
    # Extraer el Refresh Token
    refresh_token = creds.refresh_token
    client_id = creds.client_id
    client_secret = creds.client_secret
    
    print("\n¡Autenticación exitosa!")
    print(f"Refresh Token obtenido: {refresh_token}")
    
    # Actualizar .env
    env_file = '.env'
    if os.path.exists(env_file):
        set_key(env_file, 'GOOGLE_CLIENT_ID', client_id)
        set_key(env_file, 'GOOGLE_CLIENT_SECRET', client_secret)
        if refresh_token:
            set_key(env_file, 'GOOGLE_REFRESH_TOKEN', refresh_token)
        print("\nArchivo .env actualizado exitosamente con las nuevas credenciales.")
    else:
        print("\nNo se encontró archivo .env")

if __name__ == '__main__':
    main()
