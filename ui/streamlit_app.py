"""Presentation only: identity, history and Agent execution live in the API."""
import os
import uuid
import streamlit as st
from ui.api_client import AgentApiClient, ApiError, AuthenticationExpired
from ui.session_state import clear_identity


def client():
    if 'api_client' not in st.session_state:
        st.session_state.api_client = AgentApiClient(
            os.getenv('API_BASE_URL','http://127.0.0.1:8000'),
            os.getenv('APP_ORIGIN','http://127.0.0.1:5173'))
    return st.session_state.api_client


def load_history(api):
    cid = st.session_state.conversation_id
    st.session_state.messages = api.list_messages(cid) if cid else []
    st.session_state.runs = api.list_runs(cid) if cid else []


def trace(events):
    if not events:
        return
    with st.expander('工具执行过程'):
        for event in events:
            name = event.get('name', event.get('tool_name',''))
            st.write(f"{name} · {event.get('status', event.get('type',''))}")
            if event.get('args'):
                st.json(event['args'])
            summary = event.get('summary', event.get('content',''))
            if summary:
                st.text(str(summary)[:800])


def sidebar(api):
    with st.sidebar:
        st.write(f"当前账号：{st.session_state.user['name']}")
        if st.button('退出登录'):
            api.logout()
            st.session_state.pop('api_client',None)
            clear_identity(st.session_state)
            st.rerun()
        conversations = api.list_conversations()
        if st.button('新建会话'):
            st.session_state.conversation_id = api.create_conversation()['id']
            st.session_state.pop('conversation_picker',None)
            load_history(api)
            st.rerun()
        if conversations:
            ids = [row['id'] for row in conversations]
            labels = {row['id']:row['title'] for row in conversations}
            active = st.session_state.conversation_id
            selected = st.selectbox('历史会话',ids,format_func=labels.get,
                index=ids.index(active) if active in ids else 0,key='conversation_picker')
            if selected != active:
                st.session_state.conversation_id = selected
                load_history(api)
                st.rerun()
        if st.session_state.conversation_id and st.button('清空当前会话'):
            api.clear_messages(st.session_state.conversation_id)
            load_history(api)
            st.rerun()
        from model.factory import chat_model_choices
        st.selectbox('模型',chat_model_choices(),key='model_name')
        st.slider('Temperature',0.,1.,value=.3,step=.05,key='temperature')
        st.slider('Top-K 检索数量',1,8,value=3,key='top_k')
        st.download_button('导出当前会话','\n\n'.join(
            f"{m['role']}：{m['content']}" for m in st.session_state.messages),
            file_name='agent-conversation.md',mime='text/markdown')
        if st.session_state.user['role'] == 'admin':
            st.divider()
            st.write('知识文档')
            files = st.file_uploader('上传 TXT/PDF',type=['txt','pdf'],accept_multiple_files=True)
            if files and st.button('提交文档'):
                for file in files:
                    api.upload(file.name,file.getvalue())
                st.success('已提交后台处理；刷新可查看状态')
            if st.button('刷新文档状态'):
                st.rerun()
            for doc in api.list_documents():
                latest = doc['versions'][-1] if doc['versions'] else {}
                st.caption(f"{doc['title']} · {latest.get('status','无版本')}")
                if latest.get('status') == 'failed' and st.button('重试',key='retry-'+doc['id']):
                    api.retry_document(doc['id'])
                    st.rerun()


def chat(api):
    st.title('企业智能体业务助手')
    st.caption('制度查询 · 本人业务数据 · 多步骤周报；仅使用模拟企业数据')
    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            st.markdown(message['content'])
            if message.get('status','completed') != 'completed':
                st.warning('本轮状态：'+message['status'])
            if message.get('sources'):
                with st.expander('资料依据'):
                    for source in message['sources']:
                        st.write(source.get('title','企业制度'))
                        st.text(source.get('excerpt',''))
    if st.session_state.runs:
        with st.expander('历史运行记录'):
            for run in st.session_state.runs:
                st.caption(f"{run['id']} · {run['status']}")
                trace(run.get('tool_events',[]))
    prompt = st.chat_input('例如：查我的报销状态，并告诉我下一步怎么处理')
    if prompt:
        if not st.session_state.conversation_id:
            st.session_state.conversation_id = api.create_conversation()['id']
        cid = st.session_state.conversation_id
        with st.chat_message('user'):
            st.write(prompt)
        with st.chat_message('assistant'):
            output = st.empty()
            status = st.empty()
            text, steps = '', []
            for event in api.stream_chat(cid,prompt,uuid.uuid4().hex,
                model_name=st.session_state.model_name,temperature=st.session_state.temperature,
                top_k=st.session_state.top_k):
                kind = event['type']
                if kind == 'start':
                    st.session_state.run_id = event['run_id']
                elif kind == 'token':
                    text += event.get('content','')
                    output.markdown(text)
                elif kind in {'tool_call','tool_result','tool_status'}:
                    steps.append(event)
                    status.caption(f"{event.get('name','工具')} · {event.get('status',kind)}")
                elif kind == 'error':
                    st.error(event.get('message','生成失败'))
                elif kind == 'done':
                    status.caption('本轮状态：'+event['status'])
            trace(steps)
        load_history(api)
        st.session_state.run_id = None
        st.rerun()


def reports(api):
    st.subheader('周报草稿与确认保存')
    if st.button('将最近一条完整回答放入周报草稿'):
        completed = [m for m in st.session_state.messages if m['role']=='assistant' and m.get('status')=='completed']
        if completed:
            st.session_state.report_content = completed[-1]['content']
        else:
            st.info('当前会话还没有完整回答')
    st.text_input('周报标题',key='report_title')
    st.text_area('编辑草稿',key='report_content',height=240)
    if st.button('确认保存本人周报',disabled=not st.session_state.report_content.strip()):
        api.save_report(st.session_state.report_title,st.session_state.report_content)
        st.success('已保存本人周报')
    for report in api.list_reports():
        with st.expander(report['title']):
            st.markdown(report['content'])


def main():
    if 'user' not in st.session_state:
        clear_identity(st.session_state)
    api = client()
    try:
        if st.session_state.user is None:
            st.title('登录企业智能体助手')
            with st.form('login'):
                username = st.text_input('账号')
                password = st.text_input('密码',type='password')
                submit = st.form_submit_button('登录')
            if submit:
                st.session_state.user = api.login(username,password)
                st.rerun()
            return
        st.session_state.user = api.me()
        sidebar(api)
        chat_tab, report_tab = st.tabs(['智能体会话','本人周报'])
        with chat_tab:
            chat(api)
        with report_tab:
            reports(api)
    except AuthenticationExpired:
        clear_identity(st.session_state)
        st.session_state.pop('conversation_picker',None)
        st.warning('登录已失效，请重新登录')
        st.rerun()
    except ApiError as exc:
        st.error(str(exc))
        if exc.status == 409 and st.session_state.conversation_id:
            load_history(api)
            st.info('请求已处理或正在生成，已更新历史；未自动重复提交')
