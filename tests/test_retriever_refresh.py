from test_documents import knowledge


def test_update_and_disable_refresh_both_retrieval_paths(clients, knowledge):
    admin = clients['admin']
    document = admin.post('/api/documents', files={'file': ('a.txt', '年假五天。'.encode())}).json()
    knowledge.process_queued()
    assert knowledge.retrieve('年假')[0]['excerpt'] == '年假五天。'
    admin.post(f'/api/documents/{document["id"]}/versions', files={'file': ('a.txt', '年假十天。'.encode())})
    knowledge.process_queued()
    assert {source['excerpt'] for source in knowledge.retrieve('年假')} == {'年假十天。'}
    admin.patch(f'/api/documents/{document["id"]}', json={'enabled': False})
    assert knowledge.retrieve('年假') == []
