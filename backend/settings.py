from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = 'sqlite:///runtime/business.sqlite'
    runtime_dir: Path = field(default_factory=lambda: Path('runtime'))
    app_origin: str = 'http://127.0.0.1:5173'
    cookie_secure: bool = False
    session_hours: int = 24
    chat_timeout_seconds: float = 120
    tool_timeout_seconds: float = 30

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(override=False)
        return cls(
            database_url=os.getenv('DATABASE_URL', cls.database_url),
            runtime_dir=Path(os.getenv('RUNTIME_DIR', 'runtime')),
            app_origin=os.getenv('APP_ORIGIN', cls.app_origin).rstrip('/'),
            cookie_secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
            chat_timeout_seconds=float(os.getenv('CHAT_TIMEOUT_SECONDS', '120')),
            tool_timeout_seconds=float(os.getenv('TOOL_TIMEOUT_SECONDS','30')),
        )
