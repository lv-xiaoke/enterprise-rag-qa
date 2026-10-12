"""Windows psycopg requires a selector loop; Linux uses Uvicorn defaults."""
import asyncio
import os
import uvicorn

if __name__ == '__main__':
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run('api.server:app', host='127.0.0.1', port=8000, loop='asyncio', workers=1)
