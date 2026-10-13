def test_supported_sdk_clients_have_explicit_timeout_and_no_hidden_retries(monkeypatch):
    from model.factory import build_chat_model
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-unused-key')
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-unused-key')
    deepseek = build_chat_model(provider='deepseek',model='deepseek-chat')
    assert deepseek.max_retries == 0
    assert deepseek.request_timeout == 30
    tongyi = build_chat_model(provider='dashscope',model='qwen-plus')
    assert tongyi.max_retries == 1  # Tenacity stop_after_attempt counts total attempts.
    assert tongyi.model_kwargs['request_timeout'] == 30
