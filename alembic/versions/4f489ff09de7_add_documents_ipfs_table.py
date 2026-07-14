"""add_documents_ipfs_table

Revision ID: 4f489ff09de7
Revises: da2375fd15d3
Create Date: 2026-05-19 01:09:34.360833

Migración limpia: SOLO crea la tabla documents_ipfs.
No toca tablas legacy existentes (chat_messages, apscheduler_jobs, etc.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision: str = '4f489ff09de7'
down_revision: Union[str, Sequence[str], None] = 'da2375fd15d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla documents_ipfs con índices para CID y SHA-256."""
    op.create_table('documents_ipfs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('ipfs_cid', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('sha256_original', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('classification', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False),
        sa.Column('encryption_key_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('original_filename', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('pinned_kubo', sa.Boolean(), nullable=False),
        sa.Column('pinned_pinata', sa.Boolean(), nullable=False),
        sa.Column('pinata_pin_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('blockchain_tx_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('blockchain_network', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('gateway_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_ipfs_document_id'), 'documents_ipfs', ['document_id'], unique=False)
    op.create_index(op.f('ix_documents_ipfs_ipfs_cid'), 'documents_ipfs', ['ipfs_cid'], unique=True)
    op.create_index(op.f('ix_documents_ipfs_sha256_original'), 'documents_ipfs', ['sha256_original'], unique=False)
    op.create_index(op.f('ix_documents_ipfs_user_id'), 'documents_ipfs', ['user_id'], unique=False)


def downgrade() -> None:
    """Elimina la tabla documents_ipfs."""
    op.drop_index(op.f('ix_documents_ipfs_user_id'), table_name='documents_ipfs')
    op.drop_index(op.f('ix_documents_ipfs_sha256_original'), table_name='documents_ipfs')
    op.drop_index(op.f('ix_documents_ipfs_ipfs_cid'), table_name='documents_ipfs')
    op.drop_index(op.f('ix_documents_ipfs_document_id'), table_name='documents_ipfs')
    op.drop_table('documents_ipfs')
