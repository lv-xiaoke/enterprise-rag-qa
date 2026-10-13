def clear_identity(state):
    state.update(user=None, conversation_id=None, messages=[], report_content='',
                 report_title='本周工作周报', run_id=None, runs=[])
