import asyncio
import threading
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from agent.react_agent import ReactAgent
from backend.checkpoints import Checkpoints
from backend.settings import Settings
from test_agent_stream import RecordingModel
from test_chat_lifecycle import events


def test_restart_with_pending_tool_accepts_next_turn_and_preserves_history(tmp_path):
    async def exercise():
        settings = Settings(runtime_dir=tmp_path)
        first = Checkpoints(settings)
        graph = ReactAgent(model=RecordingModel(script=[AIMessage(content='unused')]), checkpointer=await first.get())._get_graph()
        config = {'configurable':{'thread_id':'interrupted-tool'}}
        await graph.aupdate_state(config, {'messages':[
            HumanMessage(content='我原来的问题'), AIMessage(content='', tool_calls=[
                {'id':'pending-call','name':'get_employee_id','args':{}}])]}, as_node='agent')
        await first.close()
        second = Checkpoints(settings)
        try:
            model = RecordingModel(script=[AIMessage(content='可以继续回答')])
            agent = ReactAgent(model=model, checkpointer=await second.get())
            result = [event async for event in agent.astream_events('新的问题','interrupted-tool')]
            assert not any(event['type'] == 'error' for event in result)
            assert any('原来的问题' in str(m.content) for m in model.calls[0])
            assert not any(isinstance(m, AIMessage) and m.tool_calls for m in model.calls[0])
        finally:
            await second.close()
    asyncio.run(exercise())


def test_tool_infrastructure_exception_is_masked_and_run_failed(v1_app, clients, monkeypatch):
    from agent.tools import agent_tools
    def broken(employee_id):
        raise RuntimeError('internal-password=should-never-leak')
    monkeypatch.setattr(agent_tools,'_lookup_employee',broken)
    model = RecordingModel(script=[AIMessage(content='',tool_calls=[{
        'id':'lookup','name':'fetch_employee_records','args':{'employee_id':'E1001','query_type':'all'}}]),
        AIMessage(content='must not complete after error')])
    v1_app.state.agent = ReactAgent(model=model, checkpointer=MemorySaver())
    client = clients['E1001']
    conversation = client.post('/api/conversations',json={}).json()['id']
    response = client.post(f'/api/conversations/{conversation}/chat',json={'message':'query','client_request_id':'tool-error'})
    assert 'internal-password' not in response.text
    assert events(response)[-1][1]['status'] == 'failed'
    assert len(model.calls) == 1


def test_knowledge_close_waits_for_active_ingestion_thread(v1_app):
    service = v1_app.state.knowledge
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    def work():
        started.set(); release.wait(2); finished.set()
    service.process_queued = work
    async def exercise():
        await service.start()
        assert await asyncio.to_thread(started.wait,1)
        closing = asyncio.create_task(service.close())
        try:
            await asyncio.sleep(.03)
            assert not closing.done()
        finally:
            release.set()
            await closing
        assert finished.is_set()
    asyncio.run(exercise())
