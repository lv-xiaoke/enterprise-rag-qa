"""Request-owned context shared by tool tasks; never stores mutable global identity."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunContext:
    user_id: str
    employee_id: str | None
    database: Any
    knowledge: Any
    sources: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    top_k: int = 3
    temperature: float | None = None
    model: Any = None
    budget: Any = None
    tool_events: list = field(default_factory=list)
    intent: dict = field(default_factory=dict)
    business_status: str = 'running'
    read_jobs: list = field(default_factory=list)
    event_sink: Any = None


current_run: ContextVar[RunContext | None] = ContextVar('agent_run', default=None)
