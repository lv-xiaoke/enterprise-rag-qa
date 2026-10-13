import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import pytest


@pytest.fixture
def v1_app(tmp_path, monkeypatch):
    # A missed model double must fail closed, never charge an existing local account.
    monkeypatch.setenv('DEEPSEEK_API_KEY', '')
    monkeypatch.setenv('DASHSCOPE_API_KEY', '')
    from api.server import create_app
    from backend.settings import Settings
    from backend.seed import seed_database
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "business.sqlite"}',
        runtime_dir=tmp_path / 'runtime',
        app_origin='http://testserver',
    )
    app = create_app(settings)
    app.state.database.create_schema()
    seed_database(app.state.database, 'Test-only-password!')
    return app


@pytest.fixture
def clients(v1_app):
    from fastapi.testclient import TestClient
    def login(username):
        client = TestClient(v1_app)
        csrf = client.get('/api/auth/csrf').json()['csrf_token']
        client.headers.update({'X-CSRF-Token': csrf, 'Origin': 'http://testserver'})
        response = client.post('/api/auth/login', json={
            'username': username, 'password': 'Test-only-password!'
        })
        assert response.status_code == 200, response.text
        return client
    return {name: login(name) for name in ['E1001', 'E1002', 'admin']}
