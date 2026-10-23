"""Consume explicit owner requests only when the current authorized queue ends.
No schedule can invent a new cycle. A queued update never replaces active weights.
"""
import base64
import copy
import io
import json
import hashlib
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from tools.release_utils import ROOT, pair_key

ACTIVE = {'training', 'checkpointed', 'resuming', 'queued'}

def read_remote(gh, path, default=None):
    r=gh.session.get(gh.base+'/contents/'+path,params={'ref':'main'},timeout=30)
    if r.status_code==404:return copy.deepcopy(default)
    r.raise_for_status()
    return json.loads(base64.b64decode(r.json()['content']))


def model_source(index, pair):
    entry=index.get('frx'+pair,index.get(pair,{}))
    active=entry.get('active_version')
    return next((v for v in entry.get('versions',[]) if v.get('N')==active
                 and v.get('verdict')=='pass' and v.get('profitability_verified')
                 and v.get('observation_dim')==62),None)


def prepare_owner_cycle(gh, state):
    """Return True only for an existing authorized cycle or a consumed request."""
    if state.get('paused'):
        print('Training paused by owner; no start/resume');return False
    # Migration: the already-running original owner-started queue is authorized.
    if state.get('status') in ACTIVE and (state.get('owner_started') or state.get('checkpoint')):
        state['owner_started']=True
        return True
    requests=read_remote(gh,'training_requests.json',{'requests':[]})
    pending=[r for r in requests.get('requests',[]) if r.get('status')=='queued']
    if not pending:
        print('No queued owner request; no automatic training cycle');return False
    req=pending[0]
    pairs=req['pairs']
    index=read_remote(gh,'models/index.json',{})
    sources={p:model_source(index,p) for p in pairs} if req['action']=='update' else {}
    if req['action']=='update' and any(v is None for v in sources.values()):
        raise ValueError('update requires an existing proven 62-input released model for every requested pair')
    # Claim is safe under train.yml single-writer; retain status for audit/idempotency.
    def claim(doc):
        row=next(r for r in doc.get('requests',[]) if r['id']==req['id'])
        row.update(status='consumed',consumed_utc=datetime.now(timezone.utc).isoformat())
        return doc
    # Persist cycle identity BEFORE consumption so a crash cannot lose a request.
    preserved={k:state[k] for k in ('smoke_test','pair_results') if k in state}
    state.clear();state.update(preserved)
    state.update(queue=pairs,active_pair=pairs[0],active_version=1,pairs_done=[],pairs_pending=pairs,
                 total_steps_done=0,last_checkpoint_steps=0,last_checkpoint_utc=None,total_steps_target=5000000,
                 status='queued',owner_started=True,paused=False,request_id=req['id'],
                 request_action=req['action'],warm_start_sources=sources,next_retrain_after_utc=None)
    select_pair_version(state,index)
    # Caller immediately commits state before training; request is only consumed after that commit.
    state['_pending_request_claim']=req['id']
    return True


def finish_request_claim(gh,state):
    request_id=state.pop('_pending_request_claim',None)
    if not request_id:return
    def claim(doc):
        for row in doc.get('requests',[]):
            if row['id']==request_id:row.update(status='consumed',consumed_utc=datetime.now(timezone.utc).isoformat())
        return doc
    gh.commit_json('training_requests.json',claim,'fix5: claim owner training request [skip ci]')


def select_pair_version(state,index):
    pair=state['active_pair'];entry=index.get('frx'+pair,index.get(pair,{}))
    versions=[int(v['N']) for v in entry.get('versions',[])]
    state['active_version']=max(versions,default=0)+1


def warm_start(gh,env,state):
    """Restore native training weights, never ONNX and never reset to random weights."""
    source=state.get('warm_start_sources',{}).get(state['active_pair'])
    if not source:return None
    tag=source.get('checkpoint_release_tag','training-checkpoints')
    asset_name=source.get('checkpoint_asset')
    if not asset_name:raise ValueError('released model lacks native checkpoint provenance; update cannot silently restart')
    rel=gh.ensure_release(tag);asset=next((a for a in gh.assets(rel) if a['name']==asset_name),None)
    if asset is None:raise ValueError('released native checkpoint unavailable')
    raw=gh.download(asset)
    if source.get('checkpoint_sha256') and hashlib.sha256(raw).hexdigest()!=source['checkpoint_sha256']:
        raise ValueError('warm-start checkpoint digest mismatch')
    path=ROOT/'cache/training'/('warm_'+asset_name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    from stable_baselines3 import PPO
    model=PPO.load(str(path),env=env,device='cpu')
    if model.observation_space.shape!=(62,):raise ValueError('warm-start requires current62-input observation')
    state['warm_started_from']={'version':source['N'],'asset':asset_name,'source_steps':model.num_timesteps}
    # New version trains another FULL5M optimizer steps, retaining the previous policy weights.
    model.num_timesteps=0
    print('WARM START new version from verified native checkpoint',asset_name,flush=True)
    return model
