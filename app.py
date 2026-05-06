import time

import streamlit as st
from agent.react_agent import ReactAgent

st.title("企业知识库 Agent 助手")
st.caption("支持企业制度问答、员工信息查询、入职指引和个人周报生成")
st.divider()

if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if "message" not in st.session_state:
    st.session_state["message"] = []

with st.expander("示例问题", expanded=False):
    st.markdown(
        """
        - 差旅报销需要哪些材料？
        - 我还有多少年假？
        - 新员工入职第一周应该完成哪些事项？
        - 根据我的本周项目记录生成周报。
        """
    )

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

prompt = st.chat_input("请输入企业制度、员工数据或周报相关问题")

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    response_messages = []
    with st.spinner("企业知识助手思考中..."):
        res_stream = st.session_state["agent"].execute_stream(prompt)

        def capture(generator, cache_list):
            for chunk in generator:
                cache_list.append(chunk)

                for char in chunk:
                    time.sleep(0.01)
                    yield char

        st.chat_message("assistant").write_stream(capture(res_stream, response_messages))
        if response_messages:
            st.session_state["message"].append(
                {"role": "assistant", "content": response_messages[-1]}
            )
        st.rerun()
