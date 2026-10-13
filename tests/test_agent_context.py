import json
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_final_context_pins_legal_long_question_and_actual_evidence():
    from agent.context import final_messages
    question = '问'*2000
    sources = [{'chunk_id':f'chunk-{i}','title':'题'*200,'excerpt':'据'*100+'FINAL-EVIDENCE'} for i in range(8)]
    call = {'id':'rag','name':'rag_summarize','args':{'query':question}}
    state = {'intent':{'task':'knowledge'},'completed':['rag_summarize'],'messages':[
        HumanMessage(content='old history'),AIMessage(content='old answer'),HumanMessage(content=question),
        AIMessage(content='',tool_calls=[call]),ToolMessage(name='rag_summarize',tool_call_id='rag',
            content=json.dumps({'status':'ok','data':sources}))]}
    rendered = '\n'.join(str(message.content) for message in final_messages(state))
    assert question in rendered
    assert rendered.count('FINAL-EVIDENCE')==8


def test_missing_or_oversized_evidence_cannot_keep_completion_flags():
    import pytest
    from agent.context import final_messages, EvidenceContextError
    state = {'intent':{'task':'knowledge'},'completed':['rag_summarize'],
             'messages':[HumanMessage(content='question')]}
    with pytest.raises(EvidenceContextError,match='证据'):
        final_messages(state)
    state['intent'] = {'task':'chat'}
    state['messages']=[HumanMessage(content='x'*33000)]
    with pytest.raises(EvidenceContextError,match='过长'):
        final_messages(state)
