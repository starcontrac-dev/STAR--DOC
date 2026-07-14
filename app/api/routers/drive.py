from fastapi import APIRouter, Depends, HTTPException, status, Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from fastapi.responses import JSONResponse
from typing import Optional
import asyncio

from app.auth import get_current_active_user, get_creds_for_user
from app.models.user import User
from app.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Cloud Integrations"])

@router.get("/api/drive/files", response_class=JSONResponse)
async def list_drive_files(
    request: Request,
    mime_type: str,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    creds = await get_creds_for_user(current_user, session)
    if not creds:
        raise HTTPException(400, "La cuenta de Google no está conectada.")

    if mime_type not in ['application/vnd.google-apps.spreadsheet', 'application/vnd.google-apps.document']:
        raise HTTPException(400, "MIME type no soportado.")

    try:
        service = build('drive', 'v3', credentials=creds)
        
        query_parts = [f"mimeType='{mime_type}'", "'me' in owners", "trashed=false"]
        if q:
            query_parts.append(f"name contains '{q.replace("'", "''")}'")
        
        query = " and ".join(query_parts)

        def list_files_blocking():
            return service.files().list(
                q=query, pageSize=100, fields="files(id, name, modifiedTime, iconLink, webViewLink)", orderBy="modifiedTime desc"
            ).execute()

        results = await asyncio.to_thread(list_files_blocking) # Corrección aquí await
        return {"files": results.get('files', [])}

    except HttpError as error:
        if error.resp.status in [401, 403]:
             raise HTTPException(error.resp.status, "Error de autenticación con Google.")
        raise HTTPException(500, f"Google Drive Error: {error}")
    except Exception as e:
        raise HTTPException(500, f"Error interno: {e}")

@router.get("/api/drive/sheets", response_class=JSONResponse)
async def get_drive_sheets(current_user: User = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)):
    # Redirect logic to reusable endpoint logic or keep simple wrapper
    # Keeping simple wrapper for backwards compatibility if frontend calls it directly
    return await list_drive_files(None, 'application/vnd.google-apps.spreadsheet', None, current_user, session)

@router.get("/api/drive/docs", response_class=JSONResponse)
async def get_drive_docs(current_user: User = Depends(get_current_active_user), session: AsyncSession = Depends(get_session)):
    return await list_drive_files(None, 'application/vnd.google-apps.document', None, current_user, session)
