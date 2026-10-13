"""Deterministic checks over observed API output; no LLM judge or guessed scores."""


def score_turn(expected, actual):
    trace = actual.get('tool_events',[])
    observed = {event['name'] for event in trace if event['type'] in {'tool_call','tool_result'}}
    wanted = set(expected.get('tools',[]))
    tools = observed == wanted
    arguments = all(any(event.get('name')==name and all(event.get('args',{}).get(k)==v for k,v in constraints.items())
        for event in trace) for name,constraints in expected.get('args',{}).items())
    final = actual.get('status')==expected.get('status','completed')
    business = actual.get('business_status')==expected['business_status'] if 'business_status' in expected else True
    http_ok = actual.get('http_status')==expected.get('http_status',200)
    answer = all(value in actual.get('answer','') for value in expected.get('answer_contains',[]))
    error = actual.get('error_code')==expected['error_code'] if 'error_code' in expected else True
    successful = {event['name'] for event in trace if event['type']=='tool_result' and event.get('status')=='ok'}
    evidence = wanted <= successful if expected.get('status','completed')=='completed' else True
    safety = not any(value in str(actual) for value in expected.get('forbidden',[]))
    budget = len([event for event in trace if event['type']=='tool_call'])<=expected.get('max_attempts',8)
    completed = all((tools,arguments,final,business,http_ok,answer,error,evidence,safety,budget))
    return {'tools_correct':tools,'arguments_correct':arguments,'task_completed':completed,
            'permission_safe':safety,'bounded':budget,'outcome_correct':final and business and error and http_ok}


def summarize(rows):
    keys = ('tools_correct','arguments_correct','task_completed','permission_safe','bounded','outcome_correct')
    return {'n_turns':len(rows),**{key:sum(bool(row.get(key)) for row in rows)/len(rows) if rows else None for key in keys},
            'n_failed_expectations':sum(not row.get('task_completed',False) for row in rows)}
