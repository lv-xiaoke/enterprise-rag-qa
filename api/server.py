"""Authenticated FastAPI entry point. Model clients are constructed only on use."""
import asyncio
from contextlib import asynccontextmanager
import logging
import secrets
import threading
import time
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy import text, update, select
from backend.auth import hasher
from backend.checkpoints import Checkpoints
from backend.db import Database
from backend.models import ChatRun, DocumentVersion, Message
from backend.settings import Settings
from api.schemas import ChatRequest
from api.routes.conversations import sse as _sse


def create_app(settings=None):
    settings = settings or Settings.from_env()
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        with app.state.database.session() as db:
            for run in db.scalars(select(ChatRun).where(ChatRun.status == 'running')):
                run.status, run.error_code, run.ended_at = 'interrupted', 'INTERRUPTED', time.time()
                db.add(Message(conversation_id=run.conversation_id, role='assistant',
                    content='服务重启中断了本次生成，请重新提问。', status='interrupted'))
            db.execute(update(DocumentVersion).where(DocumentVersion.status == 'processing').values(
                status='failed', error_code='INTERRUPTED'))
            db.commit()
        if app.state.knowledge is not None:
            await app.state.knowledge.start()
        try:
            yield
        finally:
            if app.state.knowledge is not None:
                await app.state.knowledge.close()
            await app.state.checkpoints.close()
            app.state.database.engine.dispose()

    app = FastAPI(title='企业知识与事务助手', version='2.0.0', lifespan=lifespan)
    app.state.settings = settings
    app.state.database = Database(settings.database_url)
    app.state.checkpoints = Checkpoints(settings)
    app.state.agent = None
    from backend.documents import KnowledgeService
    app.state.knowledge = KnowledgeService(app.state.database, settings)
    app.state.agent_lock = asyncio.Lock()
    app.state.reservation_lock = threading.RLock()
    app.state.run_controls = {}
    app.state.login_attempts = {}
    app.state.dummy_password_hash = hasher.hash(secrets.token_urlsafe(32))

    @app.middleware('http')
    async def identify_request(request: Request, call_next):
        request.state.request_id = secrets.token_hex(12)
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def error_response(request, status, code, message):
        return JSONResponse(status_code=status, content={'error': {
            'code': code, 'message': message, 'request_id': getattr(request.state, 'request_id', '')}})

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, f'HTTP_{exc.status_code}', str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(request, 422, 'VALIDATION_ERROR', '请求字段格式或长度不正确')

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger('agent').exception('request_failed id=%s', request.state.request_id)
        return error_response(request, 500, 'INTERNAL_ERROR', '服务处理失败，请稍后重试')

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.get('/api/ready')
    def ready(request: Request):
        try:
            with app.state.database.session() as db:
                db.execute(text('SELECT 1 FROM users LIMIT 1'))
            return {'status': 'ready'}
        except Exception:
            return error_response(request, 503, 'NOT_READY', '数据库尚未就绪')

    from api.routes import auth, conversations, documents, reports
    for module in (auth, conversations, documents, reports):
        app.include_router(module.router, prefix='/api')
    return app


app = create_app()
