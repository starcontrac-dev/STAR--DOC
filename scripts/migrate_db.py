
import json
import psycopg2
import os

# ------------------- CONFIGURACIÓN -------------------
# Modifica estos valores para que coincidan con tu configuración de PostgreSQL en Windows
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "dbname": "stardoc",  # <-- CAMBIA ESTO
    "user": "postgres",         # <-- CAMBIA ESTO
    "password": "starcontract  89"   # <-- CAMBIA ESTO
}

# Nombre del archivo JSON que contiene los usuarios
JSON_FILE = 'users.json'
# -----------------------------------------------------


def migrate_users():
    """
    Lee los usuarios de un archivo JSON y los inserta en la base de datos PostgreSQL.
    """
    if not os.path.exists(JSON_FILE):
        print(f"Error: No se encontró el archivo '{JSON_FILE}'. Asegúrate de que esté en la misma carpeta que este script.")
        return

    conn = None
    try:
        # Conectar a la base de datos
        print("Conectando a la base de datos PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("Conexión exitosa.")

        # Cargar los datos del archivo JSON
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            users_data = json.load(f)

        print(f"Se encontraron {len(users_data)} usuarios en '{JSON_FILE}'. Iniciando migración...")

        # Iterar e insertar cada usuario
        for username, user_details in users_data.items():
            
            # Convertir el diccionario de credenciales de Google a un string JSON si existe
            # La base de datos lo almacenará en una columna de tipo JSONB
            google_creds_json = None
            if user_details.get('google_credentials'):
                google_creds_json = json.dumps(user_details['google_credentials'])

            # Preparar la consulta SQL para insertar el usuario
            insert_query = """
                INSERT INTO users (username, full_name, email, hashed_password, disabled, google_credentials)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING;
            """
            
            user_tuple = (
                user_details.get('username'),
                user_details.get('full_name'),
                user_details.get('email'),
                user_details.get('hashed_password'),
                user_details.get('disabled', False),
                google_creds_json
            )
            
            cur.execute(insert_query, user_tuple)
            print(f" - Procesando usuario: {username}")

        # Confirmar los cambios en la base de datos
        conn.commit()
        print("\n¡Migración completada exitosamente!")
        print("Todos los usuarios han sido insertados en la base de datos.")

    except psycopg2.Error as e:
        print(f"\nError de base de datos: {e}")
        if conn:
            conn.rollback() # Revertir cambios en caso de error
    except Exception as e:
        print(f"\nOcurrió un error inesperado: {e}")
    finally:
        # Cerrar la conexión
        if conn:
            cur.close()
            conn.close()
            print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    migrate_users()
