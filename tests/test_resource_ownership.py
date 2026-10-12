def test_conversation_is_not_readable_or_clearable_by_another_user(clients):
    own = clients['E1001'].post('/api/conversations', json={}).json()
    url = f'/api/conversations/{own["id"]}/messages'
    assert clients['E1002'].get(url).status_code == 404
    assert clients['E1002'].delete(url).status_code == 404
    assert clients['E1001'].get(url).status_code == 200
    assert clients['E1002'].get('/api/conversations').json()['items'] == []


def test_user_cannot_impersonate_in_chat_payload(clients):
    own = clients['E1001'].post('/api/conversations', json={}).json()
    response = clients['E1001'].post(f'/api/conversations/{own["id"]}/chat', json={
        'message': 'hello', 'client_request_id': 'one', 'employee_id': 'E1002'
    })
    assert response.status_code == 422
