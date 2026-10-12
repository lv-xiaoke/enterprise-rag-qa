from agent.runtime import RunContext, current_run
from agent.tools import agent_tools
from backend.models import EmployeeRecord


def test_personal_tool_uses_database_and_hard_identity_guard(v1_app, monkeypatch):
    def no_csv():
        raise AssertionError('authenticated API must read DB, not CSV')
    monkeypatch.setattr(agent_tools, '_load_employee_records', no_csv)
    token = current_run.set(RunContext('test-user','E1001',v1_app.state.database,None))
    identity = agent_tools._current_employee.set('E1001')
    try:
        result = agent_tools.fetch_employee_records.invoke({'employee_id':'E1001','query_type':'all'})
        assert 'E1001' in result
        denied = agent_tools.fetch_employee_records.invoke({'employee_id':'E1002','query_type':'all'})
        assert '拒绝访问' in denied
        agent_tools._current_employee.set(None)
        assert '未绑定' in agent_tools.fetch_employee_records.invoke({'employee_id':'E1001','query_type':'all'})
    finally:
        agent_tools._current_employee.reset(identity)
        current_run.reset(token)
