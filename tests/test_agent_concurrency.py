import asyncio
import httpx
from test_chat_lifecycle import events


def test_interleaved_authenticated_runs_never_share_identity(v1_app, clients):
    class InterleavedAgent:
        async def astream_events(self, query, thread_id):
            from agent.tools.agent_tools import get_current_employee
            first = get_current_employee()
            await asyncio.sleep(.02)
            assert first == get_current_employee()
            yield {'type':'token','content':f'{first}:{thread_id}'}
    v1_app.state.agent = InterleavedAgent()
    ids = {name:client.post('/api/conversations',json={}).json()['id'] for name,client in clients.items() if name!='admin'}
    async def run():
        async def request(name):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=v1_app),base_url='http://testserver',
                cookies=dict(clients[name].cookies),headers=dict(clients[name].headers)) as client:
                return await client.post(f'/api/conversations/{ids[name]}/chat',json={'message':'who','client_request_id':'one'})
        return await asyncio.gather(request('E1001'),request('E1002'))
    responses = asyncio.run(run())
    assert 'E1001:' in responses[0].text and 'E1002:' not in responses[0].text
    assert 'E1002:' in responses[1].text and 'E1001:' not in responses[1].text


def test_foreign_chat_and_cancel_do_not_invoke_agent(v1_app, clients):
    class ForbiddenAgent:
        async def astream_events(self,*args):
            raise AssertionError('foreign request reached model')
            yield
    v1_app.state.agent = ForbiddenAgent()
    a,b = clients['E1001'],clients['E1002']
    cid = a.post('/api/conversations',json={}).json()['id']
    assert b.post(f'/api/conversations/{cid}/chat',json={'message':'who','client_request_id':'x'}).status_code == 404
    from backend.models import ChatRun
    with v1_app.state.database.session() as db:
        db.add(ChatRun(id='owned-run',conversation_id=cid,client_request_id='one'))
        db.commit()
    assert b.post('/api/chat-runs/owned-run/cancel').status_code == 404
