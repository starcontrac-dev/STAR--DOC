"""
Script de autenticación OAuth2 para Google Calendar.
Genera el REFRESH_TOKEN y lo guarda automáticamente en el .env.
Usa credenciales tipo 'installed' para evitar errores de redirect_uri.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Archivo de credenciales tipo "Desktop App" descargado de Google Cloud Console
CLIENT_SECRETS_FILE = "client_secret_55.json"
SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"❌ Error: No se encontró el archivo {CLIENT_SECRETS_FILE}")
        return

    print("🚀 Iniciando flujo de autenticación de Google Calendar...")
    print("📌 Se abrirá tu navegador para autorizar la aplicación.")
    print("   Usa la cuenta: starcontrac@gmail.com\n")
    
    try:
        # Crear el flujo OAuth2 desde las credenciales
        flow = InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, SCOPES)
        
        # Puerto fijo para el servidor local de callback
        creds = flow.run_local_server(port=8080)

        if not creds.refresh_token:
            print("⚠️  No se obtuvo refresh_token. Esto puede pasar si ya autorizaste antes.")
            print("    Solución: Ve a https://myaccount.google.com/permissions")
            print("    Elimina el acceso de la app y vuelve a ejecutar este script.")
            return

        print("\n✅ ======== AUTENTICACIÓN EXITOSA ========")
        print(f"   Refresh Token: {creds.refresh_token[:20]}...") 
        
        # Guardar automáticamente en .env
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
                
            updated = False
            with open(env_path, "w") as f:
                for line in lines:
                    if line.strip().startswith("GOOGLE_REFRESH_TOKEN="):
                        f.write(f'GOOGLE_REFRESH_TOKEN="{creds.refresh_token}"\n')
                        updated = True
                    else:
                        f.write(line)
                        
            if not updated:
                # Si no existía la línea, la añadimos
                with open(env_path, "a") as f:
                    f.write(f'\nGOOGLE_REFRESH_TOKEN="{creds.refresh_token}"\n')
                    
            print(f"\n📝 Archivo .env actualizado automáticamente en:")
            print(f"   {env_path}")
            print("\n🎉 ¡Configuración completada! Ya puedes usar Google Calendar en STAR-DOC.")
            
        except Exception as e:
            print(f"\n⚠️  No se pudo actualizar el .env automáticamente: {e}")
            print(f"\n   Copia este valor manualmente en tu .env:")
            print(f'   GOOGLE_REFRESH_TOKEN="{creds.refresh_token}"')
            
    except Exception as e:
        print(f"❌ Error en la autenticación: {e}")

if __name__ == '__main__':
    main()
