from datetime import timedelta, datetime, timezone
from typing import Optional
import json
import secrets
import httpx

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from google_auth_oauthlib.flow import Flow
from app.core.limiter import limiter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import (
    authenticate_user,
    get_current_active_user,
    create_access_token,
    create_user,
    generate_nonce,
    verify_wallet_signature,
    authenticate_or_create_wallet_user,
    get_password_hash,
    get_user_by_state,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SCOPES,
    LOGIN_SCOPES,
    get_user_by_username,
    create_session,
    revoke_session,
    revoke_all_sessions,
    store_oauth_state
)
import uuid
from app.models.user import User
from app.core.config import settings
from app.schemas.auth import UserCreate, WalletAddress, WalletLogin, Token, PasswordResetRequest, PasswordResetConfirm
from app.database import get_session
from app.services.email import send_email_async
from app.core.utils import get_base_url

router = APIRouter(tags=["Authentication"])

@router.post("/token", response_model=Token)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    response: Response, 
    form_data: OAuth2PasswordRequestForm = Depends(), 
    session: AsyncSession = Depends(get_session)
):
    user = await authenticate_user(form_data.username, form_data.password, session)
    if not user:
        # Error genérico para mitigar adivinación (OWASP)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Generar un JTI único para esta sesión de token de acceso
    access_jti = str(uuid.uuid4())
    access_token = create_access_token(
        data={"sub": user.username, "jti": access_jti, "role": getattr(user, 'role', 'user')}, expires_delta=access_token_expires
    )
    
    refresh_jti = str(uuid.uuid4())
    refresh_token = create_access_token(
        data={"sub": user.username, "type": "refresh", "jti": refresh_jti}, expires_delta=timedelta(days=7)
    )
    
    # Registrar las sesiones en Redis
    await create_session(user.username, access_jti, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    await create_session(user.username, refresh_jti, 7 * 24 * 60 * 60)
    
    # Cookies para seguridad contra XSS (OWASP HTTPOnly, Secure)
    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True, 
        secure=True, 
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="refresh_token", 
        value=refresh_token, 
        httponly=True, 
        secure=True, 
        samesite="lax",
        max_age=7 * 24 * 60 * 60
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(request: Request, user: UserCreate, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    db_user = await create_user(user, session)
    
    # Generar token de verificación
    token = secrets.token_urlsafe(32)
    db_user.verification_token = token
    session.add(db_user)
    await session.commit()
    
    # Background Task: Enviar correo de verificación
    base_url = get_base_url(request)
    verification_link = f"{base_url}/verify-email?token={token}"
    body = f"<p>Hola {user.full_name},</p><p>Por favor confirma tu email haciendo clic aquí: <a href='{verification_link}'>Verificar Cuenta</a></p>"
    background_tasks.add_task(send_email_async, "Verifica tu cuenta en Star-Doc", user.email, body)
    
    return {"message": "Usuario creado exitosamente. Por favor, revisa tu correo electrónico."}

@router.get("/verify-email")
async def verify_email(token: str, session: AsyncSession = Depends(get_session)):
    statement = select(User).where(User.verification_token == token)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token no válido o expirado.")
        
    user.is_verified = True
    user.verification_token = None
    session.add(user)
    await session.commit()
    
    return {"message": "Correo verificado exitosamente. Ahora puedes iniciar sesión."}

@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def forgot_password(request: Request, request_data: PasswordResetRequest, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    statement = select(User).where(User.email == request_data.email)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_password_token = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        session.add(user)
        await session.commit()
        
        base_url = get_base_url(request)
        reset_link = f"{base_url}/reset-password?token={token}"
        body = f"<p>Solicitaste restablecer tu contraseña. Ingresa aquí: <a href='{reset_link}'>Restablecer</a>.</p><p>Este enlace expira en 1 hora.</p>"
        background_tasks.add_task(send_email_async, "Recuperación de Contraseña - Star-Doc", user.email, body)
    
    # Prevención de enumeración de usuarios OWASP
    return {"message": "Si el correo está registrado, recibirás un enlace de recuperación."}

@router.post("/reset-password")
async def reset_password(request_data: PasswordResetConfirm, session: AsyncSession = Depends(get_session)):
    statement = select(User).where(User.reset_password_token == request_data.token)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    now = datetime.now(timezone.utc)
    
    if not user or not user.reset_token_expires:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token inválido o proceso no iniciado.")
        
    expiry = user.reset_token_expires
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
        
    if now > expiry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token expirado.")
        
    user.hashed_password = get_password_hash(request_data.new_password)
    user.reset_password_token = None
    user.reset_token_expires = None
    session.add(user)
    await session.commit()
    
    # Revocar todas las sesiones del usuario en Redis
    await revoke_all_sessions(user.username)
    
    return {"message": "Contraseña actualizada exitosamente. Ya puedes iniciar sesión."}

# --- Google OAuth2 ---

@router.get("/auth/google/connect")
async def login_google(request: Request, current_user: User = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)):
    """Inicia el flujo de OAuth2 para conectar Google Drive/Sheets/Gmail."""
    # Extraer dominio de origen dinámicamente
    # Extraer dominio de origen dinámicamente de forma robusta
    proto_header = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = proto_header.split(",")[0].strip()
    
    host_header = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    host = host_header.split(",")[0].strip()
    
    if "localhost" not in host and "127.0.0.1" not in host:
        scheme = "https"
        # Limpiamos cualquier puerto que los proxies puedan estar añadiendo
        if ":" in host:
            host = host.split(":")[0]
            
    origin = f"{scheme}://{host}"
    
    # La redirect_uri debe coincidir exactamente con una de las registradas en Google Console
    # Usamos el origen actual para que Google nos devuelva al mismo sitio (útil para túneles y móvil)
    dynamic_redirect_uri = f"{origin}/auth/google/callback"
    
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=dynamic_redirect_uri
    )
    authorization_url, oauth_state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    import base64
    encoded_origin = base64.urlsafe_b64encode(origin.encode()).decode().rstrip("=")
    new_state = f"conn_{encoded_origin}_{oauth_state}"
    
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    url_parts = list(urlparse(authorization_url))
    query = parse_qs(url_parts[4])
    query['state'] = [new_state]
    url_parts[4] = urlencode(query, doseq=True)
    authorization_url = urlunparse(url_parts)
    
    # Almacenar el oauth_state en Redis DB 5 (expira automáticamente) en lugar de la BD tradicional
    await store_oauth_state(new_state, current_user.username)
    
    return {"authorization_url": authorization_url}

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, code: str, state: str, session: AsyncSession = Depends(get_session)):
    is_login_flow = state.startswith("login_")
    
    import base64
    base_url = ""
    parts = state.split("_", 2)
    if len(parts) >= 2:
        encoded_origin = parts[1]
        try:
            padded = encoded_origin + "=" * ((4 - len(encoded_origin) % 4) % 4)
            base_url = base64.urlsafe_b64decode(padded).decode()
        except:
            pass

    # Reconstruir la redirect_uri dinámica que se usó al iniciar el flujo OAuth.
    # Google exige que la redirect_uri del intercambio de token sea IDÉNTICA
    # a la que se envió durante la solicitud de autorización.
    # Si tenemos un origin codificado en el state, lo usamos; si no, fallback al estático.
    callback_redirect_uri = f"{base_url}/auth/google/callback" if base_url else settings.REDIRECT_URI

    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=LOGIN_SCOPES if is_login_flow else SCOPES,
        state=state, 
        redirect_uri=callback_redirect_uri
    )
    
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        if is_login_flow:
            async with httpx.AsyncClient() as client:
                user_info_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {creds.token}"}
                )
                if not user_info_response.is_success:
                    raise HTTPException(400, "Error obteniendo datos de usuario de Google")
                    
                user_info = user_info_response.json()
                email = user_info.get("email")
                name = user_info.get("name", "Usuario Google")
                
            if not email:
                raise HTTPException(400, "Google no proporcionó el email del usuario.")

            # Buscar usuario
            statement = select(User).where(User.email == email)
            result = await session.execute(statement)
            user = result.scalar_one_or_none()
            
            if not user:
                # Crear nuevo usuario con google sign in
                username_base = email.split("@")[0]
                username = username_base
                counter = 1
                while await get_user_by_username(session, username):
                    username = f"{username_base}{counter}"
                    counter += 1
                    
                user = User(
                    username=username,
                    full_name=name,
                    email=email,
                    hashed_password="", # vacio por oauth
                    disabled=False,
                    is_verified=True,
                    role="user"
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            # Generar token de acceso para Star-Doc
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            
            access_jti = str(uuid.uuid4())
            access_token = create_access_token(
                data={"sub": user.username, "jti": access_jti, "role": getattr(user, 'role', 'user')}, expires_delta=access_token_expires
            )
            
            refresh_jti = str(uuid.uuid4())
            refresh_token = create_access_token(
                data={"sub": user.username, "type": "refresh", "jti": refresh_jti}, expires_delta=timedelta(days=7)
            )
            
            # Registrar sesiones activas en Redis
            await create_session(user.username, access_jti, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
            await create_session(user.username, refresh_jti, 7 * 24 * 60 * 60)
            
            response = RedirectResponse(url=f"{base_url}/login?token={access_token}&google_login=success")
            response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
            response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="lax", max_age=7*24*60*60)
            return response
            
        else:
            # Flujo original de Conexión de Google Drive
            # El state que recibimos es exactamente el 'new_state' que guardamos 
            # en user.oauth_state durante /auth/google/connect.
            user = await get_user_by_state(session, state)
            if not user:
                 raise HTTPException(400, "Estado de autenticación inválido o expirado.")
            
            user.google_credentials = json.loads(creds.to_json())
            user.oauth_state = None
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            return RedirectResponse(url=f"{base_url}/home?google_connected=true")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en autenticación Google: {e}")

@router.get("/auth/google/login/start")
async def google_login_start(request: Request):
    """Inicia el flujo OAuth2 para Iniciar Sesión en la aplicación usando Google."""
    # Extraer dominio de origen dinámicamente
    # Extraer dominio de origen dinámicamente de forma robusta
    proto_header = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = proto_header.split(",")[0].strip()
    
    host_header = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    host = host_header.split(",")[0].strip()
    
    if "localhost" not in host and "127.0.0.1" not in host:
        scheme = "https"
        # Limpiamos cualquier puerto que los proxies puedan estar añadiendo (ej: :443 o :80)
        if ":" in host:
            host = host.split(":")[0]
            
    origin = f"{scheme}://{host}"
    
    # Usamos el origen actual como redirect_uri para que Google regrese al dominio correcto
    dynamic_redirect_uri = f"{origin}/auth/google/callback"
    
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=LOGIN_SCOPES,
        redirect_uri=dynamic_redirect_uri
    )
    authorization_url, oauth_state = flow.authorization_url(
        access_type='online',
        prompt='consent'
    )
    
    import base64
    encoded_origin = base64.urlsafe_b64encode(origin.encode()).decode().rstrip("=")
    new_state = f"login_{encoded_origin}_{oauth_state}"
    
    # Recreamos la url con el nuevo state modificado
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    url_parts = list(urlparse(authorization_url))
    query = parse_qs(url_parts[4])
    query['state'] = [new_state]
    url_parts[4] = urlencode(query, doseq=True)
    authorization_url = urlunparse(url_parts)
    
    return RedirectResponse(url=authorization_url)

# --- Web3 Wallet ---

@router.post("/get-signature-message")
async def get_signature_message(wallet_data: WalletAddress):
    message = await generate_nonce(wallet_data.wallet_address)
    return {"message": message}

@router.post("/login-wallet", response_model=Token)
@limiter.limit("5/minute")
async def login_wallet(request: Request, response: Response, login_data: WalletLogin, session: AsyncSession = Depends(get_session)):
    if not await verify_wallet_signature(login_data.wallet_address, login_data.signature):
        raise HTTPException(status_code=400, detail="Firma inválida")
    
    user = await authenticate_or_create_wallet_user(login_data.wallet_address, session)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    access_jti = str(uuid.uuid4())
    access_token = create_access_token(
        data={"sub": user.username, "jti": access_jti, "role": getattr(user, 'role', 'user')}, expires_delta=access_token_expires
    )
    
    refresh_jti = str(uuid.uuid4())
    refresh_token = create_access_token(
        data={"sub": user.username, "type": "refresh", "jti": refresh_jti}, expires_delta=timedelta(days=7)
    )
    
    # Registrar las sesiones en Redis
    await create_session(user.username, access_jti, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    await create_session(user.username, refresh_jti, 7 * 24 * 60 * 60)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="lax", max_age=7*24*60*60)
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """Cierra la sesión del usuario revocando el token en Redis y eliminando las cookies."""
    # Obtener el token de la cookie o de la cabecera Authorization
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    if token:
        try:
            from jose import jwt
            from app.auth import SECRET_KEY, ALGORITHM
            # Decodificar el token sin verificar la expiración
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti and current_user:
                await revoke_session(current_user.username, jti)
        except Exception as e:
            # Registrar un error no crítico en el log
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error decodificando token en logout: {e}")
            
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Sesión cerrada correctamente"}
