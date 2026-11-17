"""Structured local history and monitoring (frozen schema)."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('days', sa.Column('date', sa.String(10), primary_key=True), sa.Column('has_log', sa.Boolean(), nullable=False))
    op.create_table('detections',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('date', sa.String(10), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False), sa.Column('occurred_at', sa.String(26), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False), sa.Column('legacy_key', sa.String(), unique=True))
    op.create_table('bark_sessions',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('date', sa.String(10), nullable=False),
        sa.Column('started_at', sa.String(26), nullable=False), sa.Column('ended_at', sa.String(26), nullable=False),
        sa.Column('seconds', sa.Float(), nullable=False), sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('legacy_key', sa.String(), unique=True))
    op.create_table('music_events',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('date', sa.String(10), nullable=False),
        sa.Column('time', sa.String(8), nullable=False), sa.Column('track', sa.String(), nullable=False),
        sa.Column('status', sa.String(10), nullable=False), sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('legacy_key', sa.String(), unique=True))
    op.create_table('recordings',
        sa.Column('name', sa.String(), primary_key=True), sa.Column('date', sa.String(10), nullable=False),
        sa.Column('time', sa.String(8), nullable=False), sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False), sa.Column('modified', sa.Integer(), nullable=False))
    for table in ('detections', 'bark_sessions', 'music_events', 'recordings'):
        op.create_index(f'ix_{table}_date', table, ['date'])
    op.create_table('detector', sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('state', sa.String(32), nullable=False), sa.Column('updated_at', sa.Float(), nullable=False),
        sa.Column('last_audio_at', sa.Float()), sa.Column('tracking_since', sa.Float(), nullable=False))
    op.create_table('coverage', sa.Column('date', sa.String(10), primary_key=True),
        sa.Column('hour', sa.Integer(), primary_key=True), sa.Column('seconds', sa.Float(), nullable=False))
    op.create_table('legacy_imports', sa.Column('path', sa.String(), primary_key=True),
        sa.Column('signature', sa.String(), nullable=False))


def downgrade():
    for name in ('legacy_imports', 'coverage', 'detector', 'recordings', 'music_events', 'bark_sessions', 'detections', 'days'):
        op.drop_table(name)
