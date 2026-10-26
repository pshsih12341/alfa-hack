"""applications: has_collateral

Revision ID: 5d3a9c7e2b14
Revises: 1072c7049733
Create Date: 2026-10-26 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d3a9c7e2b14'
down_revision: Union[str, Sequence[str], None] = '1072c7049733'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('applications', sa.Column('has_collateral', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('applications', 'has_collateral')
