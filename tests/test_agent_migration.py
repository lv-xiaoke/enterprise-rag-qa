def test_trace_migration_preserves_existing_runs_and_messages(tmp_path, monkeypatch):
    from alembic.config import Config
    from alembic import command
    from backend.db import Database
    from backend.models import ChatRun
    from sqlalchemy import text
    url = f'sqlite:///{tmp_path / "migration.sqlite"}'
    monkeypatch.setenv('DATABASE_URL',url)
    config = Config('alembic.ini')
    command.upgrade(config,'0001')
    database = Database(url)
    with database.engine.begin() as db:
        db.execute(text("INSERT INTO users VALUES ('u','test','unused','employee','E1001','test')"))
        db.execute(text("INSERT INTO conversations VALUES ('c','u','old','thread',1,1)"))
        db.execute(text("INSERT INTO messages VALUES ('m','c','user','preserved','completed','[]',1)"))
        db.execute(text("INSERT INTO chat_runs (id,conversation_id,client_request_id,status,cancel_requested,started_at) VALUES ('r','c','old','completed',0,1)"))
    command.upgrade(config,'head')
    with database.session() as db:
        row = db.get(ChatRun,'r')
        assert row.tool_events == []
        assert row.intent == {}
        assert row.status == 'completed'
        assert db.scalar(text("SELECT content FROM messages WHERE id='m'"))=='preserved'
    database.engine.dispose()
