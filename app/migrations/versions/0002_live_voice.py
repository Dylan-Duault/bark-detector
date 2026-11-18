"""Store the start of live voice transmissions."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'live_voice_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.String(10), nullable=False),
        sa.Column('time', sa.String(8), nullable=False),
    )
    op.create_index('ix_live_voice_events_date', 'live_voice_events', ['date'])


def downgrade():
    op.drop_table('live_voice_events')
