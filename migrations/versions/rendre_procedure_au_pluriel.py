# migrations/versions/<hash>_rename_procedure_to_procedures.py
from alembic import op
import sqlalchemy as sa

# revision identifiers...
revision = 'mettre_procedure_au_pluriel'
down_revision = '470a7b730155'


def upgrade():
    with op.batch_alter_table('dossier', schema=None) as batch_op:
        batch_op.alter_column(
            'procedure',
            new_column_name='procedures',
            existing_type=sa.String(length=50),          # ← IMPORTANT
            existing_nullable=True            # ajuste à True/False selon ta colonne
        )

def downgrade():
    with op.batch_alter_table('dossier', schema=None) as batch_op:
        batch_op.alter_column(
            'procedures',
            new_column_name='procedure',
            existing_type=sa.String(length=50),
            existing_nullable=True
        )
