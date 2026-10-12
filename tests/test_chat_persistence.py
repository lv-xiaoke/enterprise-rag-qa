def test_business_history_survives_application_reconstruction(v1_app, clients):
    from api.server import create_app
    from fastapi.testclient import TestClient
    from test_chat_lifecycle import ScriptedAgent
    v1_app.state.agent = ScriptedAgent()
    client = clients['E1001']
    conversation = client.post('/api/conversations', json={}).json()
    client.post(f'/api/conversations/{conversation["id"]}/chat', json={
        'message': 'hi', 'client_request_id': 'persist'
    })
    rebuilt = create_app(v1_app.state.settings)
    recovered = TestClient(rebuilt)
    recovered.cookies.update(client.cookies)
    response = recovered.get(f'/api/conversations/{conversation["id"]}/messages')
    assert response.status_code == 200
    assert response.json()['items'][-1]['content'] == '你好 E1001'
