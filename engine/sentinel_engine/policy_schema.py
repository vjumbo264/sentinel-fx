"""Versioned DATA-only policy interface; no broker prices, lots or MT5 API.
The adapter owns price/volume conversion; learned policies receive normalized data.
"""
from dataclasses import dataclass,field,asdict
from typing import Any
import math
VERSION='sentinel.policy.v2'
ACTION_TYPES={'hold','open','add','reduce','reverse','move_stop','close'}
REJECTION_TYPES={'margin','broker_limit','market_closed','owner_override','invalid'}
@dataclass
class ActionResult:
 status:str
 reason:str=''
 price:float|None=None
 size:float|None=None
 clamped:dict=field(default_factory=dict)
 tickets:list=field(default_factory=list)
 def to_dict(self):return asdict(self)
@dataclass
class Observation:
 schema_version:str=VERSION
 market:dict=field(default_factory=dict)
 costs:dict=field(default_factory=dict)
 session:dict=field(default_factory=dict)
 news:dict=field(default_factory=dict)
 equity:float=0.0
 drawdown:float=0.0
 pool_share:float=0.0
 positions:list=field(default_factory=list)
 recent_results:list=field(default_factory=list)
 last_action_result:dict|None=None
 session_dist_high:float=0.0
 session_dist_low:float=0.0
 spread_spike:float=0.0
 def to_dict(self):return asdict(self)
@dataclass
class Action:
 type:str
 reason:str
 side:str|None=None
 risk_fraction:float|None=None
 stop_distance:float|None=None
 targets:list=field(default_factory=list)
 position_ref:str|None=None
 fraction:float|None=None
 new_stop_distance:float|None=None
 to_breakeven:bool=False
 trail:float|None=None
 def to_dict(self):return {k:v for k,v in asdict(self).items() if v is not None and v is not False and v!=[]}

def finite_number(value,name):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(name+' must be finite numeric')
 return float(value)

def validate_action(a):
 if not isinstance(a,dict):raise ValueError('action must be a mapping')
 allowed=set(Action.__dataclass_fields__)
 if set(a)-allowed:raise ValueError('unknown action fields: '+str(set(a)-allowed))
 kind=a.get('type')
 if kind not in ACTION_TYPES:raise ValueError('invalid action type')
 if not isinstance(a.get('reason'),str) or not 0<len(a['reason'])<=500:raise ValueError('short reason required')
 if kind in ('open','add'):
  risk=finite_number(a.get('risk_fraction'),'risk_fraction')
  if not 0<risk<=1:raise ValueError('risk_fraction must be in (0,1]')
 if kind=='open':
  if a.get('side') not in ('long','short'):raise ValueError('open side must be long or short')
  if a.get('stop_distance') is not None and finite_number(a['stop_distance'],'stop_distance')<=0:raise ValueError('stop_distance must be positive')
  total=0
  for target in a.get('targets',[]):
   if set(target)!={'distance','fraction'}:raise ValueError('target requires distance and fraction only')
   if finite_number(target['distance'],'target distance')<=0:raise ValueError('positive target distance required')
   f=finite_number(target['fraction'],'target fraction')
   if not 0<f<=1:raise ValueError('target fraction out of bounds')
   total+=f
  if total>1+1e-9:raise ValueError('target fractions exceed one')
 if kind in ('add','reduce','reverse','move_stop','close') and not str(a.get('position_ref') or ''):raise ValueError('position_ref required')
 if kind=='reduce' and not 0<finite_number(a.get('fraction'),'fraction')<=1:raise ValueError('reduce fraction out of bounds')
 if kind=='move_stop':
  options=[a.get('new_stop_distance') is not None,bool(a.get('to_breakeven')),a.get('trail') is not None]
  if sum(options)!=1:raise ValueError('exactly one stop move mode required')
  for key in ('new_stop_distance','trail'):
   if a.get(key) is not None and finite_number(a[key],key)<=0:raise ValueError(key+' must be positive')
 return a

def validate_actions(actions):
 if not isinstance(actions,list):raise ValueError('actions must be a list')
 for action in actions:validate_action(action)
 return actions
