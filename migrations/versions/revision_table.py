"""Backfill heure_* NULL et impose NOT NULL avec default '00:00:00'."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# ids
revision = "fix_timesheet_heure_not_null"
down_revision = "f7a69952931d"
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()

    # 1) Backfill
    conn.execute(sa.text(
        "UPDATE timesheet SET heure_debut='00:00:00' WHERE heure_debut IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE timesheet SET heure_fin='00:00:00' WHERE heure_fin IS NULL"
    ))

    # 2) Ajouter server_default puis NOT NULL
    with op.batch_alter_table('timesheet') as batch:
        batch.alter_column(
            'heure_debut',
            existing_type=mysql.TIME(),
            server_default=sa.text("'00:00:00'"),
            nullable=False
        )
        batch.alter_column(
            'heure_fin',
            existing_type=mysql.TIME(),
            server_default=sa.text("'00:00:00'"),
            nullable=False
        )

    # 3) (Optionnel) Retirer le server_default pour l’avenir
    with op.batch_alter_table('timesheet') as batch:
        batch.alter_column(
            'heure_debut',
            existing_type=mysql.TIME(),
            server_default=None
        )
        batch.alter_column(
            'heure_fin',
            existing_type=mysql.TIME(),
            server_default=None
        )

def downgrade():
    with op.batch_alter_table('timesheet') as batch:
        batch.alter_column('heure_fin', existing_type=mysql.TIME(), nullable=True)
        batch.alter_column('heure_debut', existing_type=mysql.TIME(), nullable=True)
