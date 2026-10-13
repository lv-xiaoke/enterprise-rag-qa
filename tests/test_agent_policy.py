import pytest


def test_policy_rejects_guessed_parameters_and_unconfirmed_identity():
    from agent.contracts import IntentDecision
    from agent.policy import validate_call
    intent = IntentDecision(task='personal',query_type='reimbursement')
    assert validate_call(intent,'fetch_employee_records',{'employee_id':'E1001','query_type':'leave_balance'},set()) == 'INVALID_ARGUMENTS'
    assert validate_call(intent,'fetch_employee_records',{'employee_id':'E1001','query_type':'reimbursement'},set()) == 'MISSING_PREREQUISITE'


def test_invalid_classification_is_not_silently_defaulted():
    from agent.contracts import IntentDecision
    with pytest.raises(ValueError):
        IntentDecision(task='personal',query_type='annual_leave')
    with pytest.raises(ValueError):
        IntentDecision(task='unknown')
