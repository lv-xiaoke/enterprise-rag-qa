from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.models import Base


class Database:
    def __init__(self, url):
        options = {}
        if url.startswith('sqlite'):
            options['connect_args'] = {'check_same_thread': False, 'timeout': 5}
            if ':memory:' in url:
                options['poolclass'] = StaticPool
            else:
                Path(url.split('///', 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        elif url.startswith('postgresql'):
            options['connect_args'] = {'connect_timeout':10,
                'options':'-c statement_timeout=10000 -c lock_timeout=5000'}
        self.engine = create_engine(url, pool_pre_ping=True, **options)
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def enable_foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self):
        """Local/test bootstrap. Production uses Alembic migrations."""
        Base.metadata.create_all(self.engine)
