"""Initial business schema, frozen independently of future ORM changes."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('username', sa.String(80), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False), sa.Column('role', sa.String(20), nullable=False),
        sa.Column('employee_id', sa.String(40), unique=True), sa.Column('name', sa.String(120), nullable=False))
    op.create_table('auth_sessions', sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False), sa.Column('revoked', sa.Boolean(), nullable=False))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_table('conversations', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(120), nullable=False), sa.Column('thread_id', sa.String(32), nullable=False, unique=True),
        sa.Column('created_at', sa.Float(), nullable=False), sa.Column('updated_at', sa.Float(), nullable=False))
    op.create_index('ix_conversation_user_updated', 'conversations', ['user_id', 'updated_at'])
    op.create_table('messages', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('conversation_id', sa.String(32), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False), sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False))
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_table('chat_runs', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('conversation_id', sa.String(32), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('client_request_id', sa.String(80), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False), sa.Column('error_code', sa.String(80)),
        sa.Column('started_at', sa.Float(), nullable=False), sa.Column('ended_at', sa.Float()),
        sa.Column('ttft_ms', sa.Float()), sa.Column('total_ms', sa.Float()), sa.Column('usage', sa.JSON()),
        sa.UniqueConstraint('conversation_id', 'client_request_id'))
    op.create_index('ix_chat_runs_conversation_id', 'chat_runs', ['conversation_id'])
    op.create_table('employee_records', sa.Column('employee_id', sa.String(40), primary_key=True),
        sa.Column('data', sa.JSON(), nullable=False))
    op.create_table('weekly_reports', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(120), nullable=False), sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False), sa.Column('updated_at', sa.Float(), nullable=False))
    op.create_index('ix_report_user_updated', 'weekly_reports', ['user_id', 'updated_at'])
    op.create_table('documents', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('title', sa.String(200), nullable=False), sa.Column('active_version_id', sa.String(32)),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('uploaded_by', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False))
    op.create_table('document_versions', sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('document_id', sa.String(32), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False), sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('path', sa.Text(), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_code', sa.String(80)), sa.UniqueConstraint('document_id', 'content_hash'),
        sa.UniqueConstraint('document_id', 'number'))
    op.create_index('ix_document_versions_document_id', 'document_versions', ['document_id'])


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore an explicitly reviewed backup instead.')
