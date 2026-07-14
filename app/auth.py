
import json
import os
import secrets
import time
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.future import select

from eth_account import Account
from eth_account.messages import encode_defunct

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole
from app.core.config import settings
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

# Solución para el error de "Scope has changed"
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# --- Configuración de Web3 Wallet ---
NONCE_EXPIRATION_SECONDS = 300
nonce_storage = {}  # Respaldo en memoria por si Redis falla

# --- Configuración General ---
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# --- Rutas y Directorios ---
PROJECT_DIR = settings.BASE_DIR
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

LOGIN_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
]

# --- Instancias ---
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Funciones de Ayuda de Base de Datos (ORM) ---
async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    statement = select(User).where(User.username == username)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    return user

async def get_user_by_state(session: AsyncSession, state: str) -> Optional[User]:
    # Primero intentar obtener por Redis (DB 5)
    username = await get_user_by_oauth_state(state)
    if username:
        user = await get_user_by_username(session, username)
        if user:
            return user
            
    # Fallback si no está en Redis o está en BD
    statement = select(User).where(User.oauth_state == state)
    result = await session.execute(statement)
    return result.scalar_one_or_none()

# --- Funciones de Contraseña ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# --- Funciones de Autenticación Core ---
async def authenticate_user(username: str, password: str, session: AsyncSession) -> Optional[User]:
    user = await get_user_by_username(session, username)
    if not user:
        return None
    if not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# --- Funciones de Token JWT ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    # Generar un JTI único para esta sesión si no existe
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Dependencias de Autenticación y Usuario ---
from fastapi import Cookie

# Redefiniendo con auto_error=False para permitir fallback a cookie
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    access_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Resolver token final
    final_token = token or access_token
    if not final_token:
         raise credentials_exception

    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        if username is None:
            raise credentials_exception
            
        # Validar la sesión en Redis si el token tiene JTI
        if jti:
            if not await verify_session(username, jti):
                raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_by_username(session, username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    access_token: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_session)
) -> Optional[User]:
    """Resuelve el usuario opcionalmente si se provee token o cookie válida, sin lanzar error 401."""
    final_token = token or access_token
    if not final_token:
        return None
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        if username is None:
            return None
            
        # Validar la sesión en Redis si el token tiene JTI
        if jti:
            if not await verify_session(username, jti):
                return None
                
        user = await get_user_by_username(session, username)
        if user and not user.disabled:
            return user
    except JWTError:
        pass
    return None


# --- Funciones de Creación de Usuario ---
# No more importing UserCreate schema here to avoid circular imports if schema uses models, 
# but auth schemas are pure Pydantic.
from app.schemas.auth import UserCreate

async def create_user(user_create: UserCreate, session: AsyncSession) -> User:
    # Check existing
    existing_user = await get_user_by_username(session, user_create.username)
    if existing_user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El nombre de usuario ya está registrado")
    
    # Check email (should do query)
    statement = select(User).where(User.email == user_create.email)
    if (await session.execute(statement)).scalar_one_or_none():
         raise HTTPException(status.HTTP_400_BAD_REQUEST, "El email ya está registrado")

    hashed_password = get_password_hash(user_create.password)
    db_user = User(
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=hashed_password,
        disabled=False
    )
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user

# --- Funciones Auxiliares para Credenciales de Google ---
async def get_google_credentials(username: str, session: AsyncSession = None) -> Optional[Credentials]:
    # We need a session here. If not provided, we can't fetch. 
    # But usually this is called from endpoints where session is available.
    user = await get_user_by_username(session, username)
    if not user or not user.google_credentials:
        return None
    
    # Cargar secretos de cliente para asegurar que el refresh funcione
    client_id = None
    client_secret = None
    token_uri = None
    
    try:
        if os.path.exists(settings.GOOGLE_CLIENT_SECRETS_FILE):
             with open(settings.GOOGLE_CLIENT_SECRETS_FILE, 'r') as f:
                secrets_data = json.load(f)
                data = secrets_data.get('web') or secrets_data.get('installed')
                if data:
                    client_id = data.get('client_id')
                    client_secret = data.get('client_secret')
                    token_uri = data.get('token_uri')
    except Exception as e:
        print(f"Error loading client secrets: {e}")

    info = user.google_credentials.copy()
    if client_id and 'client_id' not in info:
        info['client_id'] = client_id
    if client_secret and 'client_secret' not in info:
        info['client_secret'] = client_secret
    if token_uri and 'token_uri' not in info:
        info['token_uri'] = token_uri
    
    creds = Credentials.from_authorized_user_info(info, SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Guardar las credenciales actualizadas en la BD
            user.google_credentials = json.loads(creds.to_json())
            session.add(user)
            await session.commit()
            await session.refresh(user)
        except Exception as e:
            # Si falla el refresh (token revocado, etc.), retornamos None para obligar a reconectar
            # Podríamos loguear el error aquí
            print(f"Error refreshing token for {username}: {e}")
            return None

    return creds

# --- Funciones de Gestión de Sesiones en Redis ---
async def create_session(username: str, token_jti: str, ttl_seconds: int):
    """Registra una sesión activa en Redis."""
    try:
        pool = await redis_manager.get_pool(db=0)
        # Clave: session:{username}:{jti}
        key = f"session:{username}:{token_jti}"
        await pool.setex(key, ttl_seconds, "active")
        # Mantener un set de sesiones activas por usuario
        user_sessions_key = f"user_sessions:{username}"
        await pool.sadd(user_sessions_key, token_jti)
        await pool.expire(user_sessions_key, ttl_seconds)
    except Exception as e:
        logger.error(f"Error al crear sesión en Redis para {username}: {e}")

async def verify_session(username: str, token_jti: str) -> bool:
    """Verifica si la sesión sigue siendo válida en Redis, con degradación graciosa si Redis está offline."""
    try:
        pool = await redis_manager.get_pool(db=0)
        return await pool.exists(f"session:{username}:{token_jti}") > 0
    except Exception as e:
        logger.warning(f"⚠️ Redis verify_session falló (degradación activa): {e}")
        return True  # Aceptar token si Redis está caído

async def revoke_session(username: str, token_jti: str):
    """Revoca una sesión específica en Redis (logout)."""
    try:
        pool = await redis_manager.get_pool(db=0)
        await pool.delete(f"session:{username}:{token_jti}")
        await pool.srem(f"user_sessions:{username}", token_jti)
    except Exception as e:
        logger.error(f"Error al revocar sesión en Redis para {username}: {e}")

async def revoke_all_sessions(username: str):
    """Revoca todas las sesiones activas de un usuario (cambio de contraseña o reinicio)."""
    try:
        pool = await redis_manager.get_pool(db=0)
        user_sessions_key = f"user_sessions:{username}"
        jtis = await pool.smembers(user_sessions_key)
        if jtis:
            pipe = pool.pipeline()
            for jti in jtis:
                pipe.delete(f"session:{username}:{jti}")
            pipe.delete(user_sessions_key)
            await pipe.execute()
    except Exception as e:
        logger.error(f"Error al revocar todas las sesiones en Redis para {username}: {e}")

# --- Funciones de OAuth States en Redis ---
async def store_oauth_state(state: str, username: str):
    """Almacena el estado de OAuth2 mapeado al username por 10 minutos en Redis DB 5."""
    try:
        pool = await redis_manager.get_pool(db=5)
        await pool.setex(f"oauth_state:{state}", 600, username)
    except Exception as e:
        logger.error(f"Error al guardar oauth_state en Redis: {e}")

async def get_user_by_oauth_state(state: str) -> Optional[str]:
    """Obtiene el username asociado a un estado de OAuth y luego borra la clave."""
    try:
        pool = await redis_manager.get_pool(db=5)
        username = await pool.get(f"oauth_state:{state}")
        if username:
            await pool.delete(f"oauth_state:{state}")
        return username
    except Exception as e:
        logger.error(f"Error al obtener oauth_state de Redis: {e}")
        return None

# --- Funciones de Web3 Nonces en Redis ---
async def store_nonce(wallet_address: str, nonce: str):
    """Almacena un nonce de Web3 en Redis DB 5 con expiración de 5 minutos."""
    try:
        pool = await redis_manager.get_pool(db=5)
        await pool.setex(f"nonce:{wallet_address.lower()}", NONCE_EXPIRATION_SECONDS, nonce)
    except Exception as e:
        logger.error(f"Error al almacenar nonce en Redis para {wallet_address}: {e}")
        # Degradación en memoria
        nonce_storage[wallet_address.lower()] = {
            "nonce": nonce,
            "timestamp": time.time()
        }

async def get_nonce(wallet_address: str) -> Optional[str]:
    """Obtiene el nonce almacenado para la dirección de billetera especificada."""
    try:
        pool = await redis_manager.get_pool(db=5)
        return await pool.get(f"nonce:{wallet_address.lower()}")
    except Exception as e:
        logger.error(f"Error al obtener nonce desde Redis para {wallet_address}: {e}")
        # Degradación en memoria
        stored = nonce_storage.get(wallet_address.lower())
        if stored and (time.time() - stored["timestamp"]) <= NONCE_EXPIRATION_SECONDS:
            return stored["nonce"]
        return None

async def delete_nonce(wallet_address: str):
    """Elimina el nonce de Web3 una vez que ha sido verificado."""
    try:
        pool = await redis_manager.get_pool(db=5)
        await pool.delete(f"nonce:{wallet_address.lower()}")
    except Exception as e:
        logger.error(f"Error al eliminar nonce de Redis para {wallet_address}: {e}")
        # Degradación en memoria
        nonce_storage.pop(wallet_address.lower(), None)

# --- Funciones de Lógica de Billetera ---
async def generate_nonce(wallet_address: str) -> str:
    """Genera un nuevo nonce aleatorio y lo almacena para su verificación posterior."""
    nonce = secrets.token_hex(32)
    message = f"Inicie sesión en Star-Doc con su billetera. Nonce: {nonce}"
    await store_nonce(wallet_address, message)
    return message

async def verify_wallet_signature(wallet_address: str, signature: str) -> bool:
    """Valida la firma de un mensaje Web3 usando el nonce almacenado y recupera la dirección pública."""
    stored_nonce = await get_nonce(wallet_address)
    if not stored_nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nonce no encontrado o expirado.")
    
    encoded_message = encode_defunct(text=stored_nonce)

    try:
        recovered_address = Account.recover_message(encoded_message, signature=signature)
    except Exception:
        await delete_nonce(wallet_address)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Firma inválida.")

    await delete_nonce(wallet_address)
    return recovered_address.lower() == wallet_address.lower()

# --- Funciones de Autenticación de Billetera ---
async def authenticate_or_create_wallet_user(wallet_address: str, session: AsyncSession) -> User:
    user = await get_user_by_username(session, wallet_address)
    if not user:
        new_user = User(
            username=wallet_address,
            full_name=f"Billetera {wallet_address[:8]}...",
            email=f"wallet_{wallet_address[2:10].lower()}@example.com",
            hashed_password="",
            disabled=False
        )
        session.add(new_user)
        try:
            await session.commit()
            await session.refresh(new_user)
            return new_user
        except Exception:
             await session.rollback()
             # Retry logic if concurrent creation?
             # For now simple raise
             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error al crear usuario de billetera")
    else:
        return user

async def is_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    is_role_admin = getattr(current_user, 'role', None) == UserRole.ADMIN
    is_username_admin = current_user.username == "starcontract"
    is_flag_admin = getattr(current_user, 'is_admin', False)
    if not (is_role_admin or is_username_admin or is_flag_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requieren privilegios de administrador.")
    return current_user

async def get_creds_for_user(user: User, session: AsyncSession):
    """Helper unificado para obtener credenciales de Google de un usuario."""
    return await get_google_credentials(user.username, session)

def create_file_download_token(filename: str, user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    to_encode = {"sub": str(user_id), "file": filename, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_file_download_token(token: str, filename: str, user_id: int) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_file = payload.get("file")
        token_user_id = payload.get("sub")
        if token_file != filename or str(token_user_id) != str(user_id):
            return False
        return True
    except JWTError:
        return False

def verify_public_download_token(token: str, filename: str) -> bool:
    """Verifica si un token de descarga firmado digitalmente es válido para el archivo especificado sin requerir sesión activa."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_file = payload.get("file")
        if token_file != filename:
            return False
        return True
    except JWTError:
        return False
