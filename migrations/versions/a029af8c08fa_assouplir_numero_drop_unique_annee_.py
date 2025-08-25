"""Assouplir numero: drop unique(annee,sequence), unique(client,numero,procedures)

Revision ID: a029af8c08fa
Revises: 18df504bdd40
Create Date: 2025-08-25 17:32:50.347344

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a029af8c08fa'
down_revision = '18df504bdd40'
branch_labels = None
depends_on = None


TABLE = 'dossier'

def upgrade():
    # 1) Supprimer en sécurité tout index/contrainte d’unicité (annee, sequence)
    #    On essaie plusieurs noms possibles, sans planter si absent.
    def safe_drop_index(name):
        try:
            op.execute(sa.text(f"ALTER TABLE `{TABLE}` DROP INDEX `{name}`"))
        except Exception:
            pass

    def safe_drop_unique(name):
        # MySQL implémente l’unique comme index → DROP INDEX suffit
        safe_drop_index(name)

    for name in (
        'uq_dossier_annee_sequence',          # ton nom le plus probable (déjà supprimé une 1ère fois)
        'ux_dossier_annee_sequence',
        'dossier_annee_sequence_uindex',
        'annee_sequence',
        'ix_dossier_annee_sequence'
    ):
        safe_drop_unique(name)

    # 2) Créer/assurer l’unicité sur (client_id, numero, procedures)
    #    Si ta colonne s’appelle procedure_id, adapte la liste ci-dessous.
    try:
        op.create_unique_constraint(
            'uq_dossier_client_numero_procedures',
            TABLE,
            ['client_id', 'numero', 'procedures']
        )
    except Exception:
        pass

    # 3) Index non-unique utile sur numero (au cas où)
    try:
        op.create_index('ix_dossier_numero', TABLE, ['numero'], unique=False)
    except Exception:
        pass


def downgrade():
    # Inverse : on enlève l’unique (client, numero, procedures)
    try:
        op.drop_constraint('uq_dossier_client_numero_procedures', TABLE, type_='unique')
    except Exception:
        pass
    try:
        op.drop_index('ix_dossier_numero', table_name=TABLE)
    except Exception:
        pass

    # On remet l’ancienne contrainte globale si besoin
    try:
        op.create_unique_constraint('uq_dossier_annee_sequence', TABLE, ['annee', 'sequence'])
    except Exception:
        pass