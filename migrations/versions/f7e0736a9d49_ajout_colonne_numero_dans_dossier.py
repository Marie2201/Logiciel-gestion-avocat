# migrations/versions/f7e0736a9d49_ajout_colonne_numero_dans_dossier.py

from alembic import op
import sqlalchemy as sa

# Identifiants Alembic
revision = "f7e0736a9d49"
down_revision = "05aaa20d3f15"
branch_labels = None
depends_on = None


def _col_exists(conn, table, column, schema=None):
    q = sa.text("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = COALESCE(:schema, DATABASE())
          AND TABLE_NAME = :table
          AND COLUMN_NAME = :column
    """)
    return conn.execute(q, {"schema": schema, "table": table, "column": column}).scalar() > 0


def _uq_exists(conn, table, constraint_name, schema=None):
    q = sa.text("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = COALESCE(:schema, DATABASE())
          AND TABLE_NAME = :table
          AND CONSTRAINT_TYPE = 'UNIQUE'
          AND CONSTRAINT_NAME = :cname
    """)
    return conn.execute(q, {"schema": schema, "table": table, "cname": constraint_name}).scalar() > 0


def upgrade():
    bind = op.get_bind()        # <-- c'est déjà une Connection
    conn = bind                 # <-- on l'utilise directement (pas de .connect())

    # 1) Ajouter les colonnes manquantes
    need_annee    = not _col_exists(conn, "dossier", "annee")
    need_sequence = not _col_exists(conn, "dossier", "sequence")
    need_numero   = not _col_exists(conn, "dossier", "numero")

    if need_annee or need_sequence or need_numero:
        with op.batch_alter_table("dossier") as batch:
            if need_annee:
                batch.add_column(sa.Column("annee", sa.Integer(), nullable=True))
            if need_sequence:
                batch.add_column(sa.Column("sequence", sa.Integer(), nullable=True))
            if need_numero:
                batch.add_column(sa.Column("numero", sa.String(20), nullable=True))

    # 2) Peupler les colonnes pour les lignes existantes qui en ont besoin
    has_created_at = _col_exists(conn, "dossier", "created_at")
    # Construire la SELECT selon la présence de created_at
    if has_created_at:
        select_sql = sa.text("""
            SELECT id,
                   COALESCE(YEAR(created_at), YEAR(CURDATE())) AS y,
                   annee, sequence, numero
            FROM dossier
            ORDER BY id
        """)
    else:
        select_sql = sa.text("""
            SELECT id,
                   YEAR(CURDATE()) AS y,
                   annee, sequence, numero
            FROM dossier
            ORDER BY id
        """)

    rows = conn.execute(select_sql).fetchall()

    # On attribue une séquence incrémentale par année uniquement pour les lignes incomplètes
    per_year_counter = {}
    to_fill = []
    for r in rows:
        curr_annee = r.annee
        curr_seq   = r.sequence
        curr_num   = r.numero
        if curr_annee is None or curr_seq is None or not curr_num:
            y_full = int(r.y)
            nxt = per_year_counter.get(y_full, 0) + 1
            per_year_counter[y_full] = nxt

            yy = str(y_full % 100).zfill(2)
            seq_str = f"{nxt:,}".replace(",", ".")   # 12345 -> "12.345"
            numero = f"{seq_str}/{yy}"
            to_fill.append((y_full, nxt, numero, r.id))

    if to_fill:
        upd = sa.text("UPDATE dossier SET annee=:a, sequence=:s, numero=:n WHERE id=:id")
        for a, s, n, _id in to_fill:
            conn.execute(upd, {"a": a, "s": s, "n": n, "id": _id})

    # 3) Contraintes NOT NULL + UNIQUE si absentes
    if not _uq_exists(conn, "dossier", "uq_dossier_annee_sequence"):
        with op.batch_alter_table("dossier") as batch:
            # mettre NOT NULL si la colonne existe (elle existe si on est ici)
            batch.alter_column("annee", existing_type=sa.Integer(), nullable=False)
            batch.alter_column("sequence", existing_type=sa.Integer(), nullable=False)
            batch.create_unique_constraint("uq_dossier_annee_sequence", ["annee", "sequence"])

    if not _uq_exists(conn, "dossier", "uq_dossier_numero"):
        with op.batch_alter_table("dossier") as batch:
            batch.alter_column("numero", existing_type=sa.String(20), nullable=False)
            batch.create_unique_constraint("uq_dossier_numero", ["numero"])


def downgrade():
    # Si tu dois réellement downgrader, on retire les contraintes puis les colonnes (si besoin).
    # Attention : selon l'état, le drop de colonnes peut échouer si elles n'existent pas.
    with op.batch_alter_table("dossier") as batch:
        # Ces drops échoueront silencieusement si la contrainte n'existe pas déjà (dans la plupart des MySQL récents,
        # sinon commente-les si tu n'as pas besoin de downgrade).
        batch.drop_constraint("uq_dossier_numero", type_="unique")
        batch.drop_constraint("uq_dossier_annee_sequence", type_="unique")

    bind = op.get_bind()
    conn = bind
    # Drop columns seulement si elles existent (sécurité)
    for col in ("numero", "sequence", "annee"):
        if _col_exists(conn, "dossier", col):
            with op.batch_alter_table("dossier") as batch:
                batch.drop_column(col)
