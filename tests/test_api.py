"""服务层测试：SSE 协议契约 + 并发下的身份隔离。

用假的异步模型，所以不需要 API Key、不产生费用，也不会因为模型措辞变化而
随机失败。这里检验的是**服务层的编排与隔离**，不是模型的能力。

为什么并发隔离值得单独写一个用例
--------------------------------
身份绑定用的是 `ContextVar`，而 `ContextVar` 只在「同一个执行上下文」里有效。
服务端把 Agent 交给异步图执行后，工具可能跑在事件循环里，也可能被丢进线程池——
后者不会自动继承上下文。一旦失去继承，`set_current_employee()` 设的值就丢了，
`_deny_if_not_self` 读到空身份，越权校验会**静默失效**：请求照常返回 200，
只是拦截不再生效。这种问题不报错，只会让安全边界悄悄消失，
所以必须有测试盯着它。
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ValidationError

import agent.react_agent as react_agent
import api.server as server_module
from agent.react_agent import ReactAgent, new_thread_id
from agent.tools.agent_tools import list_employees
from api.server import ChatRequest, _sse, app
from model.factory import ProviderError
from test_agent_stream import RecordingModel

# 模拟数据里确定存在的两个身份。用真实存在的 ID，避免用例因数据变动而失真。
SELF = "E1001"
OTHER = "E1002"


class AsyncRecordingModel(RecordingModel):
    """显式实现 `_agenerate`，让测试真的走异步路径。

    为什么不让基类回退到同步 `_generate`：那样测的是「异步图 + 同步模型」的
    兜底组合，而生产跑的是真正的异步模型。走兜底路径等于没测到服务端实际行为。
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """按「是否已经拿到工具结果」推进剧本，而不是按全局游标。

        不能沿用基类的 `cursor`：并发用例里两个请求共用同一个模型实例，
        游标会被对方推着走——第二个请求直接拿到「最终答案」，工具压根没被调用，
        于是那个用例会变成永远通过的空测试。按消息里有没有 ToolMessage 判断，
        每个会话各自独立推进，谁也不用看谁的进度。
        """
        self.calls.append(list(messages))
        answered = any(isinstance(m, ToolMessage) for m in messages)
        message = self.script[1] if answered else self.script[0]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        # 让出一次控制权，制造交错执行的机会——并发用例需要两个请求同时在飞，
        # 否则「先跑完 A 再跑 B」也能通过，测不出串不串。
        await asyncio.sleep(0)
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _ask_own_id() -> list:
    """一段最简剧本：让模型调用 `get_employee_id` 再作答。

    `get_employee_id` 不接受参数、只回当前绑定的身份，所以它的返回值
    就是「这个请求认为我是谁」的直接证据——正是并发用例需要的探针。
    """
    return [
        AIMessage(
            content="我看一下你是谁。",
            tool_calls=[{"name": "get_employee_id", "args": {}, "id": "c1"}],
        ),
        AIMessage(content="查到了。"),
    ]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """把 SSE 报文解析成 [(事件名, data), ...]。"""
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name is not None:
            events.append((name, data))
    return events


@pytest.fixture
def fake_app(monkeypatch):
    """装好假模型与启动状态的 app，不跑 lifespan。

    直接塞 `app.state` 而不是走 lifespan：lifespan 里会构造真实 ReactAgent，
    而我们要的正是「用假模型驱动」的那一个。顺带也让用例不依赖启动开销。
    """

    def _install(script: list | None = None):
        model = AsyncRecordingModel(script=script or _ask_own_id())
        monkeypatch.setattr(react_agent, "chat_model", model, raising=False)
        app.state.agent = ReactAgent()
        app.state.employees = {e["employee_id"]: e for e in list_employees()}
        return model

    return _install


@pytest.fixture
def client(fake_app):
    """同步用例走 TestClient。

    不用 httpx.ASGITransport：它只提供异步接口，同步的 httpx.Client 驱动不了。
    并发用例需要真正的并发，那里单独用 AsyncClient——两种客户端各司其职。
    TestClient 不加 with 就不会跑 lifespan，正好配合手动装好的 state。
    """
    fake_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# SSE 编码（纯函数，最便宜的一层）
# ---------------------------------------------------------------------------


class TestSseEncoding:
    def test_named_event_and_json_data(self):
        frame = _sse("token", {"content": "你好"})

        assert frame.startswith("event: token\n")
        assert frame.endswith("\n\n")
        assert json.loads(frame.split("data: ", 1)[1]) == {"content": "你好"}

    def test_newlines_in_content_do_not_break_framing(self):
        """SSE 的 data 行不能含裸换行。

        模型输出经常带换行，直接拼进去的话客户端会把一行内容当成两条独立消息，
        正文就碎了。`json.dumps` 把 \\n 转义掉，正好解决这个问题。
        """
        frame = _sse("token", {"content": "第一行\n第二行"})

        assert frame.count("\n\n") == 1
        assert json.loads(frame.split("data: ", 1)[1])["content"] == "第一行\n第二行"


# ---------------------------------------------------------------------------
# 基础接口
# ---------------------------------------------------------------------------


class TestEndpoints:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_employees_exposes_only_three_fields(self, client):
        """接口不该顺手把整条员工记录吐出去。

        `list_employees` 只回 id / 姓名 / 部门；这里再钉一遍，是因为将来
        有人图省事改成 `return records` 时越权校验就形同虚设了——
        前端选择器根本不需要年假余额这类字段。
        """
        rows = client.get("/employees").json()

        assert rows
        assert set(rows[0]) == {"employee_id", "employee_name", "department"}

    def test_unknown_employee_is_rejected(self, client):
        """拼错的员工 ID 必须是 400，不能静默回退到某个默认身份。"""
        resp = client.post(
            "/chat", json={"message": "我是谁", "employee_id": "NO-SUCH-ID"}
        )

        assert resp.status_code == 400
        assert "NO-SUCH-ID" in resp.json()["detail"]

    def test_empty_message_is_rejected(self, client):
        assert (
            client.post("/chat", json={"message": "", "employee_id": SELF}).status_code
            == 422
        )

    def test_session_reset(self, client):
        resp = client.delete(f"/sessions/{new_thread_id()}")

        assert resp.status_code == 200
        assert resp.json()["cleared"] is True


# ---------------------------------------------------------------------------
# SSE 事件流
# ---------------------------------------------------------------------------


class TestChatStream:
    def test_stream_is_named_sse_with_start_and_done(self, client):
        with client.stream(
            "POST", "/chat", json={"message": "我是谁", "employee_id": SELF}
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            events = parse_sse(resp.read().decode("utf-8"))

        names = [name for name, _ in events]
        assert names[0] == "start"
        assert names[-1] == "done"
        assert "tool_call" in names
        assert "tool_result" in names

    def test_start_event_returns_reusable_thread_id(self, client):
        """`start` 回的 thread_id 必须能原样传回来延续上下文。"""
        with client.stream(
            "POST", "/chat", json={"message": "我是谁", "employee_id": SELF}
        ) as resp:
            events = parse_sse(resp.read().decode("utf-8"))

        thread_id = dict(events)["start"]["thread_id"]

        with client.stream(
            "POST",
            "/chat",
            json={"message": "我是谁", "employee_id": SELF, "thread_id": thread_id},
        ) as resp:
            assert resp.status_code == 200

    def test_tokens_carry_the_answer_text(self, client):
        with client.stream(
            "POST", "/chat", json={"message": "我是谁", "employee_id": SELF}
        ) as resp:
            events = parse_sse(resp.read().decode("utf-8"))

        text = "".join(d["content"] for name, d in events if name == "token")
        assert "查到了" in text


# ---------------------------------------------------------------------------
# 并发身份隔离
# ---------------------------------------------------------------------------


class TestConcurrentIdentityIsolation:
    def test_two_employees_in_flight_do_not_cross_contaminate(self, fake_app):
        """两个不同身份的请求并发时，各自只能看到自己。

        这是 ContextVar 方案的核心保证，也是服务端最容易悄悄失效的一环：
        如果工具跑在不会继承上下文的线程里，两个请求会双双读到空身份，
        越权校验随之失效。而这种失败**不会报错**——只看「有没有抛异常」
        是发现不了的，必须断言工具实际看到的值。
        """
        fake_app()

        async def ask(ac: httpx.AsyncClient, employee_id: str) -> list[str]:
            async with ac.stream(
                "POST",
                "/chat",
                json={"message": "我是谁", "employee_id": employee_id},
            ) as resp:
                body = (await resp.aread()).decode("utf-8")
            return [
                d["content"] for name, d in parse_sse(body) if name == "tool_result"
            ]

        async def run() -> dict[str, list[str]]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                # gather 让两个请求同时在飞，否则测不出串不串
                self_res, other_res = await asyncio.gather(
                    ask(ac, SELF), ask(ac, OTHER)
                )
            return {SELF: self_res, OTHER: other_res}

        results = asyncio.run(run())

        assert results[SELF] == [SELF], f"{SELF} 实际看到 {results[SELF]}"
        assert results[OTHER] == [OTHER], f"{OTHER} 实际看到 {results[OTHER]}"


# ---------------------------------------------------------------------------
# 失败路径：必须是「看得见的失败」
# ---------------------------------------------------------------------------


class TestFailureIsVisible:
    """执行失败时，客户端必须收到 error，而不是一个安静的完成。

    这一组用例来自一次真实的线上观察：缺 `DEEPSEEK_API_KEY` 时，`/chat` 返回
    200 + `start` + `done`，正文为空，日志是一行 `ttft=n/a chunks=0` 的 INFO。
    看起来像「模型这次没说话」，而不是「服务坏了」。

    根因是构建执行图时会去取对话模型，而这一步原本在 `try` 外面，异常直接穿出
    异步生成器；响应头又早已发出（200 + `text/event-stream`），状态码改不了。

    这类「失败伪装成成功」的问题只断言状态码是发现不了的——200 本来就是预期的
    状态码。必须断言流里到底有没有 error 事件。
    """

    def test_model_build_failure_emits_error_event(self, fake_app, monkeypatch):
        fake_app()

        def _boom():
            raise ProviderError("缺少环境变量 DEEPSEEK_API_KEY")

        monkeypatch.setattr(react_agent, "_current_chat_model", _boom)

        with TestClient(app) as client:
            with client.stream(
                "POST", "/chat", json={"message": "我是谁", "employee_id": SELF}
            ) as resp:
                assert resp.status_code == 200  # 头已发出，只能是 200
                events = parse_sse(resp.read().decode("utf-8"))

        names = [name for name, _ in events]
        assert "error" in names, (
            f"缺 Key 时必须给出 error 事件，否则客户端收到的是空回答；实际事件：{names}"
        )
        assert "DEEPSEEK_API_KEY" in dict(events)["error"]["content"]

    def test_failed_request_is_logged_as_error_not_success(self, fake_app, monkeypatch, caplog):
        """指标日志不能把失败记成 INFO。

        日志是排查这类问题的唯一线索。如果失败请求留下的是 `ttft=n/a chunks=0`
        的 INFO 行，排查的人会往「模型没输出」的方向找，而真正的原因是服务起不来。
        """
        fake_app()

        def _boom():
            raise ProviderError("缺少环境变量 DEEPSEEK_API_KEY")

        monkeypatch.setattr(react_agent, "_current_chat_model", _boom)

        with caplog.at_level("INFO"):
            with TestClient(app) as client:
                client.post("/chat", json={"message": "我是谁", "employee_id": SELF})

        metrics = [r for r in caplog.records if "请求完成" in r.message]
        assert metrics, "每个请求都该留下一条汇总日志"
        assert metrics[-1].levelname == "ERROR", (
            f"失败的请求应记成 ERROR，实际 {metrics[-1].levelname}：{metrics[-1].message}"
        )
        assert "DEEPSEEK_API_KEY" in metrics[-1].message

    def test_failure_after_the_agent_finished_still_reports_error(
        self, fake_app, monkeypatch
    ):
        """Agent 正常跑完、但服务层自己出错，同样不能让客户端收到空回答。

        这一条单独写，是因为它覆盖的是服务层那个 `except` 独有的分支：
        上面两个用例的异常来自 Agent 内部（它自己会兜成 error 事件），
        所以即使服务层不兜也能过。这里让**引用来源整理**抛异常——它在 Agent
        之后、`finally` 之前，Agent 的兜底管不到，只有服务层的兜底能接住。
        """
        fake_app()

        def _boom(_docs):
            raise RuntimeError("来源整理炸了")

        monkeypatch.setattr(server_module, "normalize_sources", _boom)

        with TestClient(app) as client:
            with client.stream(
                "POST", "/chat", json={"message": "我是谁", "employee_id": SELF}
            ) as resp:
                assert resp.status_code == 200
                events = parse_sse(resp.read().decode("utf-8"))

        names = [name for name, _ in events]
        assert "error" in names, (
            f"服务层异常必须显式补一条 error 事件；实际事件：{names}"
        )
        assert "来源整理炸了" in dict(events)["error"]["content"]
        assert names[-1] == "done", "报错之后仍要发 done 收尾，客户端才知道流结束了"


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class TestChatRequestModel:
    def test_oversized_message_is_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="啊" * 5000, employee_id=SELF)

    def test_thread_id_is_optional(self):
        assert ChatRequest(message="你好", employee_id=SELF).thread_id is None
