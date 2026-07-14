import asyncio
import json
import os
import sys

# Añadir el directorio raíz al path para poder importar app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_session
from app.models.template import Template
from app.core.config import settings
from sqlmodel import select

async def migrate_templates():
    json_path = settings.TEMPLATES_JSON_PATH
    if not os.path.exists(json_path):
        print(f"No se encontró {json_path}. Nada que migrar.")
        return

    print(f"Leyendo plantillas de {json_path}...")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)
    except Exception as e:
        print(f"Error leyendo JSON: {e}")
        return

    async for session in get_session():
        count = 0
        for item in templates_data:
            filename = item.get('filename')
            if not filename:
                continue

            # Verificar si ya existe en DB
            statement = select(Template).where(Template.filename == filename)
            results = await session.execute(statement)
            existing = results.scalars().first()

            if existing:
                print(f"Saltando {filename} (ya existe en DB).")
                continue

            # Crear nuevo registro
            # Intentar parsear uploaded_at, si falla usar ahora
            uploaded_at_str = item.get('uploaded_at')
            from datetime import datetime
            uploaded_at = datetime.utcnow()
            if uploaded_at_str:
                try:
                    uploaded_at = datetime.fromisoformat(uploaded_at_str)
                except ValueError:
                    pass

            new_template = Template(
                filename=filename,
                description=f"Importado de templates.json. Path original: {item.get('path', '')}",
                uploaded_at=uploaded_at
            )
            session.add(new_template)
            count += 1
        
        try:
            await session.commit()
            print(f"Migración completada. {count} plantillas insertadas.")
        except Exception as e:
            await session.rollback()
            print(f"Error al hacer commit en la BD: {e}")
        break # get_session es un generador, solo necesitamos una sesión

if __name__ == "__main__":
    asyncio.run(migrate_templates())
