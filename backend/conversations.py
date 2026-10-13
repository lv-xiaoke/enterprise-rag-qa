import time
from fastapi import HTTPException
from sqlalchemy import delete, select
from backend.models import ChatRun, Conversation, Message


def owned_conversation(db, conversation_id, user_id):
    row = db.get(Conversation, conversation_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, '会话不存在')
    return row


def serialize(row, keys):
    return {key: getattr(row, key) for key in keys}


def reserve_run(database, lock, conversation_id, user_id, body):
    with lock, database.session() as db:
        conversation = owned_conversation(db, conversation_id, user_id)
        duplicate = db.scalar(select(ChatRun).where(
            ChatRun.conversation_id == conversation_id,
            ChatRun.client_request_id == body.client_request_id))
        active = db.scalar(select(ChatRun).where(
            ChatRun.conversation_id == conversation_id, ChatRun.status == 'running'))
        if duplicate or active:
            raise HTTPException(409, '请求已处理或会话正在生成，请查看历史后再试')
        run = ChatRun(conversation_id=conversation_id, client_request_id=body.client_request_id)
        db.add(run)
        db.add(Message(conversation_id=conversation_id, role='user', content=body.message))
        if conversation.title == '新对话':
            conversation.title = body.message[:40]
        conversation.updated_at = time.time()
        db.commit()
        return run, conversation.thread_id


def finish_run(database, run_id, content, status, sources, error_code, ttft_ms, usage,
               tool_events=None, intent=None, business_status=None):
    with database.session() as db:
        run = db.get(ChatRun, run_id)
        run.status, run.error_code = status, error_code
        run.ended_at = time.time()
        run.total_ms = (run.ended_at - run.started_at) * 1000
        run.ttft_ms, run.usage = ttft_ms, usage or None
        run.tool_events, run.intent = tool_events or [], intent or {}
        run.business_status = business_status or status
        db.add(Message(conversation_id=run.conversation_id, role='assistant', content=content,
                       status=status, sources=sources))
        db.commit()
