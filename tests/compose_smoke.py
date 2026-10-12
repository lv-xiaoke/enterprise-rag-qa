"""Run against an isolated Compose instance. Never requires an LLM key.
prepare -> restart backend -> verify; state contains resource IDs, no credentials.
"""
import argparse
import json
import os
from pathlib import Path
import uuid
import httpx


def login(base_url, username):
    client = httpx.Client(base_url=base_url, timeout=30)
    csrf = client.get('/api/auth/csrf').json()['csrf_token']
    client.headers.update({'Origin':base_url,'X-CSRF-Token':csrf})
    response = client.post('/api/auth/login',json={'username':username,'password':os.environ['DEMO_PASSWORD']})
    response.raise_for_status()
    return client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=['prepare','verify'])
    parser.add_argument('--base-url',default='http://127.0.0.1:18080')
    parser.add_argument('--state',type=Path,default=Path('runtime/compose-smoke.json'))
    args = parser.parse_args()
    assert httpx.get(args.base_url+'/api/ready').status_code == 200
    assert httpx.get(args.base_url+'/chat').status_code != 200 or 'text/html' in httpx.get(args.base_url+'/chat').headers.get('content-type','')
    with login(args.base_url,'E1001') as first:
        if args.phase == 'prepare':
            marker = uuid.uuid4().hex
            conversation = first.post('/api/conversations',json={}).json()['id']
            report = first.post('/api/weekly-reports',json={'title':'容器验收 '+marker,'content':'持久化标记 '+marker})
            report.raise_for_status()
            state = {'conversation':conversation,'report':report.json()['id'],'marker':marker}
            with login(args.base_url,'E1002') as second:
                assert second.get(f'/api/conversations/{conversation}/messages').status_code == 404
                assert second.get(f'/api/weekly-reports/{state["report"]}').status_code == 404
            args.state.parent.mkdir(parents=True,exist_ok=True)
            args.state.write_text(json.dumps(state),encoding='utf-8')
        else:
            state = json.loads(args.state.read_text(encoding='utf-8'))
            report = first.get(f'/api/weekly-reports/{state["report"]}')
            report.raise_for_status()
            assert state['marker'] in report.json()['content']
            assert first.get(f'/api/conversations/{state["conversation"]}/messages').status_code == 200
            assert first.patch(f'/api/weekly-reports/{state["report"]}',json={'content':'重启后编辑成功'}).status_code == 200
            # Exercises real PostgreSQL checkpoint cleanup through the API.
            assert first.delete(f'/api/conversations/{state["conversation"]}/messages').status_code == 200
    print(f'Compose {args.phase}: health, auth, ownership and persistence checks passed')


if __name__ == '__main__':
    main()
