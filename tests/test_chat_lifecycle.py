import json
from contextlib import contextmanager
from backend.models import ChatRun


class ScriptedAgent:
    async def astream_events(self, message, thread_id):
        from agent.tools.agent_tools import get_employee_id
        if message == 'error':
            raise RuntimeError('secret upstream internal detail')
        yield {'type': 'tool_call', 'name': 'get_employee_id', 'args': {}}
        identity = get_employee_id.invoke({})
        yield {'type': 'tool_result', 'name': 'get_employee_id', 'content': identity}
        yield {'type': 'token', 'content': f'你好 {identity}'}


def events(response):
    return [(block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
            for block in response.text.strip().split('\n\n') if block.startswith('event:')]


def test_stream_persists_messages_and_uses_authenticated_identity(v1_app, clients):
    v1_app.state.agent = ScriptedAgent()
    a = clients['E1001']
    conversation = a.post('/api/conversations', json={}).json()
    url = f'/api/conversations/{conversation["id"]}/chat'
    response = a.post(url, json={'message': 'who', 'client_request_id': 'one'})
    assert response.status_code == 200
    output = events(response)
    assert output[0][0] == 'start'
    assert output[-1][1]['status'] == 'completed'
    messages = a.get(f'/api/conversations/{conversation["id"]}/messages').json()['items']
    assert [m['role'] for m in messages] == ['user', 'assistant']
    assert messages[-1]['content'] == '你好 E1001'
    assert a.post(url, json={'message': 'who', 'client_request_id': 'one'}).status_code == 409
    assert clients['E1002'].post(f'/api/chat-runs/{output[0][1]["run_id"]}/cancel').status_code == 404


def test_failure_is_visible_without_exposing_internal_exception(v1_app, clients):
    v1_app.state.agent = ScriptedAgent()
    a = clients['E1001']
    conversation = a.post('/api/conversations', json={}).json()
    response = a.post(f'/api/conversations/{conversation["id"]}/chat', json={
        'message': 'error', 'client_request_id': 'error'
    })
    output = events(response)
    assert any(name == 'error' for name, _ in output)
    assert output[-1][1]['status'] == 'failed'
    assert 'secret upstream' not in response.text


def test_busy_conversation_rejects_new_run_and_clear(v1_app, clients):
    a = clients['E1001']
    conversation = a.post('/api/conversations', json={}).json()
    with v1_app.state.database.session() as db:
        db.add(ChatRun(conversation_id=conversation['id'], client_request_id='busy'))
        db.commit()
    base = f'/api/conversations/{conversation["id"]}'
    assert a.post(base + '/chat', json={'message': 'hello', 'client_request_id': 'two'}).status_code == 409
    assert a.delete(base + '/messages').status_code == 409


def test_timeout_is_failed_and_persists_error_code(v1_app, clients):
    import asyncio
    from dataclasses import replace
    class SlowAgent:
        async def astream_events(self, message, thread_id):
            await asyncio.sleep(2)
            yield {'type': 'token', 'content': 'too late'}
    v1_app.state.settings = replace(v1_app.state.settings, chat_timeout_seconds=.03)
    v1_app.state.agent = SlowAgent()
    a = clients['E1001']
    conversation = a.post('/api/conversations', json={}).json()['id']
    response = a.post(f'/api/conversations/{conversation}/chat', json={'message':'wait','client_request_id':'timeout'})
    assert any(kind == 'error' and value['code'] == 'TIMEOUT' for kind, value in events(response))
    assert events(response)[-1][1]['status'] == 'failed'


def test_startup_marks_stale_runs_and_processing_documents(v1_app, clients):
    from fastapi.testclient import TestClient
    from backend.models import Conversation, KnowledgeDocument, DocumentVersion
    conversation = clients['E1001'].post('/api/conversations', json={}).json()['id']
    with v1_app.state.database.session() as db:
        db.add(ChatRun(id='stale', conversation_id=conversation, client_request_id='stale'))
        document = KnowledgeDocument(title='stale.txt', uploaded_by=db.get(Conversation,conversation).user_id)
        db.add(document); db.flush()
        db.add(DocumentVersion(id='stale-version', document_id=document.id, number=1, content_hash='x', path='unused', status='processing'))
        db.commit()
    with TestClient(v1_app):
        with v1_app.state.database.session() as db:
            assert db.get(ChatRun,'stale').status == 'interrupted'
            assert db.get(DocumentVersion,'stale-version').error_code == 'INTERRUPTED'
