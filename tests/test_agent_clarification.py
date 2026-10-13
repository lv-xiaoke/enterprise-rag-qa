import asyncio
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from test_agent_stream import RecordingModel


def decision(task, **args):
    return AIMessage(content='',tool_calls=[{'id':'intent','name':'classify_request','args':{'task':task,**args}}])


def call(name, args=None, ident='tool-1'):
    return AIMessage(content='',tool_calls=[{'id':ident,'name':name,'args':args or {}}])


def execute(agent, query, thread='case'):
    async def run():
        return [event async for event in agent.astream_events(query,thread)]
    return asyncio.run(run())


def test_missing_business_kind_asks_before_reading_and_persists_pending():
    from agent.business_agent import BusinessAgent
    model = RecordingModel(script=[decision('personal')])
    agent = BusinessAgent(model=model,checkpointer=MemorySaver())
    result = execute(agent,'帮我查一下状态')
    assert not any(event['type']=='tool_call' for event in result)
    assert any('报销' in event.get('content','') for event in result)
    state = asyncio.run(agent._get_graph().aget_state(agent._config('case')))
    assert state.values['pending']['missing_fields'] == ['query_type']


def test_followup_receives_pending_context_and_new_topic_clears_it():
    from agent.business_agent import BusinessAgent
    model = RecordingModel(script=[decision('personal'),decision('chat'),AIMessage(content='你好')])
    agent = BusinessAgent(model=model,checkpointer=MemorySaver())
    execute(agent,'查一下状态')
    result = execute(agent,'先不查了，你好')
    assert any(e.get('content')=='你好' for e in result)
    assert any('query_type' in str(m.content) for m in model.calls[1])
    state = asyncio.run(agent._get_graph().aget_state(agent._config('case')))
    assert state.values.get('pending') is None
