"""Causal data-only graph evaluator. Terminal policy is a REAL learned model.
A classifier/score vector selects an action list from a declarative catalogue.
Catalogue distances/risk units are normalized, never broker prices or lots.
ONNX or LightGBM support multi-output action scores. No constant policy nodes.
"""
import time,copy
try:
 import numpy as np
except ImportError:
 np = None
from .policy_schema import VERSION,validate_actions
from .observation import vectorize
ALLOWED_TYPES={'feature_group','analyst','router','head','calibrator','policy','news'}
class PlanError(ValueError):pass

def _check_acyclic(nodes):
 order=[];seen=set()
 def visit(nid,stack):
  if nid in stack:raise PlanError('cycle at '+nid)
  if nid not in nodes:raise PlanError('unknown dependency '+nid)
  if nid in seen:return
  for dep in nodes[nid].get('inputs',[]):visit(dep,stack|{nid})
  seen.add(nid);order.append(nid)
 for nid in nodes:visit(nid,set())
 return order

def validate_plan(plan):
 errors=[];listed=plan.get('nodes',[])
 if not isinstance(listed,list) or not listed:return ['empty plan']
 nodes={n.get('id'):n for n in listed}
 if len(nodes)!=len(listed):errors.append('duplicate node IDs')
 if len(nodes)>64:errors.append('plan has more than 64 nodes')
 for nid,n in nodes.items():
  if not isinstance(nid,str) or n.get('type') not in ALLOWED_TYPES:errors.append('invalid node '+str(nid))
  if n.get('type') in ('analyst','head','policy') and not n.get('model'):errors.append(str(nid)+': learned model required')
  if n.get('type')=='policy':
   if n.get('schema_version')!=VERSION:errors.append(str(nid)+': policy schema version required')
   if not n.get('action_catalog'):errors.append(str(nid)+': action catalogue required')
 if sum(n.get('type')=='policy' for n in listed)!=1:errors.append('exactly one terminal learned policy required')
 try:_check_acyclic(nodes)
 except Exception as e:errors.append(str(e))
 return errors

def predict_model(model,x):
 if hasattr(model,'predict'):out=model.predict(np.asarray([x],dtype=np.float64))
 else:
  inp=model.get_inputs()[0];dtype=np.float32 if 'float' in inp.type and 'double' not in inp.type else np.float64
  out=model.run(None,{inp.name:np.asarray([x],dtype=dtype)})[0]
 out=np.asarray(out,dtype=float).reshape(-1)
 if not np.isfinite(out).all():raise PlanError('NaN or infinite learned output')
 return out

def evaluate(bundle,df,ctx=None,latency_ms=600):
 ctx=ctx or {};t0=time.monotonic();result={'schema_version':VERSION,'actions':[],'reason':'','opinions':[],'error':None}
 try:
  errors=validate_plan(bundle.plan)
  if errors:raise PlanError('; '.join(errors))
  obs=ctx.get('observation')
  if obs is None:raise PlanError('Observation required; no broker/default context fallback')
  data=obs.to_dict() if hasattr(obs,'to_dict') else obs
  nodes={n['id']:n for n in bundle.plan['nodes']};values={};opinions=[]
  for nid in _check_acyclic(nodes):
   if (time.monotonic()-t0)*1000>latency_ms:raise PlanError('latency budget exceeded')
   node=nodes[nid];kind=node['type']
   if kind=='feature_group':
    from .dsl import compute_features
    values[nid]=compute_features(node.get('dsl',[]),df)
   elif kind=='router':
    chosen=node.get('default',[])
    for rule in node.get('table',[]):
     if all(ctx.get(k)==v for k,v in rule.get('when',{}).items()):chosen=rule.get('use',chosen);break
    values[nid]=chosen
   elif kind in ('analyst','head'):
    x=[]
    for dep in node.get('inputs',[]):
     value=values[dep]
     if hasattr(value,'iloc'):x.extend(value[node.get('features') or list(value.columns)].iloc[-1].to_numpy(dtype=float).tolist())
     else:x.extend(np.asarray(value,dtype=float).reshape(-1).tolist())
    if not x:x=vectorize(obs).tolist()
    if not np.isfinite(x).all():raise PlanError('nonfinite analyst features')
    values[nid]=predict_model(bundle.model(node['model']),x);opinions.append({'id':nid,'scores':values[nid].tolist()})
   elif kind=='calibrator':
    raw=float(values[node['inputs'][0]][0]);values[nid]=np.asarray([next((v for lo,hi,v in node.get('table',[]) if lo<=raw<hi),raw)])
   elif kind=='news':values[nid]=data['news']
   elif kind=='policy':
    x=vectorize(obs).tolist()
    for dep in node.get('inputs',[]):
     if isinstance(values[dep],np.ndarray):x.extend(values[dep].reshape(-1).tolist())
    scores=predict_model(bundle.model(node['model']),x);catalog=node['action_catalog']
    if len(scores)!=len(catalog):raise PlanError('model output dimension differs from action catalogue')
    chosen=int(np.argmax(scores));actions=copy.deepcopy(catalog[chosen])
    for action in actions:
     if action.get('position_ref')=='oldest':
      ps=data['positions']
      if not ps:action.clear();action.update(type='hold',reason='Management intent has no owned position')
      else:action['position_ref']=max(ps,key=lambda p:p['time_open_minutes'])['position_ref']
    validate_actions(actions);result.update(actions=actions,reason='; '.join(a['reason'] for a in actions),opinions=opinions,scores=scores.tolist())
  return result
 except Exception as error:
  result.update(actions=[],reason='Fail closed: '+str(error),error=type(error).__name__+': '+str(error));return result
