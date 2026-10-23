#!/usr/bin/env python3
"""Resumable per-pair CPU PPO, immutable checkpoints and checked live bundles."""
import argparse
import copy
import hashlib
import io
import json
import os
import re
import signal
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from tools.train_env import SentinelScalpEnv
from tools.release_utils import ROOT, GitHub, pair_key
from tools.export_rl_bundle import export_bundle

PAIRS = 'EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD EURGBP EURJPY GBPJPY AUDJPY EURAUD GBPAUD'.split()
STATE = ROOT / 'training_state.json'
STOP = False

def utc():
    return datetime.now(timezone.utc).isoformat()

def new_state():
    return {'queue': PAIRS, 'active_pair': 'EURUSD', 'active_version': 1,
            'total_steps_done': 0, 'total_steps_target': 5_000_000,
            'last_checkpoint_utc': None, 'last_checkpoint_steps': 0,
            'pairs_done': [], 'pairs_pending': PAIRS.copy(), 'retrain_cycle': 1,
            'next_retrain_after_utc': None, 'updated_utc': None}

def synthetic_bars(size=2400):
    # Synthetic bars are ONLY permitted for the explicitly labeled offline smoke test.
    rng = np.random.default_rng(1947)
    close = 1.1 + np.cumsum(rng.normal(0, .00003, size))
    opened = np.r_[close[0], close[:-1]]
    data = {'epoch': 1704067200+np.arange(size)*60}
    values = {'open': opened, 'high': np.maximum(opened,close)+.00005,
              'low': np.minimum(opened,close)-.00005, 'close': close}
    for key, value in values.items():
        data['bid_'+key] = value
        data['ask_'+key] = value+.00015
    return pd.DataFrame(data)

def create_model(env, smoke=False):
    return PPO('MlpPolicy', env, learning_rate=3e-4, n_steps=100 if smoke else 2048,
               batch_size=50 if smoke else 64, n_epochs=10, gamma=.99,
               gae_lambda=.95, clip_range=.2, verbose=0 if smoke else 1, device='cpu', seed=7)

def save_state(gh, state, message):
    state['updated_utc'] = utc()
    snapshot = copy.deepcopy(state)
    def merge(current):
        # Preserve isolated smoke evidence written independently by CI.
        if 'smoke_test' in current and 'smoke_test' not in snapshot:
            snapshot['smoke_test'] = current['smoke_test']
        return snapshot
    gh.commit_json('training_state.json', merge, message+' [skip ci]')


def load_data(gh, pair):
    index = json.loads((ROOT / 'data/index.json').read_text())
    entry = index.get(pair_key(index, pair), {})
    if not entry:
        raise ValueError(pair+' history unavailable; run histdata-bulk first')
    releases = {}
    def release(tag):
        if tag not in releases:
            releases[tag] = gh.ensure_release(tag)
        return releases[tag]
    candidates = []
    for meta in entry.get('bulk_years', {}).values():
        rel = release(meta['release_tag'])
        asset = next(a for a in gh.assets(rel) if a['name'] == meta['asset'])
        candidates.append((asset, meta.get('sha256')))
    for tag in entry.get('shard_releases', []):
        for asset in gh.assets(release(tag)):
            # Accept existing EURUSD history naming as well as new annual archives.
            if re.fullmatch(r'(?:frx)?'+re.escape(pair)+r'_\d{4}(?:_60s\.[a-f0-9]+|_through_\d{2})?\.csv\.gz', asset['name'], re.IGNORECASE):
                candidates.append((asset, None))
    if entry.get('asset'):
        rel = release(entry['release_tag'])
        asset = next(a for a in gh.assets(rel) if a['name'] == entry['asset'])
        candidates.append((asset, entry.get('sha256')))
    frames, seen = [], set()
    for asset, sha in candidates:
        if asset['id'] in seen:
            continue
        seen.add(asset['id'])
        raw = gh.download(asset)
        if sha and hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('candle archive digest mismatch')
        frame = pd.read_csv(io.BytesIO(raw), compression='gzip')
        if not {'bid_open','bid_high','bid_low','bid_close','ask_close'}.issubset(frame.columns):
            raise ValueError('training requires indexed bid/ask M1 data, not OHLC-only fallback')
        frames.append(frame)
    if not frames:
        raise ValueError('no candle assets found for '+pair)
    frame = pd.concat(frames, ignore_index=True).sort_values('epoch').drop_duplicates('epoch',keep='last').reset_index(drop=True)
    # Chronological holdout is never supplied to PPO; no profitability claim without evaluation.
    split = int(len(frame)*.8)
    if split < 100:
        raise ValueError('insufficient training history')
    return frame.iloc[:split].reset_index(drop=True), frame.iloc[split:].reset_index(drop=True)


def checkpoint(gh, model, state, stats):
    pair, version, steps = state['active_pair'], state['active_version'], int(model.num_timesteps)
    cache = ROOT / 'cache/training'; cache.mkdir(parents=True, exist_ok=True)
    name = f'{pair}_v{version}_s{steps}.zip'
    path = cache / name
    rel = gh.ensure_release('training-checkpoints')
    existing = next((a for a in gh.assets(rel) if a['name'] == name), None)
    if existing:
        raw = gh.download(existing)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            meta = json.loads(archive.read('sentinel_checkpoint.json'))
        assert meta['steps'] == steps and meta['pair'] == pair and meta['version'] == version
        path.write_bytes(raw)
        state.update(total_steps_done=steps,last_checkpoint_steps=steps,last_checkpoint_utc=meta['saved_utc'],
                     checkpoint={'asset':name,'release_tag':'training-checkpoints','sha256':hashlib.sha256(raw).hexdigest()})
        save_state(gh,state,f'Q4: recover existing {pair} checkpoint {steps}')
        return path
    model.save(str(path))
    meta = {'pair':pair,'version':version,'steps':steps,'saved_utc':utc(), **stats}
    with zipfile.ZipFile(path,'a',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('sentinel_checkpoint.json', json.dumps(meta))
    raw = path.read_bytes()
    rel = gh.ensure_release('training-checkpoints')
    gh.upload(rel, name, raw)
    state.update(total_steps_done=steps, last_checkpoint_steps=steps, last_checkpoint_utc=meta['saved_utc'],
                 checkpoint={'asset': name,'release_tag':'training-checkpoints','sha256':hashlib.sha256(raw).hexdigest()},
                 plateau_intervals=stats.get('plateau_intervals',0), previous_mean_reward=stats.get('previous_mean_reward'))
    save_state(gh,state,f'Q4: verified {pair} v{version} checkpoint {steps}')
    return path


def restore(gh, env, state):
    pair, version = state['active_pair'], state['active_version']
    rel = gh.ensure_release('training-checkpoints')
    pattern = re.compile(re.escape(pair)+f'_v{version}_s(\\d+)\\.zip$')
    choices = [(int(pattern.fullmatch(a['name']).group(1)),a) for a in gh.assets(rel) if pattern.fullmatch(a['name'])]
    if not choices:
        if state.get('total_steps_done',0):
            raise RuntimeError('recorded training steps have no matching durable checkpoint; refusing silent restart')
        return create_model(env)
    steps, asset = max(choices,key=lambda item:item[0])
    raw = gh.download(asset)
    recorded = state.get('checkpoint',{})
    if recorded.get('asset') == asset['name'] and hashlib.sha256(raw).hexdigest() != recorded['sha256']:
        raise ValueError('checkpoint digest mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        meta = json.loads(archive.read('sentinel_checkpoint.json'))
    assert meta['pair']==pair and meta['version']==version and meta['steps']==steps
    path = ROOT / 'cache/training' / asset['name'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    # Only repository-owned checkpoints; never load user-supplied pickle/model archives here.
    model = PPO.load(str(path), env=env, device='cpu')
    assert model.num_timesteps == steps, 'checkpoint step mismatch'
    state.update(total_steps_done=steps,last_checkpoint_steps=steps,last_checkpoint_utc=meta['saved_utc'],
                 plateau_intervals=meta.get('plateau_intervals',0), previous_mean_reward=meta.get('previous_mean_reward'))
    return model


class TrainingWall(BaseCallback):
    def __init__(self, gh, state, deadline):
        super().__init__()
        self.gh,self.state,self.deadline = gh,state,deadline
        self.last_saved = state.get('last_checkpoint_steps',0)
        self.wall = False
        self.converged = False
        self.plateau = state.get('plateau_intervals',0)
        self.previous = state.get('previous_mean_reward')
        self.stats = {}

    def _on_step(self):
        self.wall = STOP or time.monotonic() >= self.deadline
        interval = self.num_timesteps-self.last_saved >= 50000
        target = self.num_timesteps >= self.state['total_steps_target']
        if interval or self.wall or target:
            rewards = [float(e['r']) for e in self.model.ep_info_buffer]
            mean = float(np.mean(rewards)) if rewards else None
            if interval and mean is not None and len(rewards) >= 10:
                self.plateau = self.plateau+1 if self.previous is not None and mean-self.previous < .001 else 0
                self.previous = mean
            self.stats = {'plateau_intervals':self.plateau,'previous_mean_reward':self.previous}
            checkpoint(self.gh,self.model,self.state,self.stats)
            self.last_saved = self.num_timesteps
            self.converged = target or self.plateau >= 10
        return not (self.wall or self.converged)


def publish(gh, model, env, holdout, state):
    pair,version = state['active_pair'],state['active_version']
    report = {'pair':pair,'version':version,'steps':model.num_timesteps,'created_utc':utc(),
              'trained_through':int(env.frame.iloc[-1]['epoch']), 'training_rows':len(env.frame),
              'holdout_rows':len(holdout), 'profitability_verified':False,
              'note':'PPO step target/plateau is not proof of profitability. Live deployment requires owner allocation/enabling.',
              'observation_dim':47, 'shared_engine':True,
              'cost_assumptions':{'commission_known':'commission_per_lot' in env.specs,
                                  'commission_per_lot':env.specs.get('commission_per_lot',0),
                                  'slippage_points':env.specs.get('slippage_points',0),
                                  'ask_source':'indexed historical ask, potentially synthesized; consult data/index.json'}}
    bundle,health = export_bundle(model,env,pair,version,ROOT/'cache/training/export',report)
    raw = bundle.read_bytes()
    releases = [r for r in gh.releases() if re.fullmatch(r'models-\d+',r['tag_name'])]
    rel = max(releases,key=lambda r:int(r['tag_name'].split('-')[-1])) if releases else gh.ensure_release('models-01')
    if sum(a['size'] for a in gh.assets(rel))+len(raw) > 1800*1024*1024:
        rel = gh.ensure_release('models-'+f"{int(rel['tag_name'].split('-')[-1])+1:02d}")
    existing = next((a for a in gh.assets(rel) if a['name'] == bundle.name),None)
    if existing:
        previous = gh.download(existing)
        with zipfile.ZipFile(io.BytesIO(previous)) as archive:
            previous_report = json.loads(archive.read('training_report.json'))
        if previous_report['steps'] != model.num_timesteps:
            raise ValueError('model version already published with different trained steps')
        raw = previous
    else:
        gh.upload(rel,bundle.name,raw)
    def merge(index):
        entry = index.setdefault('frx'+pair,{'active_version':None,'versions':[]})
        entry['versions'] = [v for v in entry['versions'] if v['N'] != version]
        entry['versions'].append({'N':version,'release_tag':rel['tag_name'],'asset':bundle.name,
                                  'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),
                                  'created_utc':utc(),'verdict':None,'profitability_verified':False})
        entry['active_version'] = version
        return index
    gh.commit_json('models/index.json',merge,f'Q4: publish health-checked {pair} v{version} [skip ci]')


def advance(state):
    pair = state['active_pair']
    if pair not in state['pairs_done']:
        state['pairs_done'].append(pair)
    state['pairs_pending'] = [p for p in state['queue'] if p not in state['pairs_done']]
    if not state['pairs_pending']:
        state.update(retrain_cycle=state['retrain_cycle']+1,
                     next_retrain_after_utc=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),
                     pairs_done=[],pairs_pending=state['queue'].copy(),active_pair=state['queue'][0],
                     active_version=state['active_version']+1)
    else:
        state['active_pair'] = state['pairs_pending'][0]
    state.update(total_steps_done=0,last_checkpoint_steps=0,last_checkpoint_utc=None,
                 plateau_intervals=0,previous_mean_reward=None,status='queued')
    state.pop('checkpoint',None)


def smoke_test():
    from stable_baselines3.common.env_checker import check_env
    specs = json.loads((ROOT/'data/symbols.json').read_text())['symbols']['EURUSD']
    env = SentinelScalpEnv(synthetic_bars(),specs)
    check_env(env,warn=True)
    monitored = Monitor(env)
    model = create_model(monitored,smoke=True)
    t0 = time.monotonic()
    model.learn(total_timesteps=1000)
    assert model.num_timesteps == 1000
    # Exercise save/resume AND Torch→ONNX→live evaluator→bundle checker offline.
    cache = ROOT/'cache/training/smoke'; cache.mkdir(parents=True,exist_ok=True)
    model.save(str(cache/'checkpoint'))
    loaded = PPO.load(str(cache/'checkpoint.zip'),env=monitored,device='cpu')
    assert loaded.num_timesteps == 1000
    bundle,health = export_bundle(loaded,env,'EURUSD',1,cache,{'smoke_test':True,'profitability_verified':False})
    state = json.loads(STATE.read_text()) if STATE.exists() else new_state()
    state['smoke_test'] = {'status':'passing','steps':1000,'synthetic':True,'network_uploads':False,
                           'observation_dim':47,'checkpoint_resume':'passing','onnx_bundle_check':{k:v for k,v in health.items() if k!='bundle'},
                           'updated_utc':utc(),'duration_seconds':round(time.monotonic()-t0,2)}
    state['updated_utc'] = utc()
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    print('SMOKE PASS: 1000 PPO steps, 47-float shared observation, checkpoint resume, ONNX parity and bundle checker; no uploads')


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--smoke-test',action='store_true');args = parser.parse_args()
    torch.set_num_threads(max(1,int(os.environ.get('TRAIN_CPU_THREADS','2'))))
    if args.smoke_test:
        smoke_test();return
    state = json.loads(STATE.read_text())
    token = os.environ.get("GH_CHAIN_PAT") or os.environ.get("GITHUB_TOKEN") or ""
    if str(token).strip().lower() in ("true", "false"):
        token = os.environ.get("GITHUB_TOKEN") or ""
    gh = GitHub(token)
    deadline = time.monotonic()+int(os.environ.get('TRAIN_WALL_SECONDS','17100'))
    due = state.get('next_retrain_after_utc')
    if due and datetime.fromisoformat(due)>datetime.now(timezone.utc):
        print('Next cycle is not due until',due);return
    if state['active_pair'] in state['pairs_done']:
        advance(state);save_state(gh,state,'Q4: advance completed pair')
    pair = state['active_pair']
    try:
        data,holdout = load_data(gh,pair)
        specs = json.loads((ROOT/'data/symbols.json').read_text())['symbols'][pair]
        env = SentinelScalpEnv(data,specs,pair)
        monitored = Monitor(env)
        model = restore(gh,monitored,state)
        state.update(status='training',next_retrain_after_utc=None)
        save_state(gh,state,'Q4: start/resume '+pair)
        callback = TrainingWall(gh,state,deadline)
        model.learn(total_timesteps=max(1,state['total_steps_target']-model.num_timesteps),
                    reset_num_timesteps=False,callback=callback)
        if callback.wall:
            state['status']='checkpointed';save_state(gh,state,'Q4: wall checkpoint '+pair)
            gh.dispatch('train.yml',{'mode':'resume'});return
        publish(gh,model,env,holdout,state)
        advance(state);save_state(gh,state,'Q4: completed '+pair+'; advance queue')
        if not state['next_retrain_after_utc']:
            gh.dispatch('train.yml',{'mode':'resume'})
    except Exception as exc:
        state.update(status='blocked',last_error=str(exc))
        save_state(gh,state,'Q4: record training blocker '+pair)
        raise

if __name__ == '__main__':
    def stop(signum,frame):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stop)
    main()
