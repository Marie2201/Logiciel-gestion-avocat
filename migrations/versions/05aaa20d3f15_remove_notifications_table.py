"""remove notifications table

Revision ID: 05aaa20d3f15
Revises: ae09f6eb6842
Create Date: 2025-08-09 21:53:52.175479

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05aaa20d3f15'
down_revision = 'ae09f6eb6842'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DROP TABLE IF EXISTS `notifications`
    """)
    pass


def downgrade():
    pass
