from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from api.server import create_app
from test_agent_stream import RecordingModel
from test_agent_clarification import decision


def test_real_api_checkpoint_path_preserves_history_across_app_restart(v1_app, monkeypatch):
    import model.factory
    first_model = RecordingModel(script=[decision('chat'),AIMessage(content='第一轮已保存')])
    monkeypatch.setattr(model.factory, 'build_chat_model', lambda: first_model)
    with TestClient(v1_app) as first:
        csrf = first.get('/api/auth/csrf').json()['csrf_token']
        first.headers.update({'Origin':'http://testserver','X-CSRF-Token':csrf})
        assert first.post('/api/auth/login',json={'username':'E1001','password':'Test-only-password!'}).status_code == 200
        conversation = first.post('/api/conversations',json={}).json()['id']
        response = first.post(f'/api/conversations/{conversation}/chat',json={'message':'记住我的项目代号 maple','client_request_id':'first'})
        assert '第一轮已保存' in response.text
        cookies = dict(first.cookies)
    second_model = RecordingModel(script=[decision('chat'),AIMessage(content='重启后继续')])
    monkeypatch.setattr(model.factory, 'build_chat_model', lambda: second_model)
    second_app = create_app(v1_app.state.settings)
    with TestClient(second_app) as second:
        second.cookies.update(cookies)
        second.headers.update({'Origin':'http://testserver','X-CSRF-Token':csrf})
        response = second.post(f'/api/conversations/{conversation}/chat',json={'message':'上次项目代号是什么','client_request_id':'second'})
        assert '重启后继续' in response.text
        assert any('maple' in str(m.content) for m in second_model.calls[0])
        history = second.get(f'/api/conversations/{conversation}/messages').json()['items']
        assert len(history) == 4
