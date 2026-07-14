"""merge collaborative fields and status templates heads

Revision ID: 8061bfc7f356
Revises: a0044cf4d21b, 90873432a2b5
Create Date: 2026-07-13 09:18:05.053943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8061bfc7f356'
down_revision: Union[str, Sequence[str], None] = ('a0044cf4d21b', '90873432a2b5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
