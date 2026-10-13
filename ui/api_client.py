"""A cookie jar belongs to one Streamlit session, never to a global cache."""
import json
import httpx


class ApiError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class AuthenticationExpired(ApiError):
    pass


class AgentApiClient:
    def __init__(self, base_url, origin, *, transport=None):
        self.http = httpx.Client(base_url=base_url.rstrip('/') + '/api/',
            headers={'Origin': origin}, timeout=httpx.Timeout(140, connect=10),
            transport=transport, trust_env=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.http.cookies.clear()
        self.http.close()

    def _check(self, response):
        if response.status_code == 401:
            self.http.cookies.clear()
            self.http.headers.pop('X-CSRF-Token', None)
            raise AuthenticationExpired('登录已失效，请重新登录', 401)
        if response.is_error:
            try:
                message = response.json().get('error', {}).get('message', '请求失败')
            except (ValueError, AttributeError):
                message = '服务请求失败'
            raise ApiError(message, response.status_code)

    def _request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError('无法连接服务，请检查 API 地址与服务状态') from exc
        self._check(response)
        return response.json()

    def login(self, username, password):
        self.http.cookies.clear()
        csrf = self._request('GET', 'auth/csrf')['csrf_token']
        self.http.headers['X-CSRF-Token'] = csrf
        return self._request('POST', 'auth/login', json={'username':username,'password':password})

    def me(self):
        return self._request('GET', 'auth/me')

    def logout(self):
        try:
            self._request('POST', 'auth/logout')
        finally:
            self.close()

    def _pages(self, path):
        items = []
        while True:
            page = self._request('GET', path, params={'limit':100,'offset':len(items)})
            rows = page['items']
            items.extend(rows)
            if not rows or len(items) >= page['total']:
                return items

    def list_conversations(self):
        return self._pages('conversations')

    def create_conversation(self, title='新对话'):
        return self._request('POST','conversations',json={'title':title})

    def list_messages(self, conversation_id):
        return self._pages(f'conversations/{conversation_id}/messages')

    def list_runs(self, conversation_id):
        return self._pages(f'conversations/{conversation_id}/runs')

    def clear_messages(self, conversation_id):
        return self._request('DELETE',f'conversations/{conversation_id}/messages')

    def stream_chat(self, conversation_id, message, client_request_id, **options):
        body = {'message':message,'client_request_id':client_request_id, **options}
        terminal = False
        try:
            with self.http.stream('POST',f'conversations/{conversation_id}/chat',json=body) as response:
                if response.is_error:
                    response.read()
                self._check(response)
                kind, data = '', []
                for line in response.iter_lines():
                    if not line:
                        if data:
                            try:
                                payload = json.loads('\n'.join(data))
                            except ValueError as exc:
                                raise ApiError('服务事件格式错误') from exc
                            terminal = terminal or kind == 'done'
                            yield {**payload, 'type':kind}
                        kind, data = '', []
                    elif line.startswith('event:'):
                        kind = line[6:].strip()
                    elif line.startswith('data:'):
                        data.append(line[5:].lstrip())
        except httpx.HTTPError as exc:
            raise ApiError('生成连接中断，请查看历史后重试') from exc
        if not terminal:
            raise ApiError('生成连接中断，请查看历史后重试')

    def cancel(self, run_id):
        return self._request('POST',f'chat-runs/{run_id}/cancel')

    def list_documents(self):
        return self._pages('documents')

    def upload(self, name, content):
        return self._request('POST','documents',files={'file':(name,content)})

    def retry_document(self, document_id):
        return self._request('POST',f'documents/{document_id}/retry')

    def list_reports(self):
        return self._pages('weekly-reports')

    def save_report(self, title, content):
        return self._request('POST','weekly-reports',json={'title':title,'content':content})
