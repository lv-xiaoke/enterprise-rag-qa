from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from agent.runtime import RunContext, current_run
from agent.tools.agent_tools import _current_employee
from test_agent_stream import RecordingModel
from test_agent_clarification import call, decision, execute


def test_weekly_report_cannot_finish_without_employee_evidence():
    from agent.business_agent import BusinessAgent
    model = RecordingModel(script=[decision('weekly_report'),AIMessage(content='伪造成功周报')])
    result = execute(BusinessAgent(model=model,checkpointer=MemorySaver()),'生成周报')
    assert any(e['type']=='error' and e['code']=='MISSING_PREREQUISITE' for e in result)
    assert not any('伪造成功' in e.get('content','') for e in result)


def test_weekly_report_completes_only_after_valid_tools(v1_app):
    from agent.business_agent import BusinessAgent
    script = [decision('weekly_report'),call('get_employee_id'),
        call('get_employee_department',{'employee_id':'E1001'},'department'),
        call('generate_weekly_report_context',ident='context'),
        call('fetch_employee_records',{'employee_id':'E1001','query_type':'weekly_report'},'records'),
        AIMessage(content='本周工作概览\n关键产出\n问题风险\n下周计划')]
    token = current_run.set(RunContext('u','E1001',v1_app.state.database,None))
    identity = _current_employee.set('E1001')
    try:
        result = execute(BusinessAgent(model=RecordingModel(script=script),checkpointer=MemorySaver()),'生成周报')
        assert not any(e['type']=='error' for e in result)
        assert len([e for e in result if e['type']=='tool_result']) == 4
        assert any('关键产出' in e.get('content','') for e in result)
    finally:
        current_run.reset(token); _current_employee.reset(identity)


def test_foreign_record_denied_before_lookup(v1_app, monkeypatch):
    from agent.business_agent import BusinessAgent
    from agent.tools import agent_tools
    monkeypatch.setattr(agent_tools,'_lookup_employee',lambda employee: (_ for _ in ()).throw(AssertionError('read forbidden')))
    script = [decision('personal',query_type='leave_balance'),call('get_employee_id'),
        call('fetch_employee_records',{'employee_id':'E1002','query_type':'leave_balance'}),AIMessage(content='must not run')]
    token = current_run.set(RunContext('u','E1001',v1_app.state.database,None))
    identity = _current_employee.set('E1001')
    try:
        result = execute(BusinessAgent(model=RecordingModel(script=script),checkpointer=MemorySaver()),'查同事年假')
        assert any(e['type']=='error' and e['code']=='ACCESS_DENIED' for e in result)
        assert any(e['type']=='tool_result' and e['status']=='denied' for e in result)
    finally:
        current_run.reset(token); _current_employee.reset(identity)
