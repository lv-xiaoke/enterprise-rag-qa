import json
from pathlib import Path


def test_scoring_uses_actual_tool_trace_and_counts_failures():
    from eval.agent_metrics import score_turn, summarize
    expected = {'tools':['fetch_employee_records'],'args':{'fetch_employee_records':{'query_type':'leave_balance'}},
                'status':'completed','answer_contains':['7']}
    actual = {'http_status':200,'status':'completed','answer':'剩余7天','tool_events':[
        {'type':'tool_call','name':'fetch_employee_records','args':{'query_type':'reimbursement'},'status':'running'}]}
    row = score_turn(expected,actual)
    assert row['arguments_correct'] is False
    assert row['task_completed'] is False  # Missing a successful tool result is not completion.
    actual['tool_events'] = []
    assert score_turn(expected,actual)['tools_correct'] is False
    report = summarize([row,{'tools_correct':False,'arguments_correct':False,'task_completed':False}])
    assert report['n_turns']==2
    assert report['task_completed']==0


def test_dataset_covers_40_fixed_scenarios_and_two_splits():
    rows = [json.loads(line) for line in Path('eval/agent_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==40
    assert len({row['id'] for row in rows})==40
    assert {row['split'] for row in rows}=={'development','heldout'}
    assert {row['category'] for row in rows}=={'knowledge','personal','clarification','workflow','permission','context','failure'}
    assert all(row['turns'] and row['script'] for row in rows)


def test_deterministic_eval_drives_real_authenticated_graph(tmp_path):
    from eval.run_agent_eval import run_evaluation
    output = run_evaluation(Path('eval/agent_cases.jsonl'),'deterministic',tmp_path,limit=2)
    assert output['mode']=='deterministic'
    assert output['summary']['n_turns']==2
    assert output['summary']['task_completed']==1
    assert all(row['actual']['tool_events'] for row in output['turns'])
