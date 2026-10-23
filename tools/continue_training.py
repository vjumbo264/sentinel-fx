"""Completion-event recovery of an owner-started cycle; never creates a cycle."""
import base64
import json
import os
import time
import urllib.request
import urllib.error

BASE = 'https://api.github.com/repos/' + os.environ.get('GITHUB_REPOSITORY', 'vjumbo264/sentinel-fx')
TOKEN = os.environ.get('GH_CHAIN_PAT') or os.environ['GITHUB_TOKEN']

def request(path, body=None):
    for attempt in range(4):
        try:
            req = urllib.request.Request(BASE + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization':'Bearer '+TOKEN, 'Accept':'application/vnd.github+json',
                         'User-Agent':'sentinel-training-continuation','Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw=response.read()
                return json.loads(raw) if raw else {}
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def main():
    state_file=request('/contents/training_state.json?ref=main')
    state=json.loads(base64.b64decode(state_file['content']))
    if state.get('status') in ('idle','complete','cancelled') or not state.get('pairs_pending'):
        print('Owner cycle complete/idle; no automatic new training.')
        return
    # Old in-flight revisions may already dispatch their own successor. Never add a second.
    runs=request('/actions/workflows/train.yml/runs?per_page=100')['workflow_runs']
    writers=[r for r in runs if r['status'] != 'completed']
    if writers:
        print('Existing writer/queued successor preserved:', ', '.join(str(r['id']) for r in writers))
        return
    request('/actions/workflows/train.yml/dispatches', {'ref':'main','inputs':{'mode':'resume'}})
    print('Resumed owner cycle from durable checkpoint',state.get('total_steps_done',0),state.get('active_pair'))

if __name__ == '__main__': main()
