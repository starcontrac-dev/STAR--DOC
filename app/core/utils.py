import re
import os
import unicodedata
from fastapi import Request

def sanitize_filename(filename: str) -> str:
    """
    Sanitiza un nombre de archivo para hacerlo seguro para el sistema de archivos.
    - Elimina acentos y caracteres especiales.
    - Reemplaza espacios con guiones bajos.
    - Elimina caracteres que no sean alfanuméricos, guiones o puntos.
    """
    # 1. Normalizar Unicode (NFD) y eliminar caracteres no-spacing mark
    filename = unicodedata.normalize('NFD', filename)
    filename = filename.encode('ascii', 'ignore').decode('utf-8')
    
    # 2. Reemplazar espacios por guiones bajos
    filename = filename.replace(' ', '_')
    
    # 3. Mantener solo alfanuméricos, guiones bajos, guiones y puntos
    filename = re.sub(r'[^\w\-.]', '', filename)
    
    # 4. Eliminar puntos o guiones repetidos/extra al inicio/final (opcional pero bueno)
    filename = filename.strip('._')
    
    # 5. Evitar nombres vacíos
    if not filename:
        filename = "unnamed_file"
        
    return filename

def get_base_url(request: Request) -> str:
    """
    Detecta dinámicamente la URL base de la solicitud actual (incluyendo HTTPS, proxys, localtunnel, etc.)
    con un fallback a la configuración settings.BASE_URL.
    """
    from app.core.config import settings
    if not request:
        return settings.BASE_URL
        
    proto_header = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = proto_header.split(",")[0].strip()
    
    host_header = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    host = host_header.split(",")[0].strip()
    
    if "localhost" not in host and "127.0.0.1" not in host:
        # En caso de proxies externos como localtunnel o producción, a veces el scheme original viene como HTTP
        # pero el proxy expone HTTPS (como https://starcontract.loca.lt).
        # Si x-forwarded-proto no está establecido o el host no tiene puerto, y no es localhost,
        # podemos asumir https por defecto si estamos en producción/test web.
        if not request.headers.get("x-forwarded-proto") and not ":" in host:
            scheme = "https"
            
    return f"{scheme}://{host}"
