import asyncio
import sys
import os
import json
from datetime import datetime

# Añadir el directorio raíz al path para importar la app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text
from app.database import async_session_maker
from app.models.user import User

async def migrate_users():
    dump_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'planes', 'bases-datos', 'stardoc_dump.sql')
    
    users_to_insert = []
    
    print(f"Leyendo usuarios desde: {dump_path}")
    with open(dump_path, 'r', encoding='utf-16') as f:
        in_copy_block = False
        for line in f:
            if line.startswith('COPY public.users '):
                in_copy_block = True
                continue
            if in_copy_block:
                if line.strip() == '\\.':
                    break
                
                parts = line.strip('\n').split('\t')
                
                def parse_null(val):
                    return None if val == '\\N' else val
                
                def parse_bool(val):
                    return True if val == 't' else False
                
                try:
                    google_creds = json.loads(parts[6]) if parse_null(parts[6]) and parts[6] != 'null' else None
                except json.JSONDecodeError:
                    google_creds = None

                user_dict = {
                    'id': int(parts[0]),
                    'username': parts[1],
                    'email': parts[2],
                    'full_name': parts[3],
                    'hashed_password': parts[4],
                    'disabled': parse_bool(parts[5]),
                    'google_credentials': google_creds,
                    'oauth_state': parse_null(parts[7]),
                    'role': parts[8],
                    'is_verified': parse_bool(parts[9]),
                    'verification_token': parse_null(parts[10]),
                    'reset_password_token': parse_null(parts[11]),
                    'reset_token_expires': None
                }
                
                raw_expires = parse_null(parts[12])
                if raw_expires:
                    try:
                        user_dict['reset_token_expires'] = datetime.strptime(raw_expires, '%Y-%m-%d %H:%M:%S.%f')
                    except ValueError:
                        user_dict['reset_token_expires'] = datetime.strptime(raw_expires, '%Y-%m-%d %H:%M:%S')

                users_to_insert.append(user_dict)

    print(f"Se encontraron {len(users_to_insert)} usuarios en el dump.")

    async with async_session_maker() as session:
        # Obtener los IDs y usernames existentes para evitar colisiones
        res_existing = await session.execute(text("SELECT id, username FROM users;"))
        existing_rows = res_existing.fetchall()
        existing_ids = {row[0] for row in existing_rows}
        existing_usernames = {row[1] for row in existing_rows}
        
        inserted_count = 0
        for u_data in users_to_insert:
            if u_data['id'] in existing_ids:
                print(f"Omitiendo usuario '{u_data['username']}' porque el ID {u_data['id']} ya existe en la base de datos.")
                continue
            if u_data['username'] in existing_usernames:
                print(f"Omitiendo usuario '{u_data['username']}' porque el username ya existe en la base de datos.")
                continue
                
            stmt = insert(User).values(**u_data)
            result = await session.execute(stmt)
            if result.rowcount > 0:
                inserted_count += 1
                
        # Sincronizar el ID autoincremental de la secuencia de Postgres si se insertó algo
        if inserted_count > 0:
            await session.execute(text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));"))
        await session.commit()
        
        print(f"Migración completada. Se insertaron {inserted_count} usuarios nuevos (omitiendo duplicados).")
        
        # Verificar el total de usuarios en la base de datos
        res = await session.execute(text("SELECT count(*) FROM users;"))
        total = res.scalar()
        print(f"Total de usuarios en la base de datos ahora: {total}")

if __name__ == "__main__":
    asyncio.run(migrate_users())
