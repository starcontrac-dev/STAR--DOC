
import os
import json
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
import logging

# --- Configuración de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Funciones Principales ---
def get_database_url():
    """Carga la URL de la base de datos desde las variables de entorno."""
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("La variable de entorno DATABASE_URL no está configurada.")
    return db_url

def read_users_from_json(file_path):
    """Lee los datos de los usuarios desde un archivo JSON."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"El archivo JSON no fue encontrado en: {file_path}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Error al decodificar el archivo JSON: {file_path}")
        return None

def migrate_users_to_postgres():
    """
    Migra los usuarios desde un archivo JSON a la base de datos PostgreSQL.
    """
    db_url = get_database_url()
    users_data = read_users_from_json('users.json')

    if not users_data:
        logging.info("No hay datos de usuarios para migrar.")
        return

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        logging.info("Conexión a la base de datos PostgreSQL establecida.")

        migrated_count = 0
        skipped_count = 0

        for username, user_details in users_data.items():
            # Verificar si el usuario ya existe
            cur.execute("SELECT id FROM users WHERE username = %s;", (username,))
            if cur.fetchone():
                logging.warning(f"El usuario '{username}' ya existe en la base de datos. Saltando...")
                skipped_count += 1
                continue

            # Insertar nuevo usuario
            # El campo 'id' es SERIAL y se autoincrementa.
            # El campo 'oauth_state' no está en el JSON, se dejará como NULL.
            cur.execute(
                """
                INSERT INTO users (username, email, full_name, hashed_password, disabled, google_credentials, is_verified, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    user_details.get('username'),
                    user_details.get('email'),
                    user_details.get('full_name'),
                    user_details.get('hashed_password'),
                    user_details.get('disabled', False),
                    Json(user_details.get('google_credentials')) if user_details.get('google_credentials') else None,
                    True, # is_verified
                    'user' # role
                )
            )
            logging.info(f"Usuario '{username}' migrado exitosamente.")
            migrated_count += 1

        conn.commit()
        logging.info("Transacción completada. Todos los cambios han sido guardados.")

    except psycopg2.Error as e:
        logging.error(f"Error de base de datos: {e}")
        if conn:
            conn.rollback()
            logging.info("Rollback realizado. No se guardaron cambios en la base de datos.")
    finally:
        if conn:
            cur.close()
            conn.close()
            logging.info("Conexión a la base de datos cerrada.")
        
        logging.info("--- Resumen de la Migración ---")
        logging.info(f"Usuarios migrados: {migrated_count}")
        logging.info(f"Usuarios omitidos (ya existían): {skipped_count}")
        logging.info("---------------------------------")


if __name__ == "__main__":
    logging.info("Iniciando el script de migración de usuarios...")
    migrate_users_to_postgres()
    logging.info("Script de migración finalizado.")
