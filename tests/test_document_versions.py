import pytest
from test_documents import knowledge


def test_failed_update_preserves_active_version_and_retry_is_idempotent(clients, knowledge):
    admin = clients['admin']
    document = admin.post('/api/documents', files={'file': ('a.txt', '年假五天。'.encode())}).json()
    knowledge.process_queued()
    admin.post(f'/api/documents/{document["id"]}/versions', files={'file': ('a.txt', b'\xff')})
    knowledge.process_queued()
    assert knowledge.retrieve('年假')[0]['excerpt'] == '年假五天。'
    listed = admin.get('/api/documents').json()['items'][0]
    assert listed['versions'][-1]['status'] == 'failed'
    duplicate = admin.post(f'/api/documents/{document["id"]}/versions', files={'file': ('a.txt', '年假五天。'.encode())})
    assert duplicate.status_code == 200
    assert len(admin.get('/api/documents').json()['items'][0]['versions']) == 2
