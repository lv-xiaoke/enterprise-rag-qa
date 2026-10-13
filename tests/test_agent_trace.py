from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from test_agent_stream import RecordingModel
from test_agent_clarification import call, decision
from test_chat_lifecycle import events


def test_real_business_trace_persists_and_is_owned(v1_app, clients):
    from agent.business_agent import BusinessAgent
    script = [decision('personal',query_type='leave_balance'),call('get_employee_id',ident='identity'),
        call('fetch_employee_records',{'employee_id':'E1001','query_type':'leave_balance'},'leave'),AIMessage(content='已查询本人年假')]
    v1_app.state.agent = BusinessAgent(model=RecordingModel(script=script),checkpointer=MemorySaver())
    a,b = clients['E1001'],clients['E1002']
    cid = a.post('/api/conversations',json={}).json()['id']
    response = a.post(f'/api/conversations/{cid}/chat',json={'message':'查我的年假','client_request_id':'one'})
    assert events(response)[-1][1]['status']=='completed'
    assert events(response)[-1][1]['business_status']=='completed'
    saved = a.get(f'/api/conversations/{cid}/runs')
    assert saved.status_code==200
    row = saved.json()['items'][0]
    assert row['intent']['query_type']=='leave_balance'
    results = [event for event in row['tool_events'] if event['type']=='tool_result']
    assert [event['tool_call_id'] for event in results] == ['identity','leave']
    assert all(event['status']=='ok' for event in results)
    assert b.get(f'/api/conversations/{cid}/runs').status_code==404


def test_no_evidence_is_failed_and_never_generates_success(v1_app, clients):
    from agent.business_agent import BusinessAgent
    class EmptyKnowledge:
        def retrieve(self,query,k=3): return []
    v1_app.state.knowledge = EmptyKnowledge()
    model = RecordingModel(script=[decision('knowledge'),call('rag_summarize',{'query':'不存在制度'}),AIMessage(content='伪造成功')])
    v1_app.state.agent = BusinessAgent(model=model,checkpointer=MemorySaver())
    a = clients['E1001']
    cid = a.post('/api/conversations',json={}).json()['id']
    result = a.post(f'/api/conversations/{cid}/chat',json={'message':'不存在制度','client_request_id':'one'})
    assert events(result)[-1][1]['status']=='failed'
    assert any(kind=='error' and value['code']=='NO_EVIDENCE' for kind,value in events(result))
    assert '伪造成功' not in result.text
    assert model.cursor==2


def test_pending_request_survives_checkpoint_reconnection(tmp_path):
    import asyncio
    from backend.checkpoints import Checkpoints
    from backend.settings import Settings
    from agent.business_agent import BusinessAgent
    async def exercise():
        settings = Settings(runtime_dir=tmp_path)
        first = Checkpoints(settings)
        agent = BusinessAgent(model=RecordingModel(script=[decision('personal')]),checkpointer=await first.get())
        _ = [e async for e in agent.astream_events('查状态','pending-thread')]
        await first.close()
        second = Checkpoints(settings)
        model = RecordingModel(script=[decision('chat'),AIMessage(content='新话题')])
        agent = BusinessAgent(model=model,checkpointer=await second.get())
        _ = [e async for e in agent.astream_events('不查了','pending-thread')]
        assert 'query_type' in str(model.calls[0][0].content)
        await second.close()
    asyncio.run(exercise())
