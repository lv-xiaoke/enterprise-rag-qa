from contextlib import AsyncExitStack


class Checkpoints:
    def __init__(self, settings):
        self.settings = settings
        self.stack = AsyncExitStack()
        self.saver = None

    async def get(self):
        if self.saver is None:
            if self.settings.database_url.startswith('postgresql'):
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                url = self.settings.database_url.replace('postgresql+psycopg://', 'postgresql://')
                saver = await self.stack.enter_async_context(AsyncPostgresSaver.from_conn_string(url))
                await saver.setup()
            else:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                path = self.settings.runtime_dir / 'checkpoints.sqlite'
                path.parent.mkdir(parents=True, exist_ok=True)
                saver = await self.stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(path)))
                await saver.setup()
            self.saver = saver
        return self.saver

    async def close(self):
        await self.stack.aclose()
        self.saver = None

    async def delete_thread(self, thread_id):
        saver = await self.get()
        if self.settings.database_url.startswith('postgresql'):
            # Version 2.0.9 supports LangGraph 0.2 but lacks adelete_thread.
            # Only this server-generated conversation thread is removed.
            async with saver.lock, saver.conn.transaction():
                for table in ('checkpoint_writes', 'checkpoint_blobs', 'checkpoints'):
                    await saver.conn.execute(f'DELETE FROM {table} WHERE thread_id = %s', (thread_id,))
        else:
            await saver.adelete_thread(thread_id)
