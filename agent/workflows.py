"""Task completion is defined by evidence, not by a model saying 'done'."""


def required_steps(intent):
    if intent.task == 'weekly_report':
        return {'get_employee_id','get_employee_department','generate_weekly_report_context',
                'fetch_employee_records:weekly_report'}
    if intent.task == 'knowledge':
        return {'rag_summarize'}
    if intent.task in {'personal','combined'}:
        steps = {'get_employee_id',f'fetch_employee_records:{intent.query_type}'}
        return steps | {'rag_summarize'} if intent.task == 'combined' else steps
    return set()


def completed_step(name, args):
    return f"{name}:{args['query_type']}" if name == 'fetch_employee_records' else name
