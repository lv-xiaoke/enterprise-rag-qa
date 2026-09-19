"""Agent 层测试：事件流契约与多轮记忆隔离。

用一个「按剧本返回消息」的假模型代替真模型。这样这些用例
不需要 API Key、不产生任何费用，也不会因为模型措辞变化而随机失败——
它们检验的是 Agent 的编排逻辑，不是模型的能力。

关于假模型的一个坑
------------------
最初用 `GenericFakeChatModel`，测试里工具死活不被调用。原因是它的 `_stream`
只把 `content` 逐字符推出去，**丢掉了 `tool_calls`**，于是图认为模型没要求
调工具，一轮就结束了。

这里改成只实现 `_generate`、不实现 `_stream`。`BaseChatModel.stream` 检测到
子类没重写 `_stream` 时会自动回退到 `_generate`，tool_calls 因此得以保留。
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

import agent.react_agent as react_agent
from agent.react_agent import DEFAULT_THREAD_ID, ReactAgent, new_thread_id
from agent.tools.agent_tools import set_current_employee
from model.factory import ProviderError


class RecordingModel(BaseChatModel):
    """按剧本依次返回消息，并记录每次调用实际收到的消息列表。

    `calls` 是断言多轮记忆的依据：模型看到的 messages 里有没有上一轮的内容，
    直接反映 checkpointer 有没有把历史接上。
    """

    script: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    def bind_tools(self, tools, **kwargs):
        # 必须返回自身：create_react_agent 会先 bind_tools 再调用
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(list(messages))
        # 剧本用完后重复最后一条，避免多轮调用时越界
        message = self.script[min(self.cursor, len(self.script) - 1)]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


class ExplodingModel(RecordingModel):
    """每次调用都抛异常，用于验证失败路径。"""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("模拟上游模型不可用")


def _texts(messages) -> list[str]:
    return [str(getattr(m, "content", "")) for m in messages]


@pytest.fixture
def thread_id() -> str:
    """每个用例一个独立会话 ID。

    checkpointer 是模块级共享的（这是刻意的：切模型不该丢历史），
    所以用例之间必须靠 thread_id 隔离，不能指望它自己清空。
    """
    return new_thread_id()


@pytest.fixture
def make_agent(monkeypatch):
    """构造一个使用假模型的 ReactAgent。

    用 monkeypatch 而不是直接给模块属性赋值：用例跑完自动还原，
    否则一个用例设的假模型会污染后面所有用例。
    """

    def _factory(script: list | None = None, model: BaseChatModel | None = None):
        model = model or RecordingModel(script=script or [])
        # raising=False：首次运行时模块里可能还没有 chat_model 这个名字
        monkeypatch.setattr(react_agent, "chat_model", model, raising=False)
        return ReactAgent(), model

    return _factory


class TestEventStream:
    """事件流契约：界面的推理过程展示完全依赖它。"""

    def test_events_appear_in_execution_order(self, make_agent, thread_id):
        agent, _ = make_agent(
            [
                AIMessage(
                    content="我先查一下。",
                    tool_calls=[
                        {"name": "get_employee_id", "args": {}, "id": "call-1"}
                    ],
                ),
                AIMessage(content="你的员工 ID 是 E1001。"),
            ]
        )

        events = list(agent.stream_events("我是谁", thread_id=thread_id))

        assert [event["type"] for event in events] == [
            "token",
            "tool_call",
            "tool_result",
            "token",
        ]

    def test_tool_call_carries_name_and_args(self, make_agent, thread_id):
        agent, _ = make_agent(
            [
                AIMessage(
                    content="查一下年假。",
                    tool_calls=[
                        {
                            "name": "fetch_employee_records",
                            "args": {
                                "employee_id": "E1001",
                                "query_type": "leave_balance",
                            },
                            "id": "call-1",
                        }
                    ],
                ),
                AIMessage(content="你还有 5 天年假。"),
            ]
        )

        call = next(
            event
            for event in agent.stream_events("我年假还剩几天", thread_id=thread_id)
            if event["type"] == "tool_call"
        )

        assert call["name"] == "fetch_employee_records"
        assert call["args"]["query_type"] == "leave_balance"

    def test_final_answer_contains_only_tokens(self, make_agent, thread_id):
        """正文只取 token，工具事件不混进答案里。"""
        agent, _ = make_agent(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "get_employee_id", "args": {}, "id": "call-1"}
                    ],
                ),
                AIMessage(content="最终答案在此。"),
            ]
        )

        text = "".join(agent.execute_stream("我是谁", thread_id=thread_id))

        assert "最终答案在此。" in text
        assert "你的员工 ID" not in text

    def test_failure_yields_error_event_instead_of_raising(self, make_agent, thread_id):
        """单次执行失败不该把 Streamlit / FastAPI 整个带崩。"""
        agent, _ = make_agent(model=ExplodingModel(script=[AIMessage(content="x")]))

        events = list(agent.stream_events("随便问问", thread_id=thread_id))

        assert [event["type"] for event in events] == ["error"]
        assert "系统提示" in events[0]["content"]


class TestGraphBuildFailure:
    """连执行图都没建起来时，也必须是 error 事件，而不是抛异常。

    这条和上面那条走的不是同一条路：上面是「图建好了、生成时炸」，这里是
    「图压根没建起来」——缺 API Key 时 `_get_graph()` 取模型就抛
    `ProviderError`。构建图的那行代码曾经在 `try` **外面**，异常会直接穿出
    异步生成器，后果分两种，都不好：

    - `api/server.py`：响应头早已发出（200 + `text/event-stream`），状态码
      改不了，异常只能让连接断开，而 `finally` 里的 `done` 照发——客户端收到
      的是一个正常收尾的空回答。实测过：200、正文为空、日志是
      `ttft=n/a chunks=0` 的 INFO 行，看起来像「模型这次没说话」。
    - `app.py`：Streamlit 的消费循环没有 try，异常会冒到 `st.write_stream`，
      用户看到的是报错堆栈而不是一句能读懂的话。

    所以构建图必须在 `try` 里面。这条用例钉的就是那个位置。
    """

    def test_model_build_failure_yields_error_event(self, make_agent, monkeypatch, thread_id):
        agent, _ = make_agent([AIMessage(content="永远用不上")])

        def _boom():
            raise ProviderError("缺少环境变量 DEEPSEEK_API_KEY")

        monkeypatch.setattr(react_agent, "_current_chat_model", _boom)

        async def collect():
            return [
                event
                async for event in agent.astream_events("随便问问", thread_id=thread_id)
            ]

        events = asyncio.run(collect())

        assert [event["type"] for event in events] == ["error"], (
            f"构建图失败应当只产出一条 error 事件，实际：{[e['type'] for e in events]}"
        )
        assert "DEEPSEEK_API_KEY" in events[0]["content"]

    def test_sync_path_also_degrades_to_error_event(self, make_agent, monkeypatch, thread_id):
        """同步路径同理——Streamlit 用的是它。"""
        agent, _ = make_agent([AIMessage(content="永远用不上")])

        def _boom():
            raise ProviderError("缺少环境变量 DEEPSEEK_API_KEY")

        monkeypatch.setattr(react_agent, "_current_chat_model", _boom)

        events = list(agent.stream_events("随便问问", thread_id=thread_id))

        assert [event["type"] for event in events] == ["error"]


class TestMemory:
    """多轮记忆：同一个 thread 接得上，不同 thread 不串。"""

    def test_same_thread_keeps_history(self, make_agent, thread_id):
        agent, model = make_agent(
            [AIMessage(content="回答一"), AIMessage(content="回答二")]
        )

        list(agent.stream_events("第一问", thread_id=thread_id))
        list(agent.stream_events("第二问", thread_id=thread_id))

        assert "第一问" in _texts(model.calls[1])

    def test_different_threads_are_isolated(self, make_agent):
        agent, model = make_agent(
            [AIMessage(content="回答一"), AIMessage(content="回答二")]
        )

        list(agent.stream_events("甲的私密问题", thread_id=new_thread_id()))
        list(agent.stream_events("乙的问题", thread_id=new_thread_id()))

        assert "甲的私密问题" not in _texts(model.calls[1])

    def test_reset_memory_forgets_the_conversation(self, make_agent, thread_id):
        """「清空会话」必须真的清掉模型侧的记忆。

        否则用户清空界面后再追问「刚才那个呢」，模型会接上一段
        用户已经看不见的上下文——看起来像凭空冒出来的回答。
        """
        agent, model = make_agent(
            [AIMessage(content="回答一"), AIMessage(content="回答二")]
        )

        list(agent.stream_events("清空前的问题", thread_id=thread_id))
        agent.reset_memory(thread_id)
        list(agent.stream_events("清空后的问题", thread_id=thread_id))

        assert "清空前的问题" not in _texts(model.calls[1])

    def test_default_thread_id_is_usable(self, make_agent):
        """默认会话 ID 存在，且调用方可以显式传它。"""
        agent, _ = make_agent([AIMessage(content="回答")])

        assert list(agent.stream_events("问题", thread_id=DEFAULT_THREAD_ID))

    def test_new_thread_id_is_unique(self):
        assert new_thread_id() != new_thread_id()


class TestGraphRebuild:
    """界面切换模型后，图必须重建，否则新模型不生效。"""

    def test_graph_is_rebuilt_when_model_changes(self, make_agent, thread_id):
        agent, first = make_agent([AIMessage(content="回答")])
        list(agent.stream_events("问题", thread_id=thread_id))
        assert agent._graph_model is first

        second = RecordingModel(script=[AIMessage(content="回答")])
        react_agent.chat_model = second
        list(agent.stream_events("再问一次", thread_id=thread_id))

        assert agent._graph_model is second

    def test_graph_is_reused_when_model_is_unchanged(self, make_agent, thread_id):
        """模型没换就不该重建——重建会丢掉编译缓存，白付一次编译开销。"""
        agent, _ = make_agent([AIMessage(content="回答")])
        list(agent.stream_events("问题", thread_id=thread_id))
        graph = agent._graph

        list(agent.stream_events("再问一次", thread_id=thread_id))

        assert agent._graph is graph


class TestIdentityIsolation:
    """身份是按请求绑定的，跨多轮工具调用不该丢。"""

    def test_identity_survives_multiple_tool_rounds(self, make_agent, thread_id):
        agent, _ = make_agent(
            [
                AIMessage(
                    content="先拿 ID。",
                    tool_calls=[{"name": "get_employee_id", "args": {}, "id": "c1"}],
                ),
                AIMessage(
                    content="再查年假。",
                    tool_calls=[
                        {
                            "name": "fetch_employee_records",
                            "args": {
                                "employee_id": "E1001",
                                "query_type": "leave_balance",
                            },
                            "id": "c2",
                        }
                    ],
                ),
                AIMessage(content="完成。"),
            ]
        )
        set_current_employee("E1001")

        results = [
            event["content"]
            for event in agent.stream_events("我年假还剩几天", thread_id=thread_id)
            if event["type"] == "tool_result"
        ]

        assert results[0] == "E1001"
        assert "拒绝访问" not in results[1]
