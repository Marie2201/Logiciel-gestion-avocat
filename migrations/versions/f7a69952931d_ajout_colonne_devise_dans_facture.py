"""ajout colonne devise dans facture

Revision ID: f7a69952931d
Revises: 731d277fd471
Create Date: 2025-08-20 13:45:01.046044
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f7a69952931d'
down_revision = '731d277fd471'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- Ajouter facture.devise si elle n'existe pas déjà ---
    facture_cols = [c['name'] for c in insp.get_columns('facture')]
    if 'devise' not in facture_cols:
        with op.batch_alter_table('facture') as batch_op:
            batch_op.add_column(sa.Column('devise', sa.String(length=8), nullable=True))

    # IMPORTANT : ne rien modifier dans 'timesheet' ici
    # (on supprime les alter_column auto-générés qui rendaient les champs NOT NULL)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    facture_cols = [c['name'] for c in insp.get_columns('facture')]
    if 'devise' in facture_cols:
        with op.batch_alter_table('facture') as batch_op:
            batch_op.drop_column('devise')

    # Rien à downgrader côté timesheet puisqu'on n'y a rien touché
