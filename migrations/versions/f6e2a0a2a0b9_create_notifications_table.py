"""create notifications table

Revision ID: f6e2a0a2a0b9
Revises: f597a20d632f
Create Date: 2025-08-09 17:44:51.058345

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'f6e2a0a2a0b9'
down_revision = 'f597a20d632f'


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table('notifications'):
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer, nullable=False),
            sa.Column('title', sa.String(120), nullable=False),
            sa.Column('message', sa.String(500), nullable=False),
            sa.Column('url', sa.String(300)),
            sa.Column('is_read', sa.Boolean),
            sa.Column('created_at', sa.DateTime),
        )
        op.create_foreign_key(
            'fk_notifications_user_id_users',
            'notifications', 'users',
            ['user_id'], ['id'],
            ondelete='CASCADE'
        )

def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table('notifications'):
        op.drop_constraint('fk_notifications_user_id_users', 'notifications', type_='foreignkey')
        op.drop_table('notifications')
