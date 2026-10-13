import json
import httpx
import pytest


def test_clients_keep_login_cookies_private_and_send_csrf():
    from ui.api_client import AgentApiClient
    def respond(request):
        if request.url.path.endswith('/csrf'):
            return httpx.Response(200, json={'csrf_token': 'csrf-a'},
                                  headers={'set-cookie': 'csrf_token=csrf-a; Path=/'})
        if request.url.path.endswith('/login'):
            assert request.headers['origin'] == 'http://testserver'
            assert request.headers['x-csrf-token'] == 'csrf-a'
            name = json.loads(request.content)['username']
            return httpx.Response(200, json={'username': name},
                                  headers={'set-cookie': f'session={name}; Path=/'})
        return httpx.Response(200, json={'cookie': request.headers.get('cookie', '')})
    a = AgentApiClient('http://testserver', 'http://testserver', transport=httpx.MockTransport(respond))
    b = AgentApiClient('http://testserver', 'http://testserver', transport=httpx.MockTransport(respond))
    a.login('E1001', 'password')
    b.login('E1002', 'password')
    assert 'session=E1001' in a.me()['cookie']
    assert 'E1002' not in a.me()['cookie']
    assert 'session=E1002' in b.me()['cookie']
    a.close(); b.close()


def test_expired_identity_clears_client_credentials():
    from ui.api_client import AgentApiClient, AuthenticationExpired
    client = AgentApiClient('http://testserver', 'http://testserver',
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={})))
    client.http.cookies.set('session', 'old')
    with pytest.raises(AuthenticationExpired):
        client.me()
    assert not client.http.cookies
    client.close()


def test_stream_detects_missing_terminal_and_normalizes_sse():
    from ui.api_client import AgentApiClient, ApiError
    content = 'event: token\ndata: {"content":"hello"}\n\nevent: done\ndata: {"status":"completed"}\n\n'
    client = AgentApiClient('http://testserver', 'http://testserver',
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=content)))
    events = list(client.stream_chat('conversation', 'hello', 'req-1'))
    assert events == [{'type':'token','content':'hello'}, {'type':'done','status':'completed'}]
    content = 'event: token\ndata: {"content":"partial"}\n\n'
    with pytest.raises(ApiError, match='中断'):
        list(client.stream_chat('conversation', 'hello', 'req-2'))
    client.close()


def test_pagination_collects_later_history_pages():
    from ui.api_client import AgentApiClient
    def respond(request):
        offset = int(request.url.params.get('offset', '0'))
        return httpx.Response(200, json={'items':[{'id':str(offset)}], 'total':2})
    with AgentApiClient('http://testserver','http://testserver',transport=httpx.MockTransport(respond)) as client:
        assert client.list_messages('c') == [{'id':'0'}, {'id':'1'}]
