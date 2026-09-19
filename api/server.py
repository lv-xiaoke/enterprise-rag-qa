"""FastAPI + SSE 服务层。

为什么要有这一层
----------------
Streamlit 界面适合演示，但它不是能被别的系统调用的形态。真实的企业助手
通常要挂到 OA、IM 机器人、内部搜索框后面，所以需要 HTTP 接口。
`requirements.txt` 里锁了 fastapi / uvicorn，对应的代码就在这里。

为什么是 SSE 而不是 WebSocket
-----------------------------
这条链路是**单向**的：客户端发一次提问，服务端持续推 token，推完即结束。
SSE 正好是这个形状——普通 HTTP、浏览器原生自动重连、不需要额外协议握手，
也更容易穿过企业网关（WebSocket 常被代理挡掉）。双向通信能力这里用不上。

关于身份隔离
------------
每个请求在生成器开头 `set_current_employee()`，且必须走**异步**生成器。
原因见 `ReactAgent.astream_events` 的说明：交给线程池迭代会因为 ContextVar
被逐次还原而静默丢掉身份，连越权校验一起失效——不报任何错。
`tests/test_api.py` 里有一个并发用例专门盯这件事。

跑起来
------
    uvicorn api.server:app --reload
    # 或
    python -m api.server
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.react_agent import ReactAgent, new_thread_id
from agent.tools.agent_tools import list_employees, set_current_employee
from rag.rag_service import last_retrieved_docs, normalize_sources
from utils.logger_handler import logger

MAX_MESSAGE_CHARS = 2000


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    employee_id: str = Field(
        ..., min_length=1, description="当前登录员工，决定工具能查到谁的数据"
    )
    thread_id: str | None = Field(
        None, description="会话 ID。不传则新建；传同一个 ID 可延续上下文"
    )


class Employee(BaseModel):
    employee_id: str
    employee_name: str
    department: str


class ResetResult(BaseModel):
    thread_id: str
    cleared: bool


# ---------------------------------------------------------------------------
# 可观测性
# ---------------------------------------------------------------------------


class RequestMetrics:
    """单次请求的运行指标，请求结束时汇总成一行日志。

    为什么不逐 token 打日志：这条链路的日志量本来就大，逐 token 打会淹掉
    真正有用的信息。攒成一行，既有首字延迟 / 总耗时 / 工具调用序列，
    又不至于把日志变成流水账。

    首字延迟（TTFT）单独记：用户体感上「卡不卡」几乎只取决于它，总耗时反而
    次要——总耗时 8 秒但 0.5 秒就出字，比 3 秒憋出一整段要好受得多。
    """

    def __init__(self, thread_id: str, employee_id: str) -> None:
        self.thread_id = thread_id
        self.employee_id = employee_id
        self._started = time.perf_counter()
        self._first_token_at: float | None = None
        self.chunks = 0
        self.chars = 0
        self.tool_calls: list[str] = []
        self.error: str | None = None

    def observe(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "tool_call":
            self.tool_calls.append(event.get("name", ""))
        elif kind == "token":
            if self._first_token_at is None:
                self._first_token_at = time.perf_counter()
            self.chunks += 1
            self.chars += len(event.get("content", ""))
        elif kind == "error":
            self.error = event.get("content", "")

    def log(self) -> None:
        total_ms = (time.perf_counter() - self._started) * 1000
        ttft = (
            f"{(self._first_token_at - self._started) * 1000:.0f}ms"
            if self._first_token_at is not None
            else "n/a"
        )
        line = (
            f"[请求完成] thread={self.thread_id} employee={self.employee_id} "
            f"ttft={ttft} total={total_ms:.0f}ms chunks={self.chunks} "
            f"chars={self.chars} tools={self.tool_calls or '无'}"
        )
        if self.error:
            logger.error(f"{line} error={self.error.strip()[:120]}")
        else:
            logger.info(line)


# ---------------------------------------------------------------------------
# SSE 编码
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict) -> str:
    """编码一条 SSE 消息。

    用带 `event:` 的具名事件，而不是把类型塞进 data 里：客户端可以直接
    `addEventListener("tool_call", ...)` 分派，不必先 parse JSON 再 switch。

    `ensure_ascii=False` 保留中文原样（SSE 本身就是 UTF-8，转义成 \\uXXXX
    只会让 curl 调试时看不懂）；`json.dumps` 会把换行转义掉，正好满足
    SSE「data 不能含裸换行」的要求。
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ReactAgent 构造很轻（图是惰性建的），但没必要每个请求建一个：
    # 它持有系统提示词，记忆 checkpointer 又是模块级的，实例复用没有副作用。
    app.state.agent = ReactAgent()
    app.state.employees = {e["employee_id"]: e for e in list_employees()}
    logger.info(f"[服务启动]已加载 {len(app.state.employees)} 个可选身份")
    yield


app = FastAPI(
    title="企业知识库 Agent 服务",
    description="LangGraph 工具调用 Agent + 混合检索 RAG，SSE 流式输出。",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", summary="健康检查")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/employees", response_model=list[Employee], summary="列出可选登录身份")
async def employees() -> list[dict]:
    return list_employees()


@app.post("/chat", summary="流式问答（SSE）")
async def chat(req: ChatRequest) -> StreamingResponse:
    if req.employee_id not in app.state.employees:
        # 未知身份是客户端错误，直接 400。不要「回退到默认员工」——
        # 那会让一个拼错的 ID 静默地以别人的身份查数据。
        raise HTTPException(status_code=400, detail=f"未知员工：{req.employee_id}")

    thread_id = req.thread_id or new_thread_id()

    async def event_stream() -> AsyncIterator[str]:
        # 身份绑定放在最前面，且在这个异步生成器内部：整段都在同一个任务
        # 上下文里，工具层读到的就是这里 set 的值。
        set_current_employee(req.employee_id)
        metrics = RequestMetrics(thread_id, req.employee_id)

        yield _sse("start", {"thread_id": thread_id})

        try:
            async for event in app.state.agent.astream_events(req.message, thread_id):
                metrics.observe(event)
                payload = {k: v for k, v in event.items() if k != "type"}
                yield _sse(event["type"], payload)

            # 引用来源：读业务路径登记的那一批，不重新检索
            sources = normalize_sources(last_retrieved_docs())
            if sources:
                yield _sse("sources", {"sources": sources})
        except Exception as exc:
            # Agent 内部已经兜了一层，这里兜的是「异常在进入 Agent 之前就发生」
            # 的情况——比如启动后才发现配置写错。不兜的话会很难看：响应头早已
            # 发出（200 + text/event-stream），状态码改不了，异常只能让连接断开，
            # 而 `finally` 里那句 `done` 照发——客户端收到的是一个正常收尾的空
            # 回答。必须显式补一条 error 事件，并让指标日志记成 error。
            logger.error(f"[服务]请求处理失败 thread={thread_id}：{exc}", exc_info=True)
            metrics.error = str(exc)
            yield _sse("error", {"content": f"处理失败：{exc}"})
        finally:
            # 放在 finally 里：客户端中途断开（StreamingResponse 被取消）时
            # 也要留下这行日志，否则「请求为什么没有输出」在日志里无从查起。
            metrics.log()
            yield _sse("done", {"thread_id": thread_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # 告诉 nginx 之类的反代不要缓冲，否则 token 会攒到最后一次性吐出，
            # 流式就白做了。
            "X-Accel-Buffering": "no",
        },
    )


@app.delete(
    "/sessions/{thread_id}", response_model=ResetResult, summary="清空某个会话的记忆"
)
async def reset_session(thread_id: str) -> ResetResult:
    app.state.agent.reset_memory(thread_id)
    return ResetResult(thread_id=thread_id, cleared=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=False)
