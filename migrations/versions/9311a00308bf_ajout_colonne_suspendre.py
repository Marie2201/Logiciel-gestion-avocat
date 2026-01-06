"""ajout colonne suspendre

Revision ID: 9311a00308bf
Revises: 587bb4030744
Create Date: 2026-01-06 18:48:34.734737

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '9311a00308bf'
down_revision = '587bb4030744'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(
            sa.Column(
                'suspended',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('0')
            )
        )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('suspended')
