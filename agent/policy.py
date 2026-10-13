from agent.contracts import IntentDecision


def clarification(intent: IntentDecision):
    if intent.task in {'personal','combined'} and intent.query_type is None:
        return {'task':intent.task,'missing_fields':['query_type'],
                'question':'你想查询报销状态、项目进展、入职待办，还是年假余额？'}
    if intent.task == 'clarify':
        return {'task':'clarify','missing_fields':['business_request'],
                'question':intent.question or '请说明你希望查询的制度、本人业务信息或周报需求。'}
    return None


def validate_call(intent, name, args, completed):
    if name in {'fetch_employee_records','get_employee_department'}:
        if name == 'fetch_employee_records':
            expected = 'weekly_report' if intent.task == 'weekly_report' else intent.query_type
            if expected is None or args.get('query_type') != expected:
                return 'INVALID_ARGUMENTS'
        if 'get_employee_id' not in completed:
            return 'MISSING_PREREQUISITE'
    return None
