"""Bound synchronous work without blocking the event loop or building a queue.

Python cannot kill a running thread safely. A timed-out read retains its slot
until it really finishes; further reads fail fast instead of accumulating.
Database and knowledge reads use separate pools so a stalled embedding does
not stop personal-data tools. Workers never publish request results themselves.
"""
import asyncio
from concurrent.futures import Future
from contextvars import copy_context
from functools import partial
import threading


class ReadBusy(RuntimeError):
    pass


class ReadTimedOut(RuntimeError):
    pass


class BoundedReads:
    def __init__(self, workers=2):
        self.slots = threading.BoundedSemaphore(workers)

    async def call(self, function, *args, timeout=30, **kwargs):
        if not self.slots.acquire(blocking=False):
            raise ReadBusy('read capacity exhausted')
        result = Future()
        context = copy_context()
        from agent.runtime import current_run
        runtime = current_run.get()
        if runtime is not None:
            runtime.read_jobs.append(result)

        def run():
            try:
                value = context.run(partial(function,*args,**kwargs))
            except BaseException as exc:
                self.slots.release()
                result.set_exception(exc)
            else:
                self.slots.release()
                result.set_result(value)

        wrapped = asyncio.wrap_future(result)
        wrapped.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        try:
            threading.Thread(target=run,name='bounded-business-read',daemon=True).start()
        except BaseException:
            self.slots.release()
            wrapped.cancel()
            raise
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped),timeout=timeout)
        except TimeoutError as exc:
            raise ReadTimedOut('read deadline exceeded') from exc


DATABASE_READS = BoundedReads(2)
KNOWLEDGE_READS = BoundedReads(2)
