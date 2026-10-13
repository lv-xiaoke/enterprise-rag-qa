"""Typed business decisions. These express intent, never trusted identity."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

QueryType = Literal['leave_balance','reimbursement','projects','onboarding','weekly_report','all']


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    task: Literal['chat','knowledge','personal','combined','weekly_report','clarify']
    query_type: QueryType | None = None
    question: str = Field(default='', max_length=500)


class ToolOutcome(BaseModel):
    status: Literal['ok','denied','not_found','invalid','error']
    data: Any = None
    message: str = ''
    retryable: bool = False
    code: str | None = None


class PendingRequest(BaseModel):
    task: str
    missing_fields: list[str]
    question: str
