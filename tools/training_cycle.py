"""Direct owner start/update inputs; no request queue and no automatic new cycles."""
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from tools.release_utils import ROOT, pair_key


def read_json(gh, path):
    blob=gh.request('GET','/contents/'+path+'?ref=main').json()
    return json.loads(base64.b64decode(blob['content']))


def source_version(entry):
    versions=[v for v in entry.get('versions',[]) if v.get('observation_dim')==62
              and v.get('policy_schema')=='sentinel.policy.v2' and v.get('checkpoint_asset')]
    active=entry.get('active_version')
    return next((v for v in versions if v['N']==active),max(versions,key=lambda v:v['N'],default=None))


def prepare(gh,state,mode,pairs):
    if mode=='resume':return bool(state.get('pairs_pending')) and state.get('status')!='idle'
    if mode not in ('start','update'):raise ValueError('mode must be start, update or resume')
    if state.get('pairs_pending') and state.get('status') not in ('idle','complete','cancelled'):
        raise ValueError('Owner cycle is already active; preserve its checkpoint and wait until it completes')
    index=read_json(gh,'models/index.json')
    if pairs=='all':
        pairs=','.join(k.removeprefix('frx') for k,e in index.items() if source_version(e))
    selected=list(dict.fromkeys(p.strip().removeprefix('frx') for p in pairs.split(',') if p.strip()))
    if not selected or any(not re.fullmatch(r'(?:[A-Z]{6}|R_\d+|1HZ\d+V)',p) for p in selected):
        raise ValueError('Select at least one valid pair; Update all needs existing native 62-input models')
    sources={}
    if mode=='update':
        for p in selected:
            source=source_version(index.get('frx'+p,index.get(p,{})))
            if not source:raise ValueError(p+' has no compatible native weights to update; train it first')
            sources[p]=source
    results=state.get('pair_results',{})
    smoke=state.get('smoke_test')
    state.clear()
    state.update(queue=selected,active_pair=selected[0],pairs_done=[],pairs_pending=selected.copy(),
                 active_version=1,total_steps_done=0,total_steps_target=5000000,
                 last_checkpoint_steps=0,last_checkpoint_utc=None,status='queued',
                 owner_started=True,cycle_mode=mode,warm_start_sources=sources,
                 next_retrain_after_utc=None,pair_results=results)
    if smoke:state['smoke_test']=smoke
    # Include unreleased versions too, so a rejected checkpoint is never overwritten.
    assets=gh.assets(gh.ensure_release('training-checkpoints'))
    versions={}
    for p in selected:
        nums=[int(v['N']) for v in index.get('frx'+p,index.get(p,{})).get('versions',[])]
        nums += [int(m.group(1)) for a in assets if (m:=re.fullmatch(re.escape(p)+r'_v(\d+)_s\d+\.zip',a['name']))]
        versions[p]=max(nums,default=0)+1
    state['cycle_versions']=versions
    state['active_version']=versions[selected[0]]
    return True


def freeze_data(gh,state):
    """Pin the actual pool index entry once per pair version, including append assets."""
    pair=state['active_pair']
    if not state.get('data_snapshot'):
        index=read_json(gh,'data/index.json')
        state['data_snapshot']=index[pair_key(index,pair)]
        state['cycle_started_utc']=datetime.now(timezone.utc).isoformat()
    return state['data_snapshot']


def warm_start(gh,env,state):
    source=state.get('warm_start_sources',{}).get(state['active_pair'])
    if source is None:return None
    rel=gh.ensure_release(source.get('checkpoint_release_tag','training-checkpoints'))
    asset=next(a for a in gh.assets(rel) if a['name']==source['checkpoint_asset'])
    raw=gh.download(asset)
    if hashlib.sha256(raw).hexdigest()!=source['checkpoint_sha256']:
        raise ValueError('Native weights digest mismatch; refusing random-weight fallback')
    path=ROOT/'cache/training'/('warm_'+asset['name']);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    from stable_baselines3 import PPO
    model=PPO.load(str(path),env=env,device='cpu')
    if model.observation_space.shape!=(62,):raise ValueError('Update requires 62-dimensional weights')
    state['warm_started_from']={'version':source['N'],'asset':asset['name'],'source_steps':model.num_timesteps}
    model.num_timesteps=0
    return model
