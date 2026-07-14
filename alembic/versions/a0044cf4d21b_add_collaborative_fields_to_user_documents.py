"""add_collaborative_fields_to_user_documents

Revision ID: a0044cf4d21b
Revises: fe558c878bb6
Create Date: 2026-07-13 01:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision: str = 'a0044cf4d21b'
down_revision: Union[str, Sequence[str], None] = 'fe558c878bb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspect_obj = reflection.Inspector.from_engine(bind)
    tables = inspect_obj.get_table_names()

    if 'user_documents' in tables:
        columns = [c['name'] for c in inspect_obj.get_columns('user_documents')]
        
        # Añadir is_collaborative si no existe
        if 'is_collaborative' not in columns:
            op.add_column('user_documents', sa.Column('is_collaborative', sa.Boolean(), nullable=True))
            # Crear índice
            op.create_index(op.f('ix_user_documents_is_collaborative'), 'user_documents', ['is_collaborative'], unique=False)
            # Inicializar valor por defecto a False para consistencia
            op.execute("UPDATE user_documents SET is_collaborative = FALSE WHERE is_collaborative IS NULL")

        # Añadir cryptpad_share_url si no existe
        if 'cryptpad_share_url' not in columns:
            op.add_column('user_documents', sa.Column('cryptpad_share_url', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspect_obj = reflection.Inspector.from_engine(bind)
    tables = inspect_obj.get_table_names()

    if 'user_documents' in tables:
        columns = [c['name'] for c in inspect_obj.get_columns('user_documents')]
        
        # Eliminar índice y columna is_collaborative
        if 'is_collaborative' in columns:
            op.drop_index(op.f('ix_user_documents_is_collaborative'), table_name='user_documents')
            op.drop_column('user_documents', 'is_collaborative')
            
        # Eliminar columna cryptpad_share_url
        if 'cryptpad_share_url' in columns:
            op.drop_column('user_documents', 'cryptpad_share_url')
