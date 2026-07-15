from .user import User
from .template import Template
from .user_document import UserDocument

# --- Modelos del Secretario IA ---
from .lead import Lead, LeadStatus, LeadSource
from .appointment import Appointment, AppointmentStatus, AppointmentType
from .availability import AvailableSlot
from .conversation import ConversationLog

# --- Modelos IPFS ---
from .document_ipfs import DocumentIPFS
from .ipfs_audit import IPFSAudit
from .document_access_log import DocumentAccessLog
from .ipns_key import IPNSKey
from .ipns_version_history import IPNSVersionHistory
from .webhook_subscription import WebhookSubscription
from .ipfs_pending_task import IPFSPendingTask

# --- Modelos de Firma ---
from .signature import SignatureRequest, SignatureSigner

# --- RAG Jurídico Localizado ---
from .legal_knowledge import LegalKnowledgeChunk

# --- Auditor de KYC / AML (SARLAFT/SAGRILAFT) ---
from .kyc_audit import KycAudit

# --- Auditoría de Tools ---
from .tool_audit import ToolAuditLog
