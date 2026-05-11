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
        /* ===== CSS Variables ===== */
        :root {
            --primary: #4f6ef6;
            --primary-dark: #3b51d4;
            --primary-light: #eef1ff;
            --accent: #7c5cf7;
            --accent-light: #f3efff;
            --coral: #f06548;
            --coral-light: #fff0ed;
            --green: #2dd4bf;
            --green-light: #edfdf9;
            --amber: #f59e0b;

            --app-bg: #f3f4f8;
            --sidebar-bg: #fafafc;
            --surface: #ffffff;
            --surface-soft: #f0f0f5;
            --surface-hover: #eaeaef;

            --text: #1a1a2e;
            --text-soft: #3d3d50;
            --muted: #8e8e9a;
            --line: #e4e4eb;

            --shadow-xs: 0 1px 2px rgba(0,0,0,.03);
            --shadow-sm: 0 2px 8px rgba(0,0,0,.05);
            --shadow-md: 0 8px 24px rgba(0,0,0,.07);
            --shadow-lg: 0 16px 48px rgba(0,0,0,.09);
            --shadow-glow: 0 0 0 3px rgba(79,110,246,.18);

            --radius-sm: 10px;
            --radius: 16px;
            --radius-lg: 22px;
            --radius-full: 999px;

            --transition: 200ms cubic-bezier(.4,0,.2,1);
            --transition-slow: 350ms cubic-bezier(.4,0,.2,1);

            --content-width: min(1540px, calc(100vw - 5rem));
            --font: "Inter", "SF Pro Display", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, -apple-system, sans-serif;
        }

        /* ===== Base ===== */
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
            padding: 1.5rem 2rem 8rem;
        }

        /* ===== Scrollbar ===== */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: #d0d0da;
            border-radius: 999px;
        }
        ::-webkit-scrollbar-thumb:hover { background: #b0b0ba; }

        /* ===== Header ===== */
        .app-topbar {
            align-items: center;
            display: flex;
            justify-content: space-between;
            margin: 0 auto 1.5rem;
            max-width: var(--content-width);
            min-height: 2.75rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid transparent;
            border-image: linear-gradient(90deg, var(--primary), var(--accent), transparent) 1;
            border-image-slice: 1;
        }

        .brand {
            background: linear-gradient(135deg, var(--text) 0%, var(--primary) 100%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: 1.25rem;
            font-weight: 680;
            letter-spacing: -.01em;
        }

        .status-pill {
            align-items: center;
            background: linear-gradient(135deg, var(--primary-light), var(--accent-light));
            border: 1px solid rgba(79,110,246,.18);
            border-radius: 999px;
            color: var(--primary-dark);
            display: inline-flex;
            font-size: .78rem;
            font-weight: 600;
            gap: .4rem;
            min-height: 2rem;
            padding: 0 .85rem;
            animation: statusPulse 3s ease-in-out infinite;
        }

        @keyframes statusPulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(79,110,246,.25); }
            50% { box-shadow: 0 0 0 6px rgba(79,110,246,0); }
        }

        .status-dot {
            background: var(--green);
            border-radius: 50%;
            display: inline-block;
            height: 7px;
            width: 7px;
        }

        /* ===== Layout helpers ===== */
        .chat-wrap, .empty-state, .quick-wrap {
            margin-left: auto;
            margin-right: auto;
            max-width: var(--content-width);
        }

        /* ===== Empty State ===== */
        .empty-state {
            padding-top: clamp(3rem, 14vh, 8rem);
            position: relative;
            text-align: center;
        }

        .empty-state::before {
            content: "";
            position: absolute;
            top: 2rem;
            left: 50%;
            transform: translateX(-50%);
            width: 420px;
            height: 420px;
            background: radial-gradient(circle at 30% 30%, rgba(124,92,247,.06) 0%, transparent 50%),
                        radial-gradient(circle at 70% 60%, rgba(79,110,246,.05) 0%, transparent 50%),
                        radial-gradient(circle at 50% 40%, rgba(240,101,72,.04) 0%, transparent 40%);
            border-radius: 50%;
            pointer-events: none;
            z-index: 0;
        }

        .empty-state > * { position: relative; z-index: 1; }

        .eyebrow {
            color: var(--muted);
            font-size: .88rem;
            font-weight: 500;
            letter-spacing: .04em;
            line-height: 1.6;
            margin-bottom: .4rem;
            text-transform: uppercase;
        }

        .empty-state h1 {
            background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 40%, var(--coral) 85%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: clamp(2.2rem, 5vw, 3.8rem);
            font-weight: 720;
            letter-spacing: -.02em;
            line-height: 1.15;
            margin: 0;
        }

        .empty-state p {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.7;
            margin: 1.2rem auto 1.6rem;
            max-width: 34rem;
        }

        .empty-state .decorative-icons {
            align-items: center;
            display: flex;
            gap: 2rem;
            justify-content: center;
            margin-top: 2.5rem;
        }

        .decorative-icons .deco-icon {
            align-items: center;
            background: var(--surface);
            border-radius: var(--radius);
            box-shadow: var(--shadow-sm);
            color: var(--muted);
            display: flex;
            flex-direction: column;
            font-size: .78rem;
            font-weight: 560;
            gap: .5rem;
            padding: 1.1rem 1.4rem;
            transition: transform var(--transition), box-shadow var(--transition);
        }

        .decorative-icons .deco-icon:hover {
            transform: translateY(-3px);
            box-shadow: var(--shadow-md);
        }

        .decorative-icons .deco-icon .icon-emoji {
            font-size: 1.6rem;
            line-height: 1;
        }

        /* ===== Quick Action Buttons ===== */
        .quick-wrap [data-testid="stHorizontalBlock"] {
            gap: .65rem;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button,
        .quick-wrap div[data-testid="stButton"] > button {
            border: none !important;
            border-radius: 12px !important;
            box-shadow: var(--shadow-xs) !important;
            color: #ffffff !important;
            font-size: .9rem !important;
            font-weight: 600 !important;
            min-height: 2.7rem !important;
            padding: .4rem 1.15rem !important;
            transition: transform var(--transition), box-shadow var(--transition), filter var(--transition) !important;
            width: 100%;
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button:hover,
        .quick-wrap div[data-testid="stButton"] > button:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md) !important;
            filter: brightness(1.05);
        }

        [data-testid="stMain"] div[data-testid="stButton"] > button:active,
        .quick-wrap div[data-testid="stButton"] > button:active {
            transform: translateY(0);
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

        /* ===== Sidebar ===== */
        [data-testid="stSidebar"] {
            background: var(--sidebar-bg);
            border-right: none !important;
            box-shadow: 2px 0 24px rgba(0,0,0,.04);
        }

        [data-testid="stSidebar"] > div {
            padding: 1.4rem 1.15rem;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--text);
            font-weight: 650;
            letter-spacing: -.01em;
        }

        [data-testid="stSidebar"] h3 {
            font-size: 1.05rem;
            position: relative;
            padding-left: .85rem;
        }

        [data-testid="stSidebar"] h3::before {
            content: "";
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 3px;
            height: 1.1em;
            background: linear-gradient(180deg, var(--primary), var(--accent));
            border-radius: 999px;
        }

        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span {
            color: var(--text-soft);
            font-size: .88rem;
        }

        [data-testid="stSidebar"] section[data-testid="stFileUploaderDropzone"] {
            background: var(--surface);
            border: 2px dashed var(--line);
            border-radius: var(--radius);
            box-shadow: none;
            padding: .85rem;
            transition: border-color var(--transition), background var(--transition);
        }

        [data-testid="stSidebar"] section[data-testid="stFileUploaderDropzone"]:hover {
            border-color: var(--primary);
            background: var(--primary-light);
        }

        [data-testid="stSidebar"] div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-testid="stTextInput"] input,
        [data-testid="stSidebar"] [data-testid="stNumberInput"] input {
            background: var(--surface);
            border: 1.5px solid var(--line);
            border-radius: 12px;
            box-shadow: none;
            transition: border-color var(--transition), box-shadow var(--transition);
        }

        [data-testid="stSidebar"] div[data-baseweb="select"] > div:focus-within,
        [data-testid="stSidebar"] [data-testid="stTextInput"] input:focus,
        [data-testid="stSidebar"] [data-testid="stNumberInput"] input:focus {
            border-color: var(--primary) !important;
            box-shadow: var(--shadow-glow) !important;
        }

        [data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"] {
            box-shadow: 0 0 0 4px rgba(79,110,246,.15);
        }

        [data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"]:focus {
            box-shadow: 0 0 0 4px rgba(79,110,246,.25);
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button,
        [data-testid="stSidebar"] div[data-testid="stDownloadButton"] > button {
            background: var(--surface);
            border: 1.5px solid var(--line) !important;
            border-radius: var(--radius-full) !important;
            box-shadow: var(--shadow-xs) !important;
            color: var(--text-soft) !important;
            font-weight: 560 !important;
            min-height: 2.5rem !important;
            transition: all var(--transition) !important;
        }

        [data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
        [data-testid="stSidebar"] div[data-testid="stDownloadButton"] > button:hover {
            background: var(--primary-light) !important;
            border-color: var(--primary) !important;
            color: var(--primary) !important;
            box-shadow: var(--shadow-sm) !important;
        }

        [data-testid="stSidebar"] hr {
            margin: 1.2rem 0;
            border-color: var(--line);
        }

        /* ===== Chat Messages ===== */
        [data-testid="stChatMessage"] {
            background: transparent;
            border: 0;
            box-shadow: none;
            margin: 0 auto 1.4rem;
            max-width: var(--content-width);
            width: 100%;
            padding: 0;
            animation: msgFadeIn .4s ease both;
        }

        @keyframes msgFadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
            justify-content: flex-start;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
            color: var(--text-soft);
            font-size: .98rem;
            line-height: 1.68;
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
            font-weight: 650;
            line-height: 1.35;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code {
            background: var(--surface-soft);
            border-radius: 6px;
            font-size: .88em;
            padding: .15em .4em;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] pre {
            background: #1e1e2e;
            border-radius: var(--radius);
        }

        /* Avatars */
        [data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"] {
            background: transparent;
            border-radius: 999px;
            height: 2.25rem;
            margin-top: .15rem;
            width: 2.25rem;
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
            height: 2.25rem;
            justify-content: center;
            width: 2.25rem;
        }

        [data-testid="stChatMessageAvatarUser"]::before {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff;
            content: "";
            -webkit-mask: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="8.2" fill="black"/></svg>') center / 1.35rem 1.35rem no-repeat;
            mask: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="8.2" fill="black"/></svg>') center / 1.35rem 1.35rem no-repeat;
        }

        [data-testid="stChatMessageAvatarAssistant"]::before {
            background: linear-gradient(135deg, var(--primary-light), var(--accent-light));
            color: var(--accent);
            content: "✦";
            font-size: 1.2rem;
            line-height: 1;
        }

        /* User message bubble */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            justify-content: flex-end;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 20px 20px 6px 20px;
            box-shadow: 0 4px 14px rgba(79,110,246,.25);
            margin-left: auto;
            max-width: min(860px, 72%);
            padding: .85rem 1.15rem;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"],
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] p,
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] li {
            color: #ffffff !important;
        }

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] code {
            background: rgba(255,255,255,.2);
            color: #fff;
        }

        /* AI message */
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-left: 3px solid var(--accent);
            border-radius: 6px var(--radius) var(--radius) 6px;
            box-shadow: var(--shadow-xs);
            max-width: 100%;
            padding: 1rem 1.2rem;
        }

        /* ===== Expander ===== */
        details[data-testid="stExpander"] {
            background: var(--surface) !important;
            border: 1px solid var(--line) !important;
            border-radius: var(--radius) !important;
            box-shadow: var(--shadow-xs) !important;
            margin: .9rem auto 1.6rem;
            max-width: var(--content-width);
            transition: border-color var(--transition), box-shadow var(--transition);
        }

        details[data-testid="stExpander"]:hover {
            border-color: #d0d0e0 !important;
            box-shadow: var(--shadow-sm) !important;
        }

        details[data-testid="stExpander"] summary {
            color: var(--text-soft) !important;
            font-size: .85rem !important;
            font-weight: 580 !important;
            padding: .6rem .9rem !important;
        }

        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"],
        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] p,
        details[data-testid="stExpander"] div[data-testid="stMarkdownContainer"] li {
            color: var(--muted) !important;
            font-size: .84rem !important;
            line-height: 1.6 !important;
        }

        /* ===== Source Cards ===== */
        .source-card {
            background: var(--surface-soft);
            border: 1px solid var(--line);
            border-left: 3px solid var(--accent);
            border-radius: 10px;
            color: var(--text-soft);
            font-size: .84rem;
            line-height: 1.6;
            margin: .6rem 0;
            padding: .75rem .9rem;
            transition: border-color var(--transition), box-shadow var(--transition);
        }

        .source-card:hover {
            border-color: var(--accent);
            box-shadow: var(--shadow-xs);
        }

        .source-title {
            color: var(--text);
            font-size: .82rem;
            font-weight: 650;
            margin-bottom: .35rem;
        }

        .source-title::before {
            content: "📄 ";
        }

        /* ===== Chat Input ===== */
        [data-testid="stChatInput"] {
            background: transparent !important;
            border-top: 0;
            padding: .9rem max(1rem, calc((100vw - var(--content-width)) / 2)) 1.2rem;
            bottom: 0;
            position: fixed;
            z-index: 99;
        }

        [data-testid="stChatInput"]::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: transparent;
        }

        [data-testid="stChatInput"] > div {
            background: var(--surface);
            border: 1.5px solid var(--line);
            border-radius: var(--radius-full);
            box-shadow: var(--shadow-sm);
            margin: 0 auto;
            width: 75%;
            max-width: 1200px;
            transition: border-color var(--transition), box-shadow var(--transition);
        }

        [data-testid="stChatInput"] > div:focus-within {
            border-color: var(--primary);
            box-shadow: var(--shadow-glow), var(--shadow-md);
        }

        [data-testid="stChatInput"] textarea,
        [data-testid="stChatInput"] input {
            color: var(--text);
            caret-color: var(--primary);
            font-size: .98rem;
            line-height: 1.5;
        }

        [data-testid="stChatInput"] textarea::placeholder,
        [data-testid="stChatInput"] input::placeholder {
            color: #b0b0be;
        }

        [data-testid="stChatInput"] button {
            border-radius: 999px;
            color: var(--primary) !important;
            transition: background var(--transition), transform var(--transition);
        }

        [data-testid="stChatInput"] button:hover {
            background: var(--primary-light) !important;
            transform: scale(1.05);
        }

        /* ===== Spinner ===== */
        .stSpinner > div {
            border-top-color: var(--primary) !important;
            border-left-color: var(--primary) !important;
        }

        /* ===== Responsive ===== */
        @media (max-width: 760px) {
            .block-container {
                padding: .9rem .9rem 7rem;
            }

            .empty-state {
                padding-top: 2.5rem;
            }

            .empty-state::before {
                width: 260px;
                height: 260px;
            }

            [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
                max-width: 88%;
            }

            [data-testid="stChatInput"] {
                padding-left: .75rem;
                padding-right: .75rem;
            }

            [data-testid="stChatInput"] > div {
                width: 92%;
            }

            .decorative-icons {
                flex-wrap: wrap;
                gap: .8rem;
            }
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
            <div class="status-pill"><span class="status-dot"></span>RAG Ready</div>
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
            <p>直接询问制度流程、入职事项、IT 支持或个人业务数据。<br>回答会保持简洁，并在末尾折叠展示检索文本块与引用来源。</p>
            <div class="decorative-icons">
                <div class="deco-icon">
                    <span class="icon-emoji">📋</span>
                    <span>制度流程</span>
                </div>
                <div class="deco-icon">
                    <span class="icon-emoji">💼</span>
                    <span>个人业务</span>
                </div>
                <div class="deco-icon">
                    <span class="icon-emoji">🖥️</span>
                    <span>IT 支持</span>
                </div>
                <div class="deco-icon">
                    <span class="icon-emoji">📊</span>
                    <span>周报生成</span>
                </div>
            </div>
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
