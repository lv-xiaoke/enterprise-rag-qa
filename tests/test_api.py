"""Authenticated API and SSE contracts; replaces retired anonymous endpoints."""
import asyncio
import json
import httpx
import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from test_agent_stream import RecordingModel
from agent.react_agent import ReactAgent
from api.routes.conversations import sse


class IdentityModel(RecordingModel):
    def _generate(self, messages, **kwargs):
        self.calls.append(list(messages))
        result = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
        message = (AIMessage(content=str(result.content)) if result else AIMessage(content='',
            tool_calls=[{'name':'get_employee_id','args':{},'id':'identity'}]))
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, **kwargs):
        await asyncio.sleep(0)
        return self._generate(messages, **kwargs)


def test_named_sse_preserves_chinese_and_escapes_newlines():
    encoded = sse('token', {'content':'你好\n世界'})
    assert encoded.count('\n\n') == 1
    assert json.loads(encoded.splitlines()[1][6:])['content'] == '你好\n世界'


def test_actual_graph_api_identity_and_error_contract(v1_app, clients):
    model = IdentityModel()
    v1_app.state.agent = ReactAgent(model=model, checkpointer=MemorySaver())
    client = clients['E1001']
    conversation = client.post('/api/conversations', json={}).json()
    response = client.post(f'/api/conversations/{conversation["id"]}/chat', json={
        'message':'who am I', 'client_request_id':'graph-api'})
    assert 'E1001' in response.text
    assert 'tool_result' in response.text
    assert '"status": "completed"' in response.text
    assert len(model.calls) == 2


def test_concurrent_graph_requests_do_not_share_identity(v1_app, clients):
    v1_app.state.agent = ReactAgent(model=IdentityModel(), checkpointer=MemorySaver())
    conversations = {name: client.post('/api/conversations', json={}).json()['id']
                     for name, client in clients.items() if name != 'admin'}
    async def run():
        async def ask(name):
            transport = httpx.ASGITransport(app=v1_app)
            async with httpx.AsyncClient(transport=transport, base_url='http://testserver',
                                            cookies=dict(clients[name].cookies), headers=dict(clients[name].headers)) as client:
                return await client.post(f'/api/conversations/{conversations[name]}/chat', json={
                    'message':'who', 'client_request_id':name})
        return await asyncio.gather(ask('E1001'), ask('E1002'))
    first, second = asyncio.run(run())
    assert 'E1001' in first.text and 'E1002' not in first.text
    assert 'E1002' in second.text and 'E1001' not in second.text


@pytest.mark.parametrize('message', ['', 'x' * 2001])
def test_invalid_message_is_rejected_before_generation(clients, message):
    client = clients['E1001']
    conversation = client.post('/api/conversations', json={}).json()
    response = client.post(f'/api/conversations/{conversation["id"]}/chat', json={
        'message':message, 'client_request_id':'invalid'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert response.headers['X-Request-ID']
