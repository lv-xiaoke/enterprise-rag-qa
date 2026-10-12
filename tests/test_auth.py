from fastapi.testclient import TestClient


def test_health_and_import_need_no_model(v1_app):
    client = TestClient(v1_app)
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/ready').status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/chat', json={'employee_id': 'E1001', 'message': 'hi'}).status_code == 404


def test_login_requires_csrf_and_origin(v1_app):
    client = TestClient(v1_app)
    payload = {'username': 'E1001', 'password': 'Test-only-password!'}
    assert client.post('/api/auth/login', json=payload).status_code == 403
    token = client.get('/api/auth/csrf').json()['csrf_token']
    assert client.post('/api/auth/login', json=payload, headers={
        'X-CSRF-Token': token, 'Origin': 'https://evil.example'
    }).status_code == 403
    assert client.post('/api/auth/login', json=payload, headers={
        'X-CSRF-Token': token, 'Origin': 'http://testserver'
    }).status_code == 200


def test_wrong_password_and_logout(v1_app, clients):
    client = clients['E1001']
    assert client.get('/api/auth/me').json()['employee_id'] == 'E1001'
    assert client.post('/api/auth/login', json={
        'username': 'E1001', 'password': 'wrong'
    }).status_code == 401
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_roles_and_no_password_exposure(clients):
    assert clients['E1001'].get('/api/documents').status_code == 403
    me = clients['admin'].get('/api/auth/me').json()
    assert me['role'] == 'admin'
    assert 'password_hash' not in me


def test_expired_session_is_rejected(v1_app, clients):
    from backend.models import AuthSession
    with v1_app.state.database.session() as db:
        for row in db.query(AuthSession).all():
            row.expires_at = 0
        db.commit()
    assert clients['E1001'].get('/api/auth/me').status_code == 401
