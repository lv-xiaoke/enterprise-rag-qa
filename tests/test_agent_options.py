from test_chat_lifecycle import ScriptedAgent, events


def test_options_are_validated_and_do_not_add_identity_fields(v1_app, clients):
    v1_app.state.agent = ScriptedAgent()
    a = clients['E1001']
    cid = a.post('/api/conversations',json={}).json()['id']
    response = a.post(f'/api/conversations/{cid}/chat',json={
        'message':'who','client_request_id':'valid','top_k':5,'temperature':0.2})
    assert response.status_code == 200
    assert events(response)[-1][1]['status'] == 'completed'
    for field, value in [('top_k',100), ('temperature',-1), ('model_name','untrusted-model'), ('thread_id','forged')]:
        response = a.post(f'/api/conversations/{cid}/chat',json={
            'message':'who','client_request_id':field,field:value})
        assert response.status_code == 422


def test_rag_model_uses_run_settings_without_shared_mutation(v1_app):
    from agent.runtime import RunContext
    from api.schemas import ChatRequest
    options = ChatRequest(message='hello',client_request_id='r',top_k=7,temperature=.4)
    context = RunContext('u','E1001',None,None,top_k=options.top_k,temperature=options.temperature)
    other = RunContext('v','E1002',None,None)
    assert context.top_k == 7
    assert other.top_k == 3
    assert other.temperature is None
