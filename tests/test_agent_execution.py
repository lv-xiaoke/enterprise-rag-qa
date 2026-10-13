import asyncio
import pytest


def test_transient_read_failure_retries_once_and_correlates_trace():
    from agent.execution import ExecutionBudget
    from agent.contracts import ToolOutcome
    count, trace = [], []
    async def flaky(name,args):
        count.append(name)
        if len(count)==1:
            raise ConnectionError('internal secret')
        return ToolOutcome(status='ok',data='ok')
    result = asyncio.run(ExecutionBudget().execute('get_employee_id',{},'call-a',trace.append,flaky))
    assert result.status == 'ok'
    assert count == ['get_employee_id','get_employee_id']
    assert all(row['tool_call_id']=='call-a' for row in trace)
    assert trace[-1]['status']=='ok'
    assert 'internal secret' not in str(trace)


def test_timeout_stops_after_bounded_attempts():
    from agent.execution import ExecutionBudget
    async def slow(name,args):
        await asyncio.sleep(1)
    budget = ExecutionBudget(tool_timeout=.01)
    result = asyncio.run(budget.execute('rag_summarize',{'query':'q'},'c',lambda event:None,slow))
    assert result.code=='TOOL_TIMEOUT'
    assert budget.total == 2


def test_denial_is_not_retried_and_repeated_call_is_bounded():
    from agent.execution import ExecutionBudget
    from agent.contracts import ToolOutcome
    count = []
    async def denied(name,args):
        count.append(1)
        return ToolOutcome(status='denied',code='ACCESS_DENIED')
    budget = ExecutionBudget()
    for n in range(3):
        result = asyncio.run(budget.execute('get_employee_id',{},str(n),lambda event:None,denied))
    assert len(count)==2
    assert result.code=='CALL_LIMIT'


def test_unknown_tool_and_extra_identity_argument_are_invalid():
    from agent.execution import execute_business_tool
    result = asyncio.run(execute_business_tool('shell',{}))
    assert result.code=='UNKNOWN_TOOL'
    result = asyncio.run(execute_business_tool('get_employee_id',{'user_id':'forged'}))
    assert result.status=='invalid'
