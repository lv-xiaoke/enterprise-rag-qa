def test_expiration_removes_history_and_pending_draft():
    from ui.session_state import clear_identity
    state = {'user':{'id':'a'}, 'conversation_id':'old', 'messages':[{'content':'private'}],
             'report_content':'private draft', 'run_id':'old-run', 'top_k':3}
    clear_identity(state)
    assert state['user'] is None
    assert state['messages'] == []
    assert state['conversation_id'] is None
    assert state['report_content'] == ''
    assert state['run_id'] is None
    assert state['top_k'] == 3
