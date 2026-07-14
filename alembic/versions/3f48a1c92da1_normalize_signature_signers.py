"""normalize_signature_signers

Revision ID: 3f48a1c92da1
Revises: fe558c878bb6
Create Date: 2026-07-03 01:30:00.000000

"""
from typing import Sequence, Union
import json
from datetime import datetime
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision: str = '3f48a1c92da1'
down_revision: Union[str, Sequence[str], None] = 'fe558c878bb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspect_obj = reflection.Inspector.from_engine(bind)
    tables = inspect_obj.get_table_names()

    # 1. Crear la tabla signature_signers si no existe
    if 'signature_signers' not in tables:
        op.create_table(
            'signature_signers',
            sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
            sa.Column('signature_request_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('signed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('signed_at', sa.DateTime(), nullable=True),
            sa.Column('ip', sa.String(length=45), nullable=True),
            sa.Column('user_agent', sa.Text(), nullable=True),
            sa.Column('token', sa.String(length=255), nullable=False),
            sa.Column('signature_image_encrypted', sa.Text(), nullable=True),
            sa.Column('otp_code', sa.String(length=6), nullable=True),
            sa.Column('otp_expires_at', sa.DateTime(), nullable=True),
            sa.Column('consent_electronic_signature', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('consent_habeas_data', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('video_rec_cid', sa.String(length=100), nullable=True),
            sa.Column('video_sha256', sa.String(length=64), nullable=True),
            sa.Column('declaration_text', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['signature_request_id'], ['signature_requests.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        # Crear índices
        op.create_index(op.f('ix_signature_signers_email'), 'signature_signers', ['email'], unique=False)
        op.create_index(op.f('ix_signature_signers_signature_request_id'), 'signature_signers', ['signature_request_id'], unique=False)
        op.create_index(op.f('ix_signature_signers_token'), 'signature_signers', ['token'], unique=True)

    # 2. Migrar los datos de la columna JSON `signers` a la nueva tabla `signature_signers`
    if 'signature_requests' in tables:
        columns = [c['name'] for c in inspect_obj.get_columns('signature_requests')]
        if 'signers' in columns:
            # Consultamos las solicitudes de firma actuales
            connection = op.get_bind()
            results = connection.execute(sa.text("SELECT id, signers FROM signature_requests")).fetchall()
            
            for row in results:
                req_id = row[0]
                signers_data = row[1]
                
                # Deserializar si es string, o procesar si es lista
                if isinstance(signers_data, str):
                    try:
                        signers_list = json.loads(signers_data)
                    except Exception:
                        signers_list = []
                elif isinstance(signers_data, list):
                    signers_list = signers_data
                else:
                    signers_list = []
                
                for s in signers_list:
                    # Extraer campos con fallbacks
                    name = s.get("name", "Desconocido")
                    email = s.get("email", "sin_correo@stardoc.com")
                    signed = s.get("signed", False)
                    
                    signed_at_str = s.get("signed_at")
                    signed_at = None
                    if signed_at_str:
                        try:
                            # Tratar de parsear formato ISO
                            signed_at = datetime.fromisoformat(signed_at_str.replace("Z", "+00:00"))
                        except Exception:
                            signed_at = datetime.utcnow() if signed else None
                            
                    ip = s.get("ip")
                    user_agent = s.get("user_agent")
                    token = s.get("token", f"token-migrated-{req_id}-{email}")
                    
                    # Evidencias en video (si existieran en el JSON anterior)
                    video_rec_cid = s.get("video_rec_cid")
                    video_sha256 = s.get("video_sha256")
                    declaration_text = s.get("declaration_text")
                    
                    # Insertar en la nueva tabla
                    connection.execute(
                        sa.text(
                            """
                            INSERT INTO signature_signers (
                                signature_request_id, name, email, signed, signed_at, ip, user_agent, token,
                                consent_electronic_signature, consent_habeas_data, video_rec_cid, video_sha256, declaration_text
                            ) VALUES (
                                :signature_request_id, :name, :email, :signed, :signed_at, :ip, :user_agent, :token,
                                :consent_electronic_signature, :consent_habeas_data, :video_rec_cid, :video_sha256, :declaration_text
                            )
                            """
                        ),
                        {
                            "signature_request_id": req_id,
                            "name": name,
                            "email": email,
                            "signed": signed,
                            "signed_at": signed_at,
                            "ip": ip,
                            "user_agent": user_agent,
                            "token": token,
                            "consent_electronic_signature": signed, # Si ya firmó, asumimos consentimiento
                            "consent_habeas_data": signed,
                            "video_rec_cid": video_rec_cid,
                            "video_sha256": video_sha256,
                            "declaration_text": declaration_text
                        }
                    )
            
            # 3. Eliminar la columna `signers` de `signature_requests`
            op.drop_column('signature_requests', 'signers')


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspect_obj = reflection.Inspector.from_engine(bind)
    tables = inspect_obj.get_table_names()

    # Si volvemos atrás, necesitamos restaurar la columna `signers` JSON en `signature_requests`
    if 'signature_requests' in tables:
        columns = [c['name'] for c in inspect_obj.get_columns('signature_requests')]
        if 'signers' not in columns:
            op.add_column('signature_requests', sa.Column('signers', sa.JSON(), nullable=True))
            
            # Re-construir los datos en JSON a partir de `signature_signers`
            if 'signature_signers' in tables:
                connection = op.get_bind()
                results = connection.execute(sa.text("SELECT id FROM signature_requests")).fetchall()
                
                for row in results:
                    req_id = row[0]
                    signers_rows = connection.execute(
                        sa.text("SELECT name, email, signed, signed_at, ip, user_agent, token, video_rec_cid, video_sha256, declaration_text FROM signature_signers WHERE signature_request_id = :id"),
                        {"id": req_id}
                    ).fetchall()
                    
                    signers_list = []
                    for s in signers_rows:
                        signed_at_str = s[3].isoformat() if s[3] else None
                        signers_list.append({
                            "name": s[0],
                            "email": s[1],
                            "signed": s[2],
                            "signed_at": signed_at_str,
                            "ip": s[4],
                            "user_agent": s[5],
                            "token": s[6],
                            "video_rec_cid": s[7],
                            "video_sha256": s[8],
                            "declaration_text": s[9]
                        })
                    
                    connection.execute(
                        sa.text("UPDATE signature_requests SET signers = :signers WHERE id = :id"),
                        {"signers": json.dumps(signers_list), "id": req_id}
                    )

    # Eliminar la tabla signature_signers
    if 'signature_signers' in tables:
        op.drop_index(op.f('ix_signature_signers_token'), table_name='signature_signers')
        op.drop_index(op.f('ix_signature_signers_signature_request_id'), table_name='signature_signers')
        op.drop_index(op.f('ix_signature_signers_email'), table_name='signature_signers')
        op.drop_table('signature_signers')
