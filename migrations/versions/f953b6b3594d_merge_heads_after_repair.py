"""merge heads after repair

Revision ID: f953b6b3594d
Revises: 51e5521c8bfd, f6e2a0a2a0b9
Create Date: 2025-08-09 18:31:00.117122

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f953b6b3594d'
down_revision = ('51e5521c8bfd', 'f6e2a0a2a0b9')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
