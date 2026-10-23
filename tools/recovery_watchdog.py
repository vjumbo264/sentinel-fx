"""Extend READY chains with durable, idempotent recovery; never start new training.
The scheduled caller runs independently of a cancelled runner. Real broker lease
and GitHub active-run checks both apply before any replacement dispatch.
"""
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.net_retry import urlopen
from tools.release_utils import GitHub
import urllib.request

COOLDOWNS = (1800, 7200, 21600)
ACTIVE = {'queued', 'in_progress', 'waiting', 'pending', 'requested'}
FAILED = {'failure', 'cancelled', 'timed_out', 'startup_failure', 'action_required', 'stale'}


def utc():
    return datetime.now(timezone.utc)


def classify(conclusion, text):
    # Explicit code/auth errors win over the event type: a scheduled login
    # failure is still a code/config error, not a GitHub incident.
    code = re.search(r'(?:ModuleNotFoundError|SyntaxError|IndentationError|NameError|AssertionError|ValueError|TypeError|KeyError):[^\n]*|(?:login failed|authorization failed|terminal not trading-ready)[^\n]*', text, re.I)
    network = re.search(r'(?:HTTP (?:Error )?5\d\d|502 Bad Gateway|503 Service Unavailable|ConnectionResetError|connection reset|URLError|runner.*(?:unavailable|lost communication)|hosted runner.*(?:error|failed))[^\n]*', text, re.I)
    if network and not code:
        return 'platform', network[0][-500:]
    if code:
        return 'code', code[0][-500:]
    if conclusion in {'cancelled', 'timed_out', 'startup_failure', 'stale'}:
        return 'platform', 'GitHub run '+conclusion
    return 'code', 'Unclassified workflow failure; inspect original run logs'


def next_failure(previous, run, kind, reason, now=None):
    now = now or utc()
    if str(previous.get('source_run')) == str(run['id']):
        return previous
    n = int(previous.get('consecutive_failures', 0))+1 if previous.get('failure_kind') == kind and previous.get('status') != 'recovered' else 1
    delay = COOLDOWNS[min(n-1, 2)] if kind == 'platform' else 90*(n+1)
    return {'status': 'code_failure_halted' if kind == 'code' and n >= 3 else 'recovering',
            'source_run': str(run['id']), 'run_url': run.get('html_url'), 'failure_kind': kind,
            'consecutive_failures': n, 'reason': reason, 'error': reason,
            'failed_at_utc': now.isoformat(), 'next_try_utc': (now+timedelta(seconds=delay)).isoformat(),
            'delay_seconds': delay}


class Watchdog:
    def __init__(self):
        token = os.environ.get('GH_CHAIN_PAT') or os.environ.get('GH_TOKEN_FOR_CHAIN') or os.environ.get('GITHUB_TOKEN')
        self.gh = GitHub(token)
        self.worker_url = os.environ.get('WORKER_URL', '').rstrip('/')
        self.secret = os.environ.get('BOT_SHARED_SECRET', '')

    def worker(self, path, body=None):
        req = urllib.request.Request(self.worker_url+path, data=json.dumps(body).encode() if body is not None else None,
              headers={'X-Bot-Secret':self.secret, 'Content-Type':'application/json', 'User-Agent':'sentinel-recovery/1.0'})
        with urlopen(req) as response:
            return json.load(response)

    def runs(self, name):
        return self.gh.request('GET', '/actions/workflows/'+name+'/runs?per_page=40').json()['workflow_runs']

    def logs(self, run):
        raw = self.gh.request('GET', '/actions/runs/'+str(run['id'])+'/logs').content
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return '\n'.join(archive.read(n).decode('utf8','replace') for n in archive.namelist() if n.startswith('0_'))

    def report_bot_failure(self, run, text=None):
        state = self.worker('/api/bot/state');previous=state['settings'].get('bot_recovery',{})
        if str(previous.get('source_run')) == str(run['id']):return previous
        kind, reason = classify(run.get('conclusion'), text if text is not None else self.logs(run))
        for key,value in os.environ.items():
            if any(s in key for s in ('PASSWORD','SECRET','TOKEN','PAT')) and len(value)>5:reason=reason.replace(value,'[redacted]')
        updated = next_failure(previous,run,kind,reason)
        self.worker('/api/bot/recovery-record',updated)
        self.worker('/api/bot/log',{'level':'critical','pair':'*','message':f"Bot recovery {updated['status']}: {reason}; next try {updated['next_try_utc']}",'data':{'run_url':run.get('html_url'),'failure_kind':kind}})
        return updated

    def bot(self):
        runs=self.runs('bot.yml')
        # Do not revive older failures after a newer successful bounded run.
        latest=next((r for r in runs if r.get('status')=='completed'),None)
        if latest and latest.get('conclusion') in FAILED:self.report_bot_failure(latest)
        if any(r.get('status') in ACTIVE for r in runs):
            print('BOT: live/queued run exists; no replacement');return
        state=self.worker('/api/bot/state');recovery=state['settings'].get('bot_recovery',{})
        if recovery.get('status')!='recovering':return
        if datetime.fromisoformat(recovery['next_try_utc'].replace('Z','+00:00'))>utc():
            print('BOT: durable cooldown until',recovery['next_try_utc']);return
        claim=self.worker('/api/bot/recovery-claim',{'source_run':recovery['source_run']})
        if not claim.get('acquired'):
            print('BOT: lease/READY/recovery claim held; no duplicate');return
        # This project is deliberately left in demo. A recovery cannot promote it.
        if state['settings'].get('mode','demo')!='demo':
            print('BOT: recovery refuses non-demo mode');return
        self.gh.dispatch('bot.yml',{'mode':'demo'})
        print('BOT: replacement dispatched after durable cooldown')

    def training(self):
        # Read current remote state, not the checkout from a prior checkpoint.
        content=self.gh.request('GET','/contents/training_state.json?ref=main').json()
        import base64
        state=json.loads(base64.b64decode(content['content']))
        if not state.get('owner_started') or state.get('paused') or state.get('status') not in {'training','checkpointed','resuming'}:
            print('TRAIN: no active owner-started cycle; watchdog does nothing');return
        heartbeat=state.get('heartbeat_utc') or state.get('updated_utc') or state.get('last_checkpoint_utc')
        if not heartbeat or (utc()-datetime.fromisoformat(heartbeat.replace('Z','+00:00'))).total_seconds()<=1800:return
        if any(r.get('status') in ACTIVE for r in self.runs('train.yml')):
            print('TRAIN: active/queued writer exists');return
        settings=self.worker('/api/bot/state')['settings']
        if settings.get('training_paused'):
            print('TRAIN: owner paused; no resume');return
        self.gh.dispatch('train.yml',{'mode':'resume'})
        print('TRAIN: stale owner-started cycle dispatched from durable checkpoint; single-writer concurrency unchanged')


def main():
    # Deliberately staged: atomic Worker record/claim routes and live recovery
    # acceptance are not yet installed. Do not turn an incomplete integration
    # into an automatically scheduled chain.
    if os.environ.get('FIX5_RECOVERY_INTEGRATION_READY') != 'true':
        raise SystemExit('Recovery integration is staged, not enabled: install/verify Worker recovery-record and recovery-claim routes first')
    watcher=Watchdog();watcher.bot();watcher.training()

if __name__=='__main__':main()
