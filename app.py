from __future__ import annotations

import html
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from langchain_community.chat_models.tongyi import ChatTongyi

import agent.react_agent as react_agent_module
import model.factory as model_factory
from agent.react_agent import ReactAgent
from agent.tools.agent_tools import rag as rag_service
from utils.config_handler import rag_conf


APP_TITLE = "企业知识库问答"
APP_SUBTITLE = "面向员工制度、流程、IT 支持与个人业务数据的智能问答助手"
KNOWLEDGE_DIR = Path("data/enterprise")

MODEL_OPTIONS = [
    rag_conf["chat_model_name"],
    "qwen-plus",
    "qwen-turbo",
    "qwen-max",
]

USER_ICON = """
<svg viewBox="0 0 24 24" aria-hidden="true">
  <circle cx="12" cy="12" r="8.2" fill="currentColor"/>
</svg>
"""

AI_ICON = """
<svg viewBox="0 0 24 24" aria-hidden="true">
  <path d="M12 2.75l1.85 5.15 5.15 1.85-5.15 1.85L12 16.75l-1.85-5.15L5 9.75 10.15 7.9 12 2.75z" fill="currentColor"/>
  <path d="M18.2 14.4l.78 2.18 2.18.78-2.18.78-.78 2.18-.78-2.18-2.18-.78 2.18-.78.78-2.18z" fill="currentColor" opacity=".78"/>
</svg>
"""


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_custom_css() -> None:
    """Inject all Streamlit UI overrides in one place."""
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f8f9fa;
            --sidebar-bg: #ffffff;
            --surface: #ffffff;
            --surface-soft: #f1f3f4;
            --surface-hover: #eef2f7;
            --text: #1f1f1f;
            --text-soft: #3c4043;
            --muted: #70757a;
            --line: #e8eaed;
            --blue: #1a73e8;
            --purple: #8e5cf7;
            --shadow: 0 18px 45px rgba(60, 64, 67, .14);
            --radius: 26px;
            --content-width: min(1540px, calc(100vw - 5rem));
            --font: Inter, Roboto, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
        }

        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            background: var(--app-bg) !important;
            color: var(--text);
            font-family: var(--font);
        }

        .stApp, .stApp button, .stApp input, .stApp textarea, .stApp select {
            font-family: var(--font);
            letter-spacing: 0;
        }

        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        .stDeployButton,
        #MainMenu,
        footer {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            visibility: hidden !important;
        }

        .block-container {
            max-width: 100%;
            padding: 1.25rem 1.5rem 8rem;
        }

        .app-topbar {
            align-items: center;
            display: flex;
            justify-content: space-between;
            margin: 0 auto 1.25rem;
            max-width: var(--content-width);
            min-height: 2.5rem;
        }

        .brand {
            color: var(--text-soft);
            font-size: 1.2rem;
            font-weight: 620;
        }

        .status-pill {
            align-items: center;
            background: #edf4ff;
            border: 1px solid #d9e8ff;
            border-radius: 999px;
            color: #185abc;
            display: inline-flex;
            font-size: .78rem;
            font-weight: 600;
            gap: .4rem;
            min-height: 2rem;
            padding: 0 .75rem;
        }

        .chat-wrap, .empty-state, .quick-wrap {
            margin-left: auto;
            margin-right: auto;
            max-width: var(--content-width);
        }

        .empty-state {
            padding-top: clamp(4rem, 18vh, 10rem);
            text-align: center; /* 【新增】让容器内的文本整体居中 */
        }

        .eyebrow {
            color: var(--muted);
            font-size: .92rem;
            line-height: 1.6;
            margin-bottom: .3rem;
        }

        .empty-state h1 {
            background: linear-gradient(90deg, #4285f4 0%, #9b72cb 45%, #d96570 78%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: clamp(2.15rem, 5vw, 3.65rem);
            font-weight: 620;
            line-height: 1.1;
            margin: 0;
        }

        .empty-state p {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.65;
            margin: 1rem auto 1.4rem; /* 【关键修改】把 0 改为 auto，让这个设定了宽度的文字块整体居中 */
            max-width: 36rem;
            text-align: center; /* 【新增】确保文字在块的内部也是居中对齐的 */
        }

        .quick-wrap [data-testid="stHorizontalBlock"] {
            gap: .6rem;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button,
        .quick-wrap div[data-testid="stButton"] > button {
            background: #8a9097;
            border: 1px solid #8a9097;
            border-radius: 10px;
            box-shadow: none;
            color: #ffffff !important;
            font-size: .88rem;
            font-weight: 560;
            min-height: 2.55rem;
            padding: .35rem 1rem;
            position: relative;
            transition: background 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
            width: 100%;
        }

        .quick-wrap div[data-testid="stButton"] > button::after {
            border-bottom: 7px solid transparent;
            border-right: 9px solid #8a9097;
            bottom: 4px;
            content: "";
            height: 0;
            left: -7px;
            position: absolute;
            width: 0;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button *,
        [data-testid="stMain"] div[data-testid="stButton"] > button p,
        [data-testid="stMain"] div[data-testid="stButton"] > button span,
        [data-testid="stMain"] div[data-testid="stButton"] > button div,
        .quick-wrap div[data-testid="stButton"] > button *,
        .quick-wrap div[data-testid="stButton"] > button p {
            color: #ffffff !important;
            opacity: 1 !important;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button:hover,
        .quick-wrap div[data-testid="stButton"] > button:hover {
            background: #747b84;
            border-color: #747b84;
            box-shadow: 0 6px 18px rgba(60, 64, 67, .16);
            color: #ffffff !important;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button:hover::after,
        .quick-wrap div[data-testid="stButton"] > button:hover::after {
            border-right-color: #747b84;
        }

        [data-testid="stSidebar"] {
            background: var(--sidebar-bg);
            border-right: 1px solid #000000;
        }

        [data-testid="stSidebar"] > div {
            padding: 1.2rem 1rem;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--text);
            font-weight: 620;
            letter-spacing: 0;
        }

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span {
            color: var(--text-soft);
            font-size: .9rem;
        }

        [data-testid="stSidebar"] section[data-testid="stFileUploaderDropzone"] {
            background: #fbfbfb;
            border: 1px dashed #d7dce2;
            border-radius: 14px;
            box-shadow: none;
            padding: .75rem;
        }

        [data-testid="stSidebar"] div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-testid="stTextInput"] input,
        [data-testid="stSidebar"] [data-testid="stNumberInput"] input {
            background: #f8fafd;
            border: 1px solid var(--line);
            border-radius: 12px;
            box-shadow: none;
        }

        [data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"] {
            box-shadow: 0 0 0 4px rgba(26, 115, 232, .12);
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button,
        [data-testid="stSidebar"] div[data-testid="stDownloadButton"] > button {
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 999px;
            box-shadow: none;
            color: var(--text-soft);
            font-weight: 560;
            min-height: 2.4rem;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
        [data-testid="stSidebar"] div[data-testid="stDownloadButton"] > button:hover {
            background: var(--surface-hover);
            border-color: #d7e3f8;
            color: var(--blue);
        }

        [data-testid="stChatMessage"] {
            background: transparent;
            border: 0;
            box-shadow: none;
            margin: 0 auto 1.35rem;
            max-width: var(--content-width);
            width: 100%; /* 【新增】强制撑满变量定义的宽度 */
            padding: 0;
        }

        /* 【新增】确保助手的头像和回答靠左对齐 */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
            justify-content: flex-start; 
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
            color: var(--text-soft);
            font-size: 1rem;
            line-height: 1.6;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p:last-child {
            margin-bottom: 0;
        }

        [data-testid="stChatMessage"] [data-testid="stChatMessageContent"],
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
            max-width: 100%;
            width: 100%;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h1,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h2,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h3 {
            color: var(--text);
            font-weight: 620;
            line-height: 1.35;
        }

        [data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"] {
            background: transparent;
            border-radius: 999px;
            height: 2rem;
            margin-top: .15rem;
            width: 2rem;
        }

        [data-testid="chatAvatarIcon-user"],
        [data-testid="chatAvatarIcon-assistant"] {
            background: transparent !important;
            color: transparent !important;
            height: 0 !important;
            width: 0 !important;
        }

        [data-testid="stChatMessageAvatarUser"]::before,
        [data-testid="stChatMessageAvatarAssistant"]::before {
            align-items: center;
            border-radius: 999px;
            display: flex;
            height: 2rem;
            justify-content: center;
            width: 2rem;
        }

        [data-testid="stChatMessageAvatarUser"]::before {
            background: #e8eaed;
            color: #5f6368;
            content: "";
            -webkit-mask: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="8.2" fill="black"/></svg>') center / 1.35rem 1.35rem no-repeat;
            mask: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="8.2" fill="black"/></svg>') center / 1.35rem 1.35rem no-repeat;
        }

        [data-testid="stChatMessageAvatarAssistant"]::before {
            background: linear-gradient(135deg, #e8f0fe, #f3e8ff);
            color: var(--purple);
            content: "✦";
            font-size: 1.15rem;
            line-height: 1;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            justify-content: flex-end;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
            background: #f1f3f4;
            border-radius: 20px;
            margin-left: auto;
            max-width: min(860px, 76%);
            padding: .78rem 1rem;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
            background: transparent;
            border: 0;
            max-width: 100%;
            padding-top: .18rem;
            width: 100%;
        }

        details[data-testid="stExpander"] {
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 14px !important;
            box-shadow: none !important;
            margin: .9rem auto 1.6rem;
            max-width: var(--content-width);
        }

        details[data-testid="stExpander"] summary {
            color: var(--muted) !important;
            font-size: .84rem !important;
            font-weight: 520 !important;
        }

        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"],
        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] p,
        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] li {
            color: var(--muted) !important;
            font-size: .84rem !important;
            line-height: 1.55 !important;
        }

        .source-card {
            background: rgba(255, 255, 255, .64);
            border: 1px solid var(--line);
            border-radius: 12px;
            color: var(--muted);
            font-size: .84rem;
            line-height: 1.55;
            margin: .55rem 0;
            padding: .7rem .8rem;
        }

        .source-title {
            color: var(--text-soft);
            font-size: .82rem;
            font-weight: 620;
            margin-bottom: .28rem;
        }

        [data-testid="stChatInput"] {
            background: transparent !important; /* 【关键修改】强制背景透明，去掉黑色 */
            border-top: 0;
            padding: .9rem max(1rem, calc((100vw - var(--content-width)) / 2)) 1.05rem;
            bottom: 0;
            position: fixed;
            z-index: 99;
        }

        [data-testid="stChatInput"] > div {
            background: var(--surface);
            border: 1px solid #000000; /* 【关键修改】边框改为黑色 */
            border-radius: 18px;
            box-shadow: none;
            margin: 0 auto;
            width: 75%;
            max-width: 1200px;
            transition: border-color 160ms ease, box-shadow 160ms ease;
        }

        /* 【可选优化】鼠标点击输入框时的边框颜色（原本是浅灰色，现在也保持黑色或加粗阴影） */
        [data-testid="stChatInput"] > div:focus-within {
            border-color: #000000;
            box-shadow: 0 0 0 1px #000000; /* 聚焦时稍微加深一点视觉效果 */
        }

        [data-testid="stChatInput"] > div:focus-within {
            border-color: #b8c1cc;
            box-shadow: none;
        }

        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] input {
            color: var(--text);
            caret-color: var(--blue);
            font-size: .98rem;
            line-height: 1.5;
        }

        [data-testid="stChatInput"] textarea::placeholder,
        [data-testid="stChatInput"] input::placeholder {
            color: #8a9097;
        }

        [data-testid="stChatInput"] button {
            border-radius: 999px;
            color: var(--blue);
        }

        [data-testid="stChatInput"] button:hover {
            background: #edf4ff;
        }

        .stSpinner > div {
            color: var(--muted) !important;
        }

        @media (max-width: 760px) {
            .block-container {
                padding-left: .9rem;
                padding-right: .9rem;
            }

            .empty-state {
                padding-top: 3.2rem;
            }

            [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
                max-width: 88%;
            }

            [data-testid="stChatInput"] {
                padding-left: .75rem;
                padding-right: .75rem;
            }
        }

        section[data-testid="stMain"] div[data-testid="stButton"] > button,
        section[data-testid="stMain"] div[data-testid="stButton"] > button *,
        section[data-testid="stMain"] div[data-testid="stButton"] > button p,
        [data-testid="stMain"] div[data-testid="stButton"] > button,
        [data-testid="stMain"] div[data-testid="stButton"] > button *,
        [data-testid="stMain"] div[data-testid="stButton"] > button p {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            opacity: 1 !important;
            font-weight: 700 !important;
            text-shadow: 0 1px 1px rgba(0, 0, 0, .28);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "agent" not in st.session_state:
        st.session_state.agent = ReactAgent()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None
    if "top_k" not in st.session_state:
        st.session_state.top_k = 3
    if "temperature" not in st.session_state:
        st.session_state.temperature = 0.3
    if "active_model_name" not in st.session_state:
        st.session_state.active_model_name = rag_conf["chat_model_name"]


def export_messages_as_markdown(messages: list[dict]) -> str:
    role_names = {"user": "用户", "assistant": "助手"}
    lines = [
        f"# {APP_TITLE} 会话记录",
        "",
        f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 消息数量：{len(messages)}",
        "",
    ]

    if not messages:
        lines.append("> 当前暂无会话内容。")
        return "\n".join(lines)

    for index, message in enumerate(messages, start=1):
        role = role_names.get(message["role"], message["role"])
        lines.extend([f"## {index}. {role}", "", message["content"].strip(), ""])
        sources = message.get("sources") or []
        if sources:
            lines.append("### 引用来源")
            for source_index, source in enumerate(sources, start=1):
                lines.append(f"- [{source_index}] {source.get('source', '未知来源')}")
            lines.append("")

    return "\n".join(lines)


def reset_conversation() -> None:
    st.session_state.messages = []
    st.session_state.pending_prompt = None


def sync_runtime_settings() -> None:
    model_name = st.session_state.get("model_name", rag_conf["chat_model_name"])
    top_k = int(st.session_state.get("top_k", 3))
    temperature = float(st.session_state.get("temperature", 0.3))

    if model_name != st.session_state.get("active_model_name"):
        model_factory.chat_model = ChatTongyi(model=model_name, temperature=temperature)
        react_agent_module.chat_model = model_factory.chat_model
        rag_service.model = model_factory.chat_model
        rag_service.chain = rag_service._init_chain()
        st.session_state.agent = ReactAgent()
        st.session_state.active_model_name = model_name

    try:
        rag_service.retriever = rag_service.vector_store.vector_store.as_retriever(
            search_kwargs={"k": top_k}
        )
    except Exception:
        pass

    for model_like in (getattr(rag_service, "model", None),):
        if model_like is not None and hasattr(model_like, "temperature"):
            try:
                model_like.temperature = temperature
            except Exception:
                pass


def save_uploaded_files(uploaded_files: list) -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for uploaded_file in uploaded_files:
        safe_name = Path(uploaded_file.name).name
        target_path = KNOWLEDGE_DIR / safe_name
        target_path.write_bytes(uploaded_file.getbuffer())


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 知识库控制台")
        st.caption("模型、检索、上传和会话操作都收纳在这里。")

        model_options = list(dict.fromkeys(MODEL_OPTIONS))
        default_index = model_options.index(st.session_state.active_model_name)
        st.selectbox("模型", model_options, index=default_index, key="model_name")
        st.slider("Temperature", 0.0, 1.0, key="temperature", step=0.05)
        st.slider("Top-K 检索数量", 1, 8, key="top_k", step=1)

        st.divider()
        st.markdown("### 知识文档")
        uploaded_files = st.file_uploader(
            "上传 TXT / PDF",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded_files and st.button("保存并载入知识库", use_container_width=True):
            save_uploaded_files(uploaded_files)
            with st.spinner("正在写入向量库..."):
                rag_service.vector_store.load_document()
            st.success("知识库已更新")

        st.divider()
        st.download_button(
            "导出会话",
            data=export_messages_as_markdown(st.session_state.messages),
            file_name=f"enterprise-kb-chat-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.button("清空会话", type="secondary", use_container_width=True, on_click=reset_conversation)


def render_header() -> None:
    st.markdown(
        """
        <div class="app-topbar">
            <div class="brand">企业知识库问答系统</div>
            <div class="status-pill">✦ RAG Ready</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="eyebrow">{html.escape(APP_SUBTITLE)}</div>
            <h1>今天想了解什么？</h1>
            <p>直接询问制度流程、入职事项、IT 支持或个人业务数据。回答会保持简洁，并在末尾折叠展示检索文本块与引用来源。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def normalize_sources(raw_docs: list) -> list[dict[str, str]]:
    sources = []
    for index, doc in enumerate(raw_docs, start=1):
        metadata = getattr(doc, "metadata", {}) or {}
        source = (
            metadata.get("source")
            or metadata.get("file_path")
            or metadata.get("filename")
            or "企业知识库"
        )
        page = metadata.get("page")
        if page is not None:
            source = f"{source} · p.{page}"

        content = " ".join(getattr(doc, "page_content", "").split())
        sources.append(
            {
                "title": f"文本块 {index}",
                "source": str(source),
                "content": content[:520],
            }
        )
    return sources


def retrieve_sources(prompt: str) -> list[dict[str, str]]:
    try:
        docs = rag_service.retriever_docs(prompt)
    except Exception:
        return []
    return normalize_sources(docs)


def render_sources(sources: list[dict[str, str]]) -> None:
    if not sources:
        return

    with st.expander("检索到的文本块与引用来源", expanded=False):
        for source in sources:
            st.markdown(
                f"""
                <div class="source-card">
                    <div class="source-title">{html.escape(source["title"])} · {html.escape(source["source"])}</div>
                    <div>{html.escape(source["content"])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_messages() -> None:
    if not st.session_state.messages:
        render_empty_state()
        return

    st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)
    for message in st.session_state.messages:
        icon = USER_ICON if message["role"] == "user" else AI_ICON
        with st.chat_message(message["role"], avatar=icon):
            st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(message.get("sources", []))
    st.markdown("</div>", unsafe_allow_html=True)


def stream_agent_response(prompt: str) -> None:
    sync_runtime_settings()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_ICON):
        st.markdown(prompt)

    sources = retrieve_sources(prompt)
    response_chunks: list[str] = []

    with st.chat_message("assistant", avatar=AI_ICON):
        with st.spinner("正在检索知识库并生成回答..."):
            stream = st.session_state.agent.execute_stream(prompt)

            def capture():
                for chunk in stream:
                    response_chunks.append(chunk)
                    for char in chunk:
                        time.sleep(0.004)
                        yield char

            st.write_stream(capture())

    content = "".join(response_chunks).strip()
    if content:
        st.session_state.messages.append(
            {"role": "assistant", "content": content, "sources": sources}
        )
    st.rerun()


init_state()
inject_custom_css()
render_sidebar()
sync_runtime_settings()
render_header()
render_messages()

submitted_prompt = st.chat_input("向企业知识库提问")
prompt_to_run = st.session_state.pop("pending_prompt", None) or submitted_prompt

if prompt_to_run:
    stream_agent_response(prompt_to_run)
