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


def test_tool_start_is_durable_before_business_operation(v1_app, clients):
    from agent.business_agent import BusinessAgent
    from agent.execution import execute_business_tool
    from backend.models import ChatRun
    from sqlalchemy import select
    observed = []
    async def operation(name,args):
        with v1_app.state.database.session() as db:
            run = db.scalar(select(ChatRun).where(ChatRun.status=='running'))
            starts = [e for e in run.tool_events if e['type']=='tool_call']
            assert starts and starts[-1]['name']==name
            observed.append(name)
        return await execute_business_tool(name,args)
    script = [decision('personal',query_type='leave_balance'),call('get_employee_id'),
        call('fetch_employee_records',{'employee_id':'E1001','query_type':'leave_balance'},'leave'),AIMessage(content='6')]
    v1_app.state.agent = BusinessAgent(model=RecordingModel(script=script),checkpointer=MemorySaver(),tool_executor=operation)
    a = clients['E1001']
    cid = a.post('/api/conversations',json={}).json()['id']
    response = a.post(f'/api/conversations/{cid}/chat',json={'message':'查年假','client_request_id':'durable'})
    assert events(response)[-1][1]['status']=='completed'
    assert observed==['get_employee_id','fetch_employee_records']


def test_restart_reconciles_unmatched_tool_and_business_status(v1_app, clients):
    from fastapi.testclient import TestClient
    from backend.models import ChatRun
    cid = clients['E1001'].post('/api/conversations',json={}).json()['id']
    start = {'type':'tool_call','name':'get_employee_id','tool_call_id':'pending-id',
             'attempt':1,'args':{},'status':'running'}
    with v1_app.state.database.session() as db:
        db.add(ChatRun(id='interrupted-trace',conversation_id=cid,client_request_id='stale',tool_events=[start]))
        db.commit()
    with TestClient(v1_app):
        saved = clients['E1001'].get(f'/api/conversations/{cid}/runs').json()['items'][0]
        assert saved['status']==saved['business_status']=='interrupted'
        assert saved['tool_events'][0]==start
        result = saved['tool_events'][-1]
        assert result['type']=='tool_result'
        assert result['status']=='interrupted'
        assert result['tool_call_id']=='pending-id'
        assert result['error_code']=='INTERRUPTED'


def test_late_trace_commit_cannot_overwrite_cancelled_run(v1_app, clients,monkeypatch):
    import threading
    from sqlalchemy.orm import Session,sessionmaker
    from backend.conversations import record_tool_event,finish_run
    from backend.models import ChatRun
    cid = clients['E1001'].post('/api/conversations',json={}).json()['id']
    database = v1_app.state.database
    with database.session() as db:
        db.add(ChatRun(id='late-write',conversation_id=cid,client_request_id='late'))
        db.commit()
    selected,release = threading.Event(),threading.Event()
    class DelayedSession(Session):
        def get(self,*args,**kwargs):
            row = super().get(*args,**kwargs)
            if threading.current_thread().name=='delayed-trace':
                selected.set()
                release.wait(5)
            return row
    monkeypatch.setattr(database,'session',sessionmaker(bind=database.engine,class_=DelayedSession,expire_on_commit=False))
    failures = []
    event = {'type':'tool_call','name':'get_employee_id','tool_call_id':'late','attempt':1,'args':{}}
    def delayed():
        try:
            record_tool_event(database,'late-write',event,{})
        except RuntimeError as exc:
            failures.append(str(exc))
    thread = threading.Thread(target=delayed,name='delayed-trace',daemon=True)
    thread.start()
    try:
        assert selected.wait(2)
        finish_run(database,'late-write','','cancelled',[],None,None,{})
    finally:
        release.set()
        thread.join(3)
    with database.session() as db:
        row = db.get(ChatRun,'late-write')
        assert row.status=='cancelled'
        assert row.tool_events==[]
    assert failures
