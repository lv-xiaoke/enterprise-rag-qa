"""基于 LangGraph 的工具调用 Agent。

为什么从「文本 ReAct」换成「工具调用」
--------------------------------------
旧实现用 `langchain.agents.create_react_agent` + `AgentExecutor`，靠**文本解析**
识别 `Action: xxx` / `Action Input: xxx`。这条路有几个固有问题：

- 模型少写一个冒号、多写一句解释，整轮就解析失败。旧代码因此挂了个
  `handle_parsing_errors` 兜底——那本质是在给解析器的脆弱性打补丁，
  而不是在解决问题。
- 入参只能是字符串，所以工具内部要手工 strip 引号和花括号、按逗号切分
  （旧 `fetch_employee_records` 就是这么干的）。
- 无法表达「这个参数只能是这几个值之一」，模型传错值只能在运行时报错。

工具调用（tool calling）把「选哪个工具、传什么参数」交给模型的结构化输出能力，
由 provider 保证 JSON schema 合法。解析失败这一整类问题从根上消失，
工具签名也能是强类型的（见 `agent/tools/agent_tools.py`）。

关于记忆
--------
用 `MemorySaver` 按 `thread_id` 保存每个会话的消息序列，于是多轮追问
（「那病假呢？」）能接上上一轮的上下文。`thread_id` 由入口传入：
Streamlit 用会话级 ID，FastAPI 用客户端传入的会话 ID。
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Iterator

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.tools.agent_tools import (
    fetch_employee_records,
    generate_weekly_report_context,
    get_employee_department,
    get_employee_id,
    rag_summarize,
)
from utils.logger_handler import logger
from utils.prompt_loader import load_system_prompts

# 记忆存放处。放模块级而不是实例级：界面上切换模型会重建 ReactAgent，
# 若把 checkpointer 放在实例里，切一次模型就把整段对话历史弄丢了。
_CHECKPOINTER = MemorySaver()

DEFAULT_THREAD_ID = "default"


def new_thread_id() -> str:
    """生成新的会话 ID。

    清空对话时换一个 ID 即可丢弃该会话的全部记忆——比去翻 checkpointer
    内部结构删数据更简单，也不依赖 LangGraph 的私有 API。
    """
    return uuid.uuid4().hex


def _current_chat_model():
    """取当前对话模型：优先用模块属性，没有再回落到工厂。

    不写成顶层的 `from model.factory import chat_model`，是因为那会在 import
    阶段就构建模型客户端——没有 API Key 时连 `import agent.react_agent` 都会失败，
    而工具层与 Agent 结构的测试本不该依赖 Key。

    同时这也让 `app.py` 里 `react_agent_module.chat_model = ...` 的赋值继续生效：
    赋值写进模块 `__dict__`，这里优先读它。
    """
    override = globals().get("chat_model")
    if override is not None:
        return override

    from model.factory import chat_model as built

    globals()["chat_model"] = built
    return built


class ReactAgent:
    """企业知识助手 Agent：工具调用 + 多轮记忆 + 结构化流式输出。"""

    def __init__(self) -> None:
        self.tools = [
            rag_summarize,
            get_employee_id,
            get_employee_department,
            fetch_employee_records,
            generate_weekly_report_context,
        ]
        self.system_prompt = load_system_prompts()
        self._graph = None
        # 构建图时用的模型对象，用于检测界面是否换过模型
        self._graph_model = None

    # -- 图 ----------------------------------------------------------------

    def _get_graph(self):
        """惰性构建并缓存执行图。

        模型是模块级可变量（界面切换模型会直接给 `chat_model` 赋值），
        所以缓存之外还要比对模型对象：发现换了就重建图，否则切换模型不会生效。
        """
        model = _current_chat_model()

        if self._graph is None or self._graph_model is not model:
            from langgraph.prebuilt import create_react_agent

            self._graph = create_react_agent(
                model=model,
                tools=self.tools,
                state_modifier=SystemMessage(content=self.system_prompt),
                checkpointer=_CHECKPOINTER,
            )
            self._graph_model = model
            logger.info(f"[Agent]已构建执行图，工具 {len(self.tools)} 个")

        return self._graph

    # -- 记忆 --------------------------------------------------------------

    def reset_memory(self, thread_id: str) -> None:
        """清空指定会话的对话记忆。"""
        try:
            _CHECKPOINTER.delete_thread(thread_id)
        except Exception as exc:  # 记忆清理失败不该打断「清空会话」这个操作
            logger.error(f"[Agent]清理会话记忆失败 thread_id={thread_id}：{exc}")

    # -- 执行 --------------------------------------------------------------

    def _config(self, thread_id: str) -> dict:
        return {
            "configurable": {"thread_id": thread_id},
            "metadata": {"business_scene": "enterprise_knowledge_assistant"},
        }

    @staticmethod
    def _describe(message) -> Iterator[dict]:
        """把图内部的消息翻译成前端能用的事件。"""
        if isinstance(message, AIMessage):
            for call in getattr(message, "tool_calls", None) or []:
                yield {
                    "type": "tool_call",
                    "name": call.get("name", ""),
                    "args": call.get("args", {}),
                }
        elif isinstance(message, ToolMessage):
            yield {
                "type": "tool_result",
                "name": getattr(message, "name", "") or "",
                "content": str(message.content),
            }

    def _payload(self, query: str) -> dict:
        return {"messages": [{"role": "user", "content": query}]}

    def _translate(self, mode: str, chunk) -> Iterator[dict]:
        """把 (stream_mode, chunk) 翻译成事件。

        sync / async 两条执行路径共用这一份翻译逻辑——各写一份的话，
        迟早会有一边漏掉某个事件类型，而且很难被发现。
        """
        if mode == "messages":
            message, meta = chunk
            # 只转发 agent 节点产出的正文。工具节点的输出已经由
            # tool_result 事件单独给出，这里再推一次会重复。
            if meta.get("langgraph_node") == "agent":
                text = getattr(message, "content", "")
                if text:
                    yield {"type": "token", "content": text}
        elif mode == "updates":
            for update in (chunk or {}).values():
                for message in (update or {}).get("messages", []) or []:
                    yield from self._describe(message)

    def stream_events(
        self, query: str, thread_id: str = DEFAULT_THREAD_ID
    ) -> Iterator[dict]:
        """流式执行，产出结构化事件（同步）。

        事件类型：
          tool_call    模型决定调用某个工具，带工具名与参数
          tool_result  工具的执行结果
          token        最终答案的增量文本
          error        执行失败

        界面上把 tool_call / tool_result 渲染成可折叠的「推理过程」，
        token 渲染成正文——这样用户能看到 Agent 在查什么，而不是干等一个转圈。
        """
        try:
            graph = self._get_graph()
            for mode, chunk in graph.stream(
                self._payload(query),
                config=self._config(thread_id),
                stream_mode=["updates", "messages"],
            ):
                yield from self._translate(mode, chunk)
        except Exception as exc:
            # 兜底异常处理：调用方（Streamlit / FastAPI）不该因单次执行失败而崩掉
            logger.error(f"[Agent]执行失败：{exc}", exc_info=True)
            yield {"type": "error", "content": f"\n\n[系统提示：处理失败：{exc}]\n"}

    async def astream_events(
        self, query: str, thread_id: str = DEFAULT_THREAD_ID
    ) -> AsyncIterator[dict]:
        """流式执行，产出结构化事件（异步）。事件类型同 `stream_events`。

        服务端为什么必须走异步版本
        --------------------------
        `stream_events` 是阻塞的。在 FastAPI 里直接迭代它有两个选择，都不好：

        1. 在协程里直接迭代 → 整个事件循环被阻塞，一个慢请求会卡住所有并发请求。
        2. 交给线程池迭代 → 会踩到一个很隐蔽的坑：Starlette 的
           `iterate_in_threadpool` 是**每个元素一次** `run_sync`，每次调用都拿
           事件循环上下文的**副本**。于是「在生成器开头 set 一次 ContextVar」
           这种写法会失效——第一轮 `_next` 里 set 的身份，到第二轮就被还原成
           默认值了。工具层读到的身份是空的，越权校验也就跟着失效，而且不会
           报任何错。

        走 `astream` 则整段都在事件循环的同一个任务上下文里，ContextVar 的行为
        完全符合直觉。代价是模型调用必须是异步的（LangChain 的 ChatModel 都支持）。

        注意 `_get_graph()` 在 `try` **里面**：构建图会去取对话模型，缺 API Key
        时就在这里抛 `ProviderError`。放到 try 外面的话，异常会直接穿出这个
        异步生成器；而调用方（`api/server.py`）已经因为流式响应把 200 和
        `text/event-stream` 头发出去了，改不了状态码，客户端最终只会收到一个
        空的 `done`——没有答案、也没有报错。本项目实测过这个现象：
        缺 Key 时请求返回 200、正文为空、日志是 `ttft=n/a chunks=0` 的 INFO 行，
        看起来像一次成功的空回答。放进 try 里，它才会变成一条 `error` 事件。
        """
        try:
            graph = self._get_graph()
            async for mode, chunk in graph.astream(
                self._payload(query),
                config=self._config(thread_id),
                stream_mode=["updates", "messages"],
            ):
                for event in self._translate(mode, chunk):
                    yield event
        except Exception as exc:
            logger.error(f"[Agent]执行失败：{exc}", exc_info=True)
            yield {"type": "error", "content": f"\n\n[系统提示：处理失败：{exc}]\n"}

    def execute_stream(
        self, query: str, thread_id: str = DEFAULT_THREAD_ID
    ) -> Iterator[str]:
        """以纯文本增量流式返回答案。

        保留这个接口是为了不动既有调用方（Streamlit 正文渲染、评测脚本的
        `"".join(agent.execute_stream(q))`）。需要工具调用过程时用 stream_events。
        """
        for event in self.stream_events(query, thread_id):
            if event["type"] in ("token", "error"):
                yield event["content"]


if __name__ == "__main__":
    agent = ReactAgent()

    print("=== 流式事件（含工具调用过程）===")
    for ev in agent.stream_events("根据我的本周项目记录生成周报", thread_id="demo"):
        if ev["type"] == "tool_call":
            print(f"\n[调用工具] {ev['name']}  参数={ev['args']}")
        elif ev["type"] == "tool_result":
            print(f"[工具返回] {ev['name']} -> {ev['content'][:80]}")
        elif ev["type"] == "token":
            print(ev["content"], end="", flush=True)
    print()
