"""Code/bundle health only; never claims profitability or broker execution.
Requires real embedded input vectors, schema conformance, adapter conversion
cases, parity against trainer outputs, finite outputs and a latency report.
"""
import json,time,math
import numpy as np
import pandas as pd
from .bundle import verify_bundle,load_bundle
from .plan import validate_plan,evaluate
from .policy_schema import validate_actions

def equal(actual,expected,tolerance=1e-6):
 if isinstance(expected,dict):return isinstance(actual,dict) and all(k in actual and equal(actual[k],v,tolerance) for k,v in expected.items())
 if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b,tolerance) for a,b in zip(actual,expected))
 if isinstance(expected,(int,float)) and not isinstance(expected,bool):return isinstance(actual,(int,float)) and math.isfinite(actual) and abs(actual-expected)<=tolerance
 return actual==expected

def check_bundle(path):
 report={'ok':False,'bundle':path,'problems':[],'warnings':[],'checks':{},'latency_ms':None}
 ok,problems=verify_bundle(path)
 if not ok:report['problems']=problems;return report
 try:
  b=load_bundle(path);errors=validate_plan(b.plan)
  if errors:raise ValueError('; '.join(errors))
  vectors=json.loads(b.zf.read('tests/vectors.json'));cases=vectors.get('vectors',[])
  if not cases:raise ValueError('nonempty embedded vectors required; no invented baseline')
  times=[]
  for i,case in enumerate(cases):
   if not case.get('observation') or not case.get('expected'):raise ValueError('trainer observation and expected output required')
   frame=pd.DataFrame(case.get('candles',[]));ctx={'observation':case['observation']}
   t=time.perf_counter();out=evaluate(b,frame,ctx);times.append((time.perf_counter()-t)*1000)
   if out.get('error'):raise ValueError('vector '+str(i)+' '+out['error'])
   validate_actions(out['actions'])
   if not equal(out,case['expected'],vectors.get('tolerance',1e-6)):raise ValueError('parity mismatch at vector '+str(i))
   if not equal(evaluate(b,frame,ctx),out):raise ValueError('nondeterministic output')
  report['latency_ms']=round(max(times),3)
  if report['latency_ms']>float(vectors.get('latency_ms',600)):raise ValueError('latency budget exceeded')
  conversions=json.loads(b.zf.read('tests/adapter.json'))
  if not conversions:raise ValueError('adapter conversion cases required')
  from .execution_adapter import ExecutionAdapter
  from .sim import SimulationBroker
  for i,case in enumerate(conversions):
   port=SimulationBroker(case['specs'],case['balance'],case.get('leverage',100),commission=case.get('commission',0));port.set_tick(case['tick'],case['epoch'])
   ad=ExecutionAdapter(port,'TEST','health',case['balance'],case['free_margin'],case['volatility'],case.get('overrides'))
   result=ad.execute(case['action'],'health')
   if not equal(result,case['expected']):raise ValueError('adapter parity mismatch at case '+str(i))
   if result['status'] in ('filled','partial') and case['action']['type']=='open':
    if any(p['sl']<=0 or p['volume']<case['specs']['volume_min'] for p in port.get_open_positions()):raise ValueError('invalid size/server stop')
  report['checks']={k:True for k in ['archive_integrity','safe_data_formats','analysis_plan_dag','embedded_vectors_execution','contract_conformance','output_parity','adapter_conversions']};report['ok']=True
 except Exception as error:report['problems'].append(str(error))
 return report

def main(argv=None):
 import argparse,sys
 ap=argparse.ArgumentParser();ap.add_argument('bundle');ap.add_argument('--json',action='store_true');a=ap.parse_args(argv)
 result=check_bundle(a.bundle);print(json.dumps(result,indent=2));sys.exit(0 if result['ok'] else 1)
if __name__=='__main__':main()
