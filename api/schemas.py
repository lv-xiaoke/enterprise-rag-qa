from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ConversationRequest(StrictModel):
    title: str = Field(default='新对话', min_length=1, max_length=120)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    client_request_id: str = Field(min_length=1, max_length=80)


class ReportRequest(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=50000)


class ReportPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=50000)


class DocumentPatch(StrictModel):
    enabled: bool
