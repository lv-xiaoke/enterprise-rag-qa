"""Two distinct Python processes, one retained DB/checkpoint directory."""
import json
import os
import subprocess
import sys


def test_pending_and_owned_history_survive_real_process_restart(tmp_path):
    code = r'''
import json, sys
from pathlib import Path
from api.server import create_app
from backend.settings import Settings
from backend.seed import seed_database
from backend.documents import KnowledgeService
from agent.business_agent import BusinessAgent
from eval.agent_fixtures import ScriptedBusinessModel, FixtureEmbeddings
from fastapi.testclient import TestClient
root, phase = Path(sys.argv[1]), sys.argv[2]
app = create_app(Settings(database_url=f'sqlite:///{root / "business.sqlite"}',
    runtime_dir=root,app_origin='http://testserver'))
app.state.database.create_schema()
seed_database(app.state.database,'Process-test-password!')
app.state.knowledge = KnowledgeService(app.state.database,app.state.settings,embedding=FixtureEmbeddings())
script = [{'intent':{'task':'personal'}}] if phase=='prepare' else [
    {'intent':{'task':'personal','query_type':'reimbursement'}},
    {'tool':'get_employee_id'},
    {'tool':'fetch_employee_records','args':{'employee_id':'E1001','query_type':'reimbursement'}},
    {'answer':'补充住宿发票'}]
model = ScriptedBusinessModel(script=script)
with TestClient(app) as client:
    csrf = client.get('/api/auth/csrf').json()['csrf_token']
    client.headers.update({'Origin':'http://testserver','X-CSRF-Token':csrf})
    assert client.post('/api/auth/login',json={'username':'E1001','password':'Process-test-password!'}).status_code==200
    if phase=='prepare':
        cid = client.post('/api/conversations',json={}).json()['id']
        (root/'state.json').write_text(json.dumps({'conversation':cid}))
    else:
        cid = json.loads((root/'state.json').read_text())['conversation']
    app.state.agent = BusinessAgent(model=model,checkpointer=client.portal.call(app.state.checkpoints.get))
    response = client.post(f'/api/conversations/{cid}/chat',json={
        'message':'查一下状态' if phase=='prepare' else '报销','client_request_id':phase})
    assert response.status_code==200
    runs = client.get(f'/api/conversations/{cid}/runs').json()['items']
    messages = client.get(f'/api/conversations/{cid}/messages').json()['items']
    if phase=='verify':
        assert 'query_type' in str(model.calls[0][0].content)
        assert any('查一下状态' in message['content'] for message in messages)
    print(json.dumps({'phase':phase,'business_status':runs[0]['business_status'],'messages':len(messages)}))
'''
    env = {**os.environ,'DEEPSEEK_API_KEY':'','DASHSCOPE_API_KEY':'','PYTHONIOENCODING':'utf-8'}
    outputs = []
    for phase in ['prepare','verify']:
        result = subprocess.run([sys.executable,'-c',code,str(tmp_path),phase],env=env,
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        assert result.returncode==0, result.stderr
        outputs.append(json.loads(result.stdout.splitlines()[-1]))
    assert outputs==[{'phase':'prepare','business_status':'needs_input','messages':2},
                     {'phase':'verify','business_status':'completed','messages':4}]


def test_completed_tool_trace_survives_hard_process_exit_before_answer(tmp_path):
    code = r'''
import json, os, sys
from pathlib import Path
from api.server import create_app
from backend.settings import Settings
from backend.seed import seed_database
from backend.documents import KnowledgeService
from agent.business_agent import BusinessAgent
from eval.agent_fixtures import ScriptedBusinessModel, FixtureEmbeddings
from fastapi.testclient import TestClient
root,phase = Path(sys.argv[1]),sys.argv[2]
app = create_app(Settings(database_url=f'sqlite:///{root / "business.sqlite"}',runtime_dir=root,app_origin='http://testserver'))
app.state.database.create_schema()
seed_database(app.state.database,'Process-test-password!')
app.state.knowledge = KnowledgeService(app.state.database,app.state.settings,embedding=FixtureEmbeddings())
class CrashAfterTools(ScriptedBusinessModel):
    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        if self.cursor==3:
            os._exit(7)
        return super()._generate(messages,stop,run_manager,**kwargs)
with TestClient(app) as client:
    csrf = client.get('/api/auth/csrf').json()['csrf_token']
    client.headers.update({'Origin':'http://testserver','X-CSRF-Token':csrf})
    assert client.post('/api/auth/login',json={'username':'E1001','password':'Process-test-password!'}).status_code==200
    if phase=='crash':
        cid = client.post('/api/conversations',json={}).json()['id']
        (root/'crash-state.json').write_text(json.dumps({'conversation':cid}))
        model = CrashAfterTools(script=[{'intent':{'task':'personal','query_type':'leave_balance'}},
            {'tool':'get_employee_id'},{'tool':'fetch_employee_records','args':{'employee_id':'E1001','query_type':'leave_balance'}}])
        app.state.agent = BusinessAgent(model=model,checkpointer=client.portal.call(app.state.checkpoints.get))
        client.post(f'/api/conversations/{cid}/chat',json={'message':'查年假','client_request_id':'crash'})
        raise AssertionError('process must exit in final answer generation')
    cid = json.loads((root/'crash-state.json').read_text())['conversation']
    run = client.get(f'/api/conversations/{cid}/runs').json()['items'][0]
    results = [e for e in run['tool_events'] if e['type']=='tool_result']
    assert [e['name'] for e in results]==['get_employee_id','fetch_employee_records']
    assert all(e['status']=='ok' for e in results)
    assert run['status']==run['business_status']=='interrupted'
    print(json.dumps({'status':run['status'],'tool_results':len(results)}))
'''
    env = {**os.environ,'DEEPSEEK_API_KEY':'','DASHSCOPE_API_KEY':'','PYTHONIOENCODING':'utf-8'}
    crashed = subprocess.run([sys.executable,'-c',code,str(tmp_path),'crash'],env=env,
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert crashed.returncode==7, crashed.stderr
    resumed = subprocess.run([sys.executable,'-c',code,str(tmp_path),'verify'],env=env,
        capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert resumed.returncode==0, resumed.stderr
    assert json.loads(resumed.stdout.splitlines()[-1])=={'status':'interrupted','tool_results':2}
