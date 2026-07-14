import asyncio
import logging
from sqlmodel import select
from app.database import async_session_maker, engine
from app.models.ipns_key import IPNSKey

# Configurar logging básico para ver el output en consola
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def deactivate_test_keys():
    """
    Busca todas las claves IPNS en la base de datos que comiencen con el prefijo 'test_'
    y que se encuentren marcadas como activas, cambiándolas a inactivas (is_active = False)
    para evitar que el publicador automático intente firmarlas en el nodo Kubo local.
    """
    logger.info("Iniciando conexión a la base de datos...")
    
    async with async_session_maker() as session:
        # Seleccionar claves que inicien con "test_" y que sigan activas
        stmt = select(IPNSKey).where(IPNSKey.key_name.like("test_%")).where(IPNSKey.is_active == True)
        result = await session.execute(stmt)
        keys_to_deactivate = result.scalars().all()
        
        if not keys_to_deactivate:
            logger.info("No se encontraron claves de prueba activas ('test_%') en la base de datos.")
            await engine.dispose()
            return
            
        logger.info(f"Se encontraron {len(keys_to_deactivate)} claves activas con prefijo 'test_':")
        for key in keys_to_deactivate:
            logger.info(f" -> Desactivando clave: '{key.key_name}' | CID actual: '{key.current_cid}'")
            key.is_active = False
            session.add(key)
            
        # Comprometer los cambios
        await session.commit()
        logger.info("¡Base de datos actualizada exitosamente! Las claves han sido desactivadas.")
    
    # Cerrar el pool de conexiones
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(deactivate_test_keys())
