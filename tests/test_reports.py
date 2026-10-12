def test_report_crud_and_ownership(clients):
    a, b = clients['E1001'], clients['E1002']
    response = a.post('/api/weekly-reports', json={'title': '本周工作', 'content': '完成知识库改造'})
    assert response.status_code == 201
    report = response.json()
    url = f'/api/weekly-reports/{report["id"]}'
    assert b.get(url).status_code == 404
    assert b.patch(url, json={'content': '改写'}).status_code == 404
    assert b.delete(url).status_code == 404
    assert a.patch(url, json={'content': '补充测试'}).json()['content'] == '补充测试'
    assert a.get('/api/weekly-reports?limit=1').json()['total'] == 1
    assert a.delete(url).status_code == 200
    assert a.get(url).status_code == 404
