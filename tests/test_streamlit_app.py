import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from test_agent_stream import RecordingModel
from test_agent_clarification import call, decision


@pytest.mark.parametrize('logout_status',[200,503])
def test_streamlit_login_chat_history_and_confirmed_report(v1_app, monkeypatch,logout_status):
    from agent.business_agent import BusinessAgent
    from ui.api_client import AgentApiClient
    import ui.streamlit_app
    script = [decision('personal',query_type='leave_balance'),call('get_employee_id'),
        call('fetch_employee_records',{'employee_id':'E1001','query_type':'leave_balance'},'records'),AIMessage(content='本人年假已查到')]
    model = RecordingModel(script=script)
    monkeypatch.setattr('model.factory.build_chat_model',lambda **kwargs:model)
    v1_app.state.agent = BusinessAgent(model=model,checkpointer=MemorySaver())
    server = TestClient(v1_app)
    def transport(request):
        if request.url.path.endswith('/auth/logout') and logout_status==503:
            return httpx.Response(503,json={'error':{'message':'synthetic outage'}})
        response = server.request(request.method,str(request.url),headers=dict(request.headers),content=request.content)
        return httpx.Response(response.status_code,headers=response.headers,content=response.content)
    monkeypatch.setattr(ui.streamlit_app,'AgentApiClient',lambda *args:AgentApiClient('http://testserver',
        'http://testserver',transport=httpx.MockTransport(transport)))
    at = AppTest.from_file('app.py',default_timeout=20).run()
    assert not at.exception
    at.text_input[0].set_value('E1001')
    at.text_input[1].set_value('Test-only-password!')
    at.button[0].click().run()
    assert not at.exception
    at.chat_input[0].set_value('查我的年假').run()
    assert not at.exception
    assert any('本人年假已查到' in element.value for element in at.markdown)
    draft_button = next(button for button in at.button if button.label=='将最近一条完整回答放入周报草稿')
    draft_button.click().run()
    assert at.text_area[0].value=='本人年假已查到'
    save = next(button for button in at.button if button.label=='确认保存本人周报')
    save.click().run()
    assert not at.exception
    assert any('已保存' in element.value for element in at.success)
    next(button for button in at.button if button.label=='退出登录').click().run()
    assert not at.exception
    assert at.session_state['user'] is None
    assert at.session_state['messages']==[]
    server.close()


def test_unchanged_selected_conversation_refreshes_on_rerun(v1_app, monkeypatch):
    from ui.api_client import AgentApiClient
    import ui.streamlit_app
    server = TestClient(v1_app)
    def transport(request):
        response = server.request(request.method,str(request.url),headers=dict(request.headers),content=request.content)
        return httpx.Response(response.status_code,headers=response.headers,content=response.content)
    monkeypatch.setattr(ui.streamlit_app,'AgentApiClient',lambda *args:AgentApiClient('http://testserver',
        'http://testserver',transport=httpx.MockTransport(transport)))
    at = AppTest.from_file('app.py',default_timeout=20).run()
    at.text_input[0].set_value('E1001'); at.text_input[1].set_value('Test-only-password!')
    at.button[0].click().run()
    next(b for b in at.button if b.label=='新建会话').click().run()
    cid = at.session_state['conversation_id']
    from backend.models import Message
    with v1_app.state.database.session() as db:
        db.add(Message(conversation_id=cid,role='assistant',content='server-finished-later'))
        db.commit()
    at.run()
    assert not at.exception
    assert any('server-finished-later' in element.value for element in at.markdown)
    server.close()
