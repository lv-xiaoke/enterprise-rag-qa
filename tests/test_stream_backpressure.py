import asyncio
import time
from sqlalchemy import select
from starlette.requests import Request
from api.routes.conversations import chat
from api.schemas import ChatRequest
from backend.models import User


def test_disconnect_does_not_wait_for_full_event_queue(v1_app, clients):
    client = clients['E1001']
    conversation = client.post('/api/conversations', json={}).json()['id']
    class FloodAgent:
        async def astream_events(self, message, thread_id):
            for _ in range(1000):
                yield {'type': 'token', 'content': 'x'}
    v1_app.state.agent = FloodAgent()
    with v1_app.state.database.session() as db:
        user = db.scalar(select(User).where(User.username == 'E1001'))
    async def exercise():
        request = Request({'type': 'http', 'app': v1_app})
        response = await chat(conversation, ChatRequest(message='flood', client_request_id='disconnect'), request, user)
        stream = response.body_iterator
        await stream.__anext__()
        await asyncio.sleep(.05)
        started = time.perf_counter()
        async with asyncio.timeout(.5):
            await stream.aclose()
        assert time.perf_counter() - started < .3
    asyncio.run(exercise())
