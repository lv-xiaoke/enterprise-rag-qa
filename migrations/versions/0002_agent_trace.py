"""Add authenticated business outcomes and tool execution history."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_runs',sa.Column('tool_events',sa.JSON(),nullable=False,server_default='[]'))
    op.add_column('chat_runs',sa.Column('intent',sa.JSON(),nullable=False,server_default='{}'))
    op.add_column('chat_runs',sa.Column('business_status',sa.String(30),nullable=False,server_default='unknown'))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a reviewed backup instead.')
