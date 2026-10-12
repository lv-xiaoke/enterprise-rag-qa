import asyncio
import os
import uuid
import pytest
from langchain_core.messages import AIMessage
from agent.react_agent import ReactAgent
from backend.checkpoints import Checkpoints
from backend.settings import Settings
from test_agent_stream import RecordingModel


def exercise_restart(settings):
    async def exercise():
        thread = uuid.uuid4().hex
        first = Checkpoints(settings)
        model = RecordingModel(script=[AIMessage(content='记住了')])
        agent = ReactAgent(model=model, checkpointer=await first.get())
        _ = [event async for event in agent.astream_events('记住暗号 blueberry', thread)]
        await first.close()
        second = Checkpoints(settings)
        resumed_model = RecordingModel(script=[AIMessage(content='blueberry')])
        agent = ReactAgent(model=resumed_model, checkpointer=await second.get())
        _ = [event async for event in agent.astream_events('暗号是什么', thread)]
        assert any('blueberry' in str(m.content) for m in resumed_model.calls[0])
        await second.delete_thread(thread)
        assert await (await second.get()).aget_tuple({'configurable': {'thread_id': thread}}) is None
        await second.close()
    if os.name == 'nt':
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(exercise())
    else:
        asyncio.run(exercise())


def test_sqlite_graph_checkpoint_survives_new_service(tmp_path):
    exercise_restart(Settings(runtime_dir=tmp_path))


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='专用 PostgreSQL 集成 URL 未设置')
def test_postgres_graph_checkpoint_survives_new_connection(tmp_path):
    exercise_restart(Settings(database_url=os.environ['TEST_POSTGRES_URL'], runtime_dir=tmp_path))
