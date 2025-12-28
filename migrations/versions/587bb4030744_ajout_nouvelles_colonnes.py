"""ajout nouvelles colonnes

Revision ID: 587bb4030744
Revises: 2c4fbcf60622
Create Date: 2025-09-29 10:49:52.967606

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '587bb4030744'
down_revision = '2c4fbcf60622'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'timesheet',
        'heure_debut',
        existing_type=sa.Time(),
        nullable=False,
        server_default=sa.text("'00:00:00'")
    )
    op.alter_column(
        'timesheet',
        'heure_fin',
        existing_type=sa.Time(),
        nullable=False,
        server_default=sa.text("'00:00:00'")
    )


    # ### end Alembic commands ###



    # ### end Alembic commands ###
