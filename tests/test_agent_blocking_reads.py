import asyncio
import threading


def test_stalled_read_has_bounded_workers_and_does_not_block_another_pool():
    from agent.blocking_reads import BoundedReads, ReadBusy, ReadTimedOut
    blocked = BoundedReads(1)
    other = BoundedReads(1)
    release = threading.Event()
    entered = threading.Event()
    def stall():
        entered.set()
        release.wait(5)
        return 'stale result'
    async def run():
        import pytest
        with pytest.raises(ReadTimedOut):
            await blocked.call(stall,timeout=.03)
        assert entered.is_set()
        with pytest.raises(ReadBusy):
            await blocked.call(lambda:'must not enqueue',timeout=.03)
        assert await other.call(lambda:'other user can continue',timeout=.1)=='other user can continue'
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_embedding_wait_does_not_hold_document_version_lock(v1_app):
    from backend.documents import KnowledgeService
    from backend.models import User
    from sqlalchemy import select
    from eval.agent_fixtures import FixtureEmbeddings
    release,entered = threading.Event(),threading.Event()
    class SlowQueryEmbedding(FixtureEmbeddings):
        def embed_query(self,text):
            entered.set()
            release.wait(5)
            return super().embed_query(text)
        def embed_documents(self,texts):
            return [FixtureEmbeddings.embed_query(self,text) for text in texts]
    service = KnowledgeService(v1_app.state.database,v1_app.state.settings,embedding=SlowQueryEmbedding())
    with v1_app.state.database.session() as db:
        admin = db.scalar(select(User).where(User.username=='admin'))
        service.upload('policy.txt','模拟制度：请先审批。'.encode(),admin.id)
    service.process_queued()
    thread = threading.Thread(target=service.retrieve,args=('审批制度',),daemon=True)
    thread.start()
    acquired = False
    try:
        assert entered.wait(2)
        acquired = service._lock.acquire(blocking=False)
        assert acquired
    finally:
        if acquired:
            service._lock.release()
        release.set()
        thread.join(3)
    assert not thread.is_alive()


def test_timed_out_read_is_not_retried_and_cannot_publish_late_evidence(v1_app):
    from agent.execution import ExecutionBudget, execute_business_tool
    from agent.runtime import RunContext,current_run
    from agent.tools.agent_tools import _current_employee
    release = threading.Event()
    class SlowKnowledge:
        def retrieve(self,query,k=3):
            release.wait(5)
            return [{'chunk_id':'late','excerpt':'must not leak into next turn'}]
    runtime = RunContext('u','E1001',v1_app.state.database,SlowKnowledge(),budget=ExecutionBudget(tool_timeout=.03))
    token = current_run.set(runtime)
    identity = _current_employee.set('E1001')
    async def run():
        result = await runtime.budget.execute('rag_summarize',{'query':'q'},'slow',lambda event:None,execute_business_tool)
        assert result.code=='TOOL_TIMEOUT'
        assert runtime.budget.total==1
        assert (await execute_business_tool('get_employee_id',{})).data=='E1001'
        release.set()
        await asyncio.sleep(.05)
        assert runtime.sources==[]
    try:
        asyncio.run(run())
    finally:
        release.set()
        current_run.reset(token)
        _current_employee.reset(identity)
