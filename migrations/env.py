from alembic import context
from backend.db import Database
from backend.models import Base
from backend.settings import Settings

settings = Settings.from_env()


def include_name(name, type_, parent_names):
    # LangGraph owns checkpoint tables and their migration lifecycle.
    return type_ != 'table' or name in Base.metadata.tables


if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True, include_name=include_name)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = Database(settings.database_url).engine
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, include_name=include_name)
        with context.begin_transaction():
            context.run_migrations()
