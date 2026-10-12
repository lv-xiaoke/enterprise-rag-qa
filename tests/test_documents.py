import pytest


@pytest.fixture
def knowledge(v1_app, tmp_path):
    from backend.documents import KnowledgeService
    from test_ingest_ledger import FakeEmbeddings
    service = KnowledgeService(v1_app.state.database, v1_app.state.settings,
                               embedding=FakeEmbeddings(), collection_name='test_versions')
    v1_app.state.knowledge = service
    return service


def test_upload_limits_and_admin_boundary(clients, knowledge):
    assert clients['E1001'].post('/api/documents', files={'file': ('a.txt', b'hi')}).status_code == 403
    assert clients['admin'].post('/api/documents', files={'file': ('a.exe', b'hi')}).status_code == 422
    assert clients['admin'].post('/api/documents', files={'file': ('a.txt', b'\xff')}).status_code == 201


def test_upload_and_source_access(clients, knowledge):
    admin = clients['admin']
    response = admin.post('/api/documents', files={'file': ('制度.txt', '年假为五天。'.encode())})
    assert response.status_code == 201
    document = response.json()
    knowledge.process_queued()
    sources = knowledge.retrieve('年假')
    assert sources and sources[0]['document_id'] == document['id']
    source = sources[0]
    url = f'/api/sources/{source["version_id"]}/{source["chunk_id"]}'
    assert clients['E1001'].get(url).json()['content'] == '年假为五天。'
    assert 'path' not in clients['E1001'].get(url).text
