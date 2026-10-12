"""Acceptance harness: real HTTP/DB/Chroma, deterministic model substitute."""
import asyncio
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
from api.server import create_app
from backend.settings import Settings
from backend.seed import seed_database
from backend.documents import KnowledgeService
from agent.runtime import current_run
from agent.tools.agent_tools import fetch_employee_records, get_employee_id
from test_ingest_ledger import FakeEmbeddings

directory = Path(__file__).resolve().parents[1] / 'runtime' / 'browser' / uuid.uuid4().hex
app = create_app(Settings(database_url=f'sqlite:///{directory / "business.sqlite"}',
    runtime_dir=directory, app_origin='http://127.0.0.1:5177'))
app.state.database.create_schema()
seed_database(app.state.database, 'Test-only-password!')
app.state.knowledge = KnowledgeService(app.state.database, app.state.settings, embedding=FakeEmbeddings())


class BrowserAgent:
    async def astream_events(self, message, thread_id):
        if '慢速' in message:
            for _ in range(100):
                yield {'type': 'token', 'content': '正在生成。'}
                await asyncio.sleep(.2)
            return
        employee = get_employee_id.invoke({})
        yield {'type': 'tool_call', 'name': 'get_employee_id', 'args': {}}
        if '报销' in message or '周报' in message:
            records = fetch_employee_records.invoke({'employee_id': employee,
                'query_type': 'weekly_report' if '周报' in message else 'reimbursement'})
            text = f'员工 {employee}\n\n本周进展：{records}\n\n下周计划：继续推进项目。'
        else:
            sources = await asyncio.to_thread(current_run.get().knowledge.retrieve, message)
            current_run.get().sources.extend(sources)
            text = '\n'.join(s['excerpt'] for s in sources) or '知识库没有相关依据。'
        for index in range(0, len(text), 10):
            yield {'type': 'token', 'content': text[index:index+10]}
            await asyncio.sleep(.01)


app.state.agent = BrowserAgent()
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8017)
