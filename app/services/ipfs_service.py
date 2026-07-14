"""Servicio IPFS con estrategia dual: Kubo Local + Pinata Cloud."""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

from app.services.crypto_engine import CryptoEngine, DocClassification
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configuración
KUBO_RPC_URL = os.getenv("KUBO_RPC_URL", "http://127.0.0.1:5001")
PINATA_JWT = settings.PINATA_JWT
PINATA_API_URL = "https://api.pinata.cloud"
PINATA_GATEWAY = settings.PINATA_GATEWAY

class IPFSService:
    """Servicio profesional de gestión IPFS para documentos legales."""

    # ── Kubo Local (IPFS Desktop) ──

    @staticmethod
    async def check_kubo_health() -> dict:
        """Verifica el estado de salud, peers y almacenamiento del nodo Kubo."""
        health = {
            "online": False, 
            "peer_id": None, 
            "version": None, 
            "repo_size_bytes": 0, 
            "repo_max_bytes": 0, 
            "peers_connected": 0, 
            "error": None
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # 1. Info básica del nodo
                resp = await client.post(f"{KUBO_RPC_URL}/api/v0/id")
                if resp.status_code == 200:
                    data = resp.json()
                    health["online"] = True
                    health["peer_id"] = data.get("ID")
                    health["version"] = data.get("AgentVersion")
                else:
                    health["error"] = f"Kubo /id retornó HTTP {resp.status_code}"
                    return health
                
                # 2. Stats del Repositorio
                repo_resp = await client.post(f"{KUBO_RPC_URL}/api/v0/repo/stat")
                if repo_resp.status_code == 200:
                    repo_data = repo_resp.json()
                    health["repo_size_bytes"] = repo_data.get("RepoSize", 0)
                    health["repo_max_bytes"] = repo_data.get("StorageMax", 0)
                
                # 3. Swarm Peers
                peers_resp = await client.post(f"{KUBO_RPC_URL}/api/v0/swarm/peers")
                if peers_resp.status_code == 200:
                    peers_data = peers_resp.json()
                    health["peers_connected"] = len(peers_data.get("Peers") or [])
        except Exception as e:
            health["error"] = str(e)
        return health

    @staticmethod
    async def upload_to_kubo(file_name: str, file_data: bytes) -> dict:
        """Sube archivo al nodo local Kubo vía RPC API."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/add",
                files={"file": (file_name, file_data)},
                params={"cid-version": 1, "pin": "true"}
            )
            resp.raise_for_status()
            result = resp.json()
            cid = result["Hash"]
            
            # Hacerlo visible en la interfaz "Files" de IPFS Desktop (MFS)
            try:
                import urllib.parse
                safe_name = urllib.parse.quote(file_name.replace("/", "_"))
                await client.post(
                    f"{KUBO_RPC_URL}/api/v0/files/cp",
                    params=[("arg", f"/ipfs/{cid}"), ("arg", f"/{safe_name}")]
                )
            except Exception as e:
                logger.warning(f"No se pudo enlazar a MFS en IPFS Desktop: {e}")
                
            return {"cid": cid, "size": result["Size"], "name": result["Name"]}

    @staticmethod
    async def get_from_kubo(cid: str) -> bytes:
        """Descarga contenido desde el nodo local por CID."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/cat",
                params={"arg": cid}
            )
            resp.raise_for_status()
            return resp.content

    @staticmethod
    async def stream_from_kubo(cid: str, chunk_size: int = 64 * 1024, offset: Optional[int] = None, length: Optional[int] = None):
        """
        Descarga contenido desde Kubo en modo streaming (chunks) con soporte opcional de offset y longitud.
        Genera bloques de bytes para uso con StreamingResponse de FastAPI.
        """
        params = {"arg": cid}
        if offset is not None:
            params["offset"] = str(offset)
        if length is not None:
            params["length"] = str(length)
            
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{KUBO_RPC_URL}/api/v0/cat",
                params=params
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk


    @staticmethod
    async def pin_in_kubo(cid: str) -> dict:
        """Pinea un CID existente en el nodo local."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/pin/add",
                params={"arg": cid}
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def list_pins_kubo() -> list:
        """Lista todos los pins del nodo local."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/pin/ls",
                params={"type": "recursive"}
            )
            resp.raise_for_status()
            data = resp.json()
            return list(data.get("Keys", {}).keys())

    @staticmethod
    async def create_mfs_directory(dir_path: str) -> None:
        """Crea un directorio en el Mutable File System (MFS) de Kubo."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/files/mkdir",
                params={"arg": dir_path, "parents": "true"}
            )
            # 500 puede ocurrir si ya existe, lo manejamos tolerando la existencia
            if resp.status_code not in (200, 500):
                resp.raise_for_status()

    @staticmethod
    async def copy_to_mfs(source_ipfs_path: str, dest_mfs_path: str) -> None:
        """Copia un CID de IPFS a una ruta en el MFS de Kubo."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/files/cp",
                params=[("arg", source_ipfs_path), ("arg", dest_mfs_path)]
            )
            resp.raise_for_status()

    @staticmethod
    async def stat_mfs_path(mfs_path: str) -> dict:
        """Obtiene información (incluido el CID) de una ruta MFS."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/files/stat",
                params={"arg": mfs_path}
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def unpin_from_kubo(cid: str) -> dict:
        """Despinea un CID del nodo local Kubo."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/pin/rm",
                params={"arg": cid}
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def run_gc() -> dict:
        """Ejecuta Garbage Collection en el repositorio Kubo."""
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{KUBO_RPC_URL}/api/v0/repo/gc")
            resp.raise_for_status()
            return {"message": "Garbage collection completado."}

    @staticmethod
    async def get_repo_stats() -> dict:
        """Obtiene estadísticas detalladas del repositorio Kubo combinando salud y almacenamiento."""
        # 1. Obtener salud (online, peers_connected, etc.)
        health = await IPFSService.check_kubo_health()
        
        # 2. Si no está online, retornar estructura básica offline
        if not health.get("online", False):
            return {
                "online": False,
                "peer_id": None,
                "version": None,
                "repo_size_bytes": 0,
                "repo_max_bytes": 0,
                "peers_connected": 0,
                "error": health.get("error"),
                "RepoSize": 0,
                "StorageMax": 0,
                "NumObjects": 0,
                "RepoPath": "N/A",
                "repo_size_human": "0.00 MB",
                "storage_max_human": "0.00 GB",
                "num_objects": 0,
                "repo_path": "N/A",
                "usage_percent": 0.0
            }
            
        # 3. Si está online, obtener stats detallados de repo
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{KUBO_RPC_URL}/api/v0/repo/stat")
                resp.raise_for_status()
                data = resp.json()
                repo_size = data.get("RepoSize", 0)
                storage_max = data.get("StorageMax", 0)
                num_objects = data.get("NumObjects", 0)
                repo_path = data.get("RepoPath", "N/A")
                
                return {
                    # Claves en minúsculas (para dashboard.html)
                    "online": True,
                    "peer_id": health.get("peer_id"),
                    "version": health.get("version"),
                    "repo_size_bytes": repo_size,
                    "repo_max_bytes": storage_max,
                    "peers_connected": health.get("peers_connected", 0),
                    "error": None,
                    
                    # Claves en mayúsculas (para ia.html)
                    "RepoSize": repo_size,
                    "StorageMax": storage_max,
                    "NumObjects": num_objects,
                    "RepoPath": repo_path,
                    
                    # Claves extra
                    "repo_size_human": f"{repo_size / (1024**2):.2f} MB",
                    "storage_max_human": f"{storage_max / (1024**3):.2f} GB",
                    "num_objects": num_objects,
                    "repo_path": repo_path,
                    "usage_percent": round((repo_size / max(storage_max, 1)) * 100, 2)
                }
        except Exception as e:
            logger.error(f"Error al obtener repo stats: {e}")
            # Fallback a salud básica
            repo_size = health.get("repo_size_bytes", 0)
            storage_max = health.get("repo_max_bytes", 0)
            return {
                "online": True,
                "peer_id": health.get("peer_id"),
                "version": health.get("version"),
                "repo_size_bytes": repo_size,
                "repo_max_bytes": storage_max,
                "peers_connected": health.get("peers_connected", 0),
                "error": str(e),
                "RepoSize": repo_size,
                "StorageMax": storage_max,
                "NumObjects": 0,
                "RepoPath": "N/A",
                "repo_size_human": f"{repo_size / (1024**2):.2f} MB",
                "storage_max_human": f"{storage_max / (1024**3):.2f} GB",
                "num_objects": 0,
                "repo_path": "N/A",
                "usage_percent": round((repo_size / max(storage_max, 1)) * 100, 2)
            }

    # ── Pinata Cloud (Pinning Remoto) ──


    @staticmethod
    async def upload_to_pinata(
        file_name: str, file_data: bytes,
        metadata: Optional[dict] = None,
        group_id: Optional[str] = None
    ) -> dict:
        """Sube y pinea archivo en Pinata para redundancia."""
        headers = {"Authorization": f"Bearer {PINATA_JWT}"}
        pinata_metadata = json.dumps({
            "name": file_name,
            "keyvalues": metadata or {}
        })
        pinata_options = json.dumps({"cidVersion": 1})

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{PINATA_API_URL}/pinning/pinFileToIPFS",
                headers=headers,
                files={"file": (file_name, file_data)},
                data={
                    "pinataMetadata": pinata_metadata,
                    "pinataOptions": pinata_options,
                }
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"Pinata pin exitoso: {result['IpfsHash']}")
            return {
                "cid": result["IpfsHash"],
                "size": result["PinSize"],
                "timestamp": result["Timestamp"],
                "pinata_id": result.get("id"),
            }

    @staticmethod
    async def pin_by_cid_pinata(cid: str, name: str) -> dict:
        """Pinea en Pinata un CID que ya existe en la red IPFS."""
        headers = {
            "Authorization": f"Bearer {PINATA_JWT}",
            "Content-Type": "application/json"
        }
        payload = {
            "hashToPin": cid,
            "pinataMetadata": {"name": name}
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{PINATA_API_URL}/pinning/pinByHash",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def get_gateway_url(cid: str) -> str:
        """Genera URL del gateway preferido para IPFS (soporta subdominios o gateway dedicado de Pinata)."""
        if settings.PINATA_GATEWAY and "mypinata.cloud" in settings.PINATA_GATEWAY:
            return f"{settings.PINATA_GATEWAY}/ipfs/{cid}"
        if cid.startswith("baf"):
            return f"https://{cid}.ipfs.inbrowser.link/"
        return f"https://ipfs.io/ipfs/{cid}"

    # ── Pipeline Completo ──

    @staticmethod
    async def secure_upload(
        file_name: str,
        file_data: bytes,
        classification: DocClassification = DocClassification.PUBLIC,
        metadata: Optional[dict] = None,
        encryption_key: Optional[bytes] = None,
    ) -> dict:
        """
        Pipeline completo: hash → encriptar (si aplica) → subir local → pin remoto.
        """
        # Asegurar tipo de clasificación a string plano limpio para evitar fallos de Enum/SQLAlchemy
        class_str = classification.value if hasattr(classification, "value") else str(classification)
        class_str = class_str.strip().lower()

        sha256_original = CryptoEngine.compute_sha256(file_data)
        upload_data = file_data
        upload_name = file_name

        # Encriptar si es confidencial o cadena de custodia
        if class_str != "public":
            envelope = CryptoEngine.encrypt_with_envelope(file_data, key=encryption_key)
            upload_data = envelope["encrypted_data"]
            encryption_key = envelope["encryption_key"]
            upload_name = f"{file_name}.enc"
            logger.info(f"Documento encriptado: {class_str}")

        # 1. Subir a nodo local Kubo
        kubo_result = None
        try:
            kubo_result = await IPFSService.upload_to_kubo(upload_name, upload_data)
            logger.info(f"Kubo local OK: {kubo_result['cid']}")
        except Exception as e:
            logger.warning(f"Kubo local no disponible: {e}")

        # 2. Subir/Pin en Pinata (Estrategia híbrida: solo confidencial/cadena de custodia para cuidar la cuota gratuita de 500 archivos)
        pinata_result = None
        if PINATA_JWT and class_str != "public":
            meta = {
                "classification": class_str,
                "sha256_original": sha256_original,
                "source": "star-doc",
                **(metadata or {})
            }
            # Lanzamos la tarea de Pinata en background para no bloquear el Event Loop
            import asyncio
            asyncio.create_task(
                IPFSService.upload_to_pinata(upload_name, upload_data, metadata=meta)
            )
        else:
            logger.info("Evitando subida a Pinata para archivo publico (Estrategia Hibrida para proteger limite gratuito de 500 archivos)")

        # Determinar CID final (retornamos el de Kubo inmediatamente)
        cid = (kubo_result or {}).get("cid")
        if not cid:
            raise RuntimeError("No se pudo subir a ningún proveedor IPFS")

        return {
            "cid": cid,
            "sha256_original": sha256_original,
            "classification": class_str,
            "encryption_key": encryption_key,
            "kubo": kubo_result,
            "pinata": pinata_result,
            "gateway_url": IPFSService.get_gateway_url(cid),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_encrypted": class_str != "public",
        }

    # ── IPNS para Versionado de Contratos ──

    @staticmethod
    async def ipns_create_key(key_name: str) -> dict:
        """Crea una nueva clave en Kubo para publicar nombres IPNS mutables."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/key/gen",
                params={"arg": key_name, "type": "ed25519"}
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def ipns_publish(cid: str, key_name: str) -> dict:
        """Publica un CID bajo un nombre IPNS mutable usando una clave local."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/name/publish",
                params={"arg": cid, "key": key_name}
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def ipns_resolve(ipns_name: str) -> str:
        """Resuelve un nombre IPNS mutable a su CID de destino inmutable actual."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/name/resolve",
                params={"arg": ipns_name}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["Path"]

    @staticmethod
    async def ipns_list_keys() -> dict:
        """Lista todas las claves IPNS registradas en Kubo."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KUBO_RPC_URL}/api/v0/key/list"
            )
            resp.raise_for_status()
            return resp.json()

