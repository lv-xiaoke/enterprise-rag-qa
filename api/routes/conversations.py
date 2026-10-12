import asyncio
import contextlib
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from api.dependencies import CurrentUser, pagination, require_csrf
from api.schemas import ChatRequest, ConversationRequest
from agent.runtime import RunContext, current_run
from agent.tools.agent_tools import _current_employee
from backend.conversations import finish_run, owned_conversation, reserve_run, serialize
from backend.models import ChatRun, Conversation, Message, new_id

router = APIRouter(tags=['会话'])
log = logging.getLogger('agent')


def sse(kind, data):
    return f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


@router.post('/conversations', status_code=201, dependencies=[Depends(require_csrf)])
def create_conversation(body: ConversationRequest, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        row = Conversation(user_id=user.id, title=body.title)
        db.add(row)
        db.commit()
        return serialize(row, ('id', 'title', 'created_at', 'updated_at'))


@router.get('/conversations')
def list_conversations(request: Request, user: CurrentUser, page=Depends(pagination)):
    limit, offset = page
    with request.app.state.database.session() as db:
        query = select(Conversation).where(Conversation.user_id == user.id)
        rows = db.scalars(query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)).all()
        return {'items': [serialize(row, ('id', 'title', 'updated_at')) for row in rows],
                'total': db.scalar(select(func.count()).select_from(query.subquery()))}


@router.get('/conversations/{conversation_id}/messages')
def list_messages(conversation_id: str, request: Request, user: CurrentUser, page=Depends(pagination)):
    limit, offset = page
    with request.app.state.database.session() as db:
        owned_conversation(db, conversation_id, user.id)
        query = select(Message).where(Message.conversation_id == conversation_id)
        rows = db.scalars(query.order_by(Message.created_at, Message.id).limit(limit).offset(offset)).all()
        return {'items': [serialize(row, ('id', 'role', 'content', 'status', 'sources', 'created_at')) for row in rows],
                'total': db.scalar(select(func.count()).select_from(query.subquery()))}


async def get_agent(app):
    if app.state.agent is None:
        async with app.state.agent_lock:
            if app.state.agent is None:
                from agent.react_agent import ReactAgent
                from model.factory import build_chat_model
                checkpoint = await app.state.checkpoints.get()
                app.state.agent = ReactAgent(model=build_chat_model(), checkpointer=checkpoint)
    return app.state.agent


@router.post('/conversations/{conversation_id}/chat', dependencies=[Depends(require_csrf)])
async def chat(conversation_id: str, body: ChatRequest, request: Request, user: CurrentUser):
    state = request.app.state
    run, thread_id = reserve_run(state.database, state.reservation_lock, conversation_id, user.id, body)
    stop = asyncio.Event()
    state.run_controls[run.id] = stop

    async def stream():
        context = RunContext(user.id, user.employee_id, state.database, state.knowledge)
        started = time.perf_counter()
        content, status, error_code, ttft = '', 'completed', None, None
        queue = asyncio.Queue(maxsize=128)

        async def produce():
            context_token = current_run.set(context)
            identity_token = _current_employee.set(user.employee_id)
            try:
                agent = await get_agent(request.app)
                async for event in agent.astream_events(body.message, thread_id):
                    await queue.put(event)
            except Exception:
                log.exception('chat_failed run=%s', run.id)
                await queue.put({'type': 'error'})
                await queue.put(None)
            else:
                await queue.put(None)
            finally:
                current_run.reset(context_token)
                _current_employee.reset(identity_token)

        producer = asyncio.create_task(produce())
        stopper = asyncio.create_task(stop.wait())
        pending_read = None
        try:
            yield sse('start', {'run_id': run.id, 'conversation_id': conversation_id})
            async with asyncio.timeout(state.settings.chat_timeout_seconds):
                while True:
                    pending_read = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait([pending_read, stopper], return_when=asyncio.FIRST_COMPLETED)
                    if stopper in done:
                        status = 'cancelled'
                        break
                    event = pending_read.result()
                    pending_read = None
                    if event is None:
                        break
                    kind = event['type']
                    if kind == 'error':
                        status, error_code = 'failed', 'MODEL_ERROR'
                        yield sse('error', {'code': error_code, 'message': '生成失败，请检查模型配置或稍后重试'})
                        break
                    if kind == 'token':
                        content += event.get('content', '')
                        if ttft is None:
                            ttft = (time.perf_counter() - started) * 1000
                    if kind in {'token', 'tool_call', 'tool_result'}:
                        yield sse(kind, {key: value for key, value in event.items() if key != 'type'})
        except TimeoutError:
            status, error_code = 'failed', 'TIMEOUT'
            yield sse('error', {'code': error_code, 'message': '生成超时，请稍后重试'})
        except (asyncio.CancelledError, GeneratorExit):
            status = 'cancelled'
            raise
        finally:
            for task in [producer, stopper, pending_read]:
                if task and not task.done():
                    task.cancel()
            for task in [producer, stopper, pending_read]:
                if task:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            finish_run(state.database, run.id, content, status, context.sources, error_code, ttft, context.usage)
            state.run_controls.pop(run.id, None)
            log.info('chat_finished run=%s status=%s ttft_ms=%s', run.id, status, ttft)
        if context.sources:
            yield sse('sources', {'sources': context.sources})
        yield sse('done', {'run_id': run.id, 'status': status})

    return StreamingResponse(stream(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
    })


@router.post('/chat-runs/{run_id}/cancel', dependencies=[Depends(require_csrf)])
async def cancel(run_id: str, request: Request, user: CurrentUser):
    with request.app.state.database.session() as db:
        run = db.get(ChatRun, run_id)
        if not run:
            raise HTTPException(404, '运行不存在')
        owned_conversation(db, run.conversation_id, user.id)
        run.cancel_requested = True
        db.commit()
    control = request.app.state.run_controls.get(run_id)
    if control:
        control.set()
    return {'ok': True}


@router.delete('/conversations/{conversation_id}/messages', dependencies=[Depends(require_csrf)])
async def clear_messages(conversation_id: str, request: Request, user: CurrentUser):
    state = request.app.state
    with state.reservation_lock, state.database.session() as db:
        row = owned_conversation(db, conversation_id, user.id)
        if db.scalar(select(ChatRun).where(ChatRun.conversation_id == row.id, ChatRun.status == 'running')):
            raise HTTPException(409, '请先停止生成')
        # Rotate before clearing: a failed checkpoint cleanup cannot restore old memory.
        old_thread = row.thread_id
        row.thread_id = new_id()
        db.execute(delete(Message).where(Message.conversation_id == row.id))
        db.execute(delete(ChatRun).where(ChatRun.conversation_id == row.id))
        db.commit()
    await state.checkpoints.delete_thread(old_thread)
    return {'ok': True}
