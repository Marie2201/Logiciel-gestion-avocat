"""timesheet forfait

Revision ID: 731d277fd471
Revises: f7e0736a9d49
Create Date: 2025-08-18 15:19:59.071992

"""
from alembic import op
import sqlalchemy as sa

revision = '731d277fd471'
down_revision = 'f7e0736a9d49' 
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()

    # Ajouter colonnes si absentes
    def col_exists(table, col):
        q = sa.text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :t AND COLUMN_NAME = :c
        """)
        return bind.execute(q, {"t": table, "c": col}).scalar() > 0

    with op.batch_alter_table('timesheet') as batch:
        if not col_exists('timesheet', 'type_facturation'):
            batch.add_column(sa.Column('type_facturation', sa.String(10), nullable=False, server_default='horaire'))
        if not col_exists('timesheet', 'montant_forfait'):
            batch.add_column(sa.Column('montant_forfait', sa.Numeric(10, 2), nullable=True))

        # Assouplir ces colonnes (NULL autorisé pour forfait)
        batch.alter_column('heure_debut', existing_type=sa.Time(), nullable=True)
        batch.alter_column('heure_fin', existing_type=sa.Time(), nullable=True)
        batch.alter_column('taux_horaire', existing_type=sa.Float(), nullable=True)
        batch.alter_column('duree_heures', existing_type=sa.Float(), nullable=True)

    # Retirer le server_default une fois posée
    with op.batch_alter_table('timesheet') as batch:
        batch.alter_column('type_facturation', existing_type=sa.String(10), server_default=None)


def downgrade():
    with op.batch_alter_table('timesheet') as batch:
        # Si besoin
        batch.drop_column('montant_forfait')
        batch.drop_column('type_facturation')