"""Explicit scripted model and toy embeddings for executor checks, not model quality."""
import hashlib
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class FixtureEmbeddings(Embeddings):
    def embed_query(self,text):
        return [byte/255 for byte in hashlib.sha256(text.encode()).digest()[:16]]

    def embed_documents(self,texts):
        return [self.embed_query(text) for text in texts]


class ScriptedBusinessModel(BaseChatModel):
    script: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    cursor: int = 0

    @property
    def _llm_type(self):
        return 'executor-fixture'

    def bind_tools(self,tools,**kwargs):
        return self

    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        self.calls.append(list(messages))
        if self.cursor>=len(self.script):
            raise RuntimeError('fixture script exhausted')
        item = self.script[self.cursor]
        self.cursor += 1
        if 'intent' in item:
            message = AIMessage(content='',tool_calls=[{'id':f'intent-{self.cursor}',
                'name':'classify_request','args':item['intent']}])
        elif 'tool' in item:
            message = AIMessage(content='',tool_calls=[{'id':f'call-{self.cursor}',
                'name':item['tool'],'args':item.get('args',{})}])
        else:
            message = AIMessage(content=item['answer'])
        return ChatResult(generations=[ChatGeneration(message=message)])
