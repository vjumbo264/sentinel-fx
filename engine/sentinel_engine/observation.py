"""Shared causal observation and deterministic vectorization, training == live.
Input rows are COMPLETED M1 bars. Epoch is bar-open UTC; asof is bar close.
"""
import math
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from .policy_schema import Observation,VERSION
TIMEFRAMES={'M1':60,'M5':300,'M15':900,'H1':3600}

def causal_market(df):
 df=df.copy()
 if 'epoch' not in df:df['epoch']=df['time']
 df=df.sort_values('epoch').drop_duplicates('epoch');asof=int(df.iloc[-1]['epoch'])+60
 markets={};volatility=None
 for name,seconds in TIMEFRAMES.items():
  base=df.assign(bucket=(df.epoch.astype('int64')//seconds)*seconds)
  agg=base.groupby('bucket').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),count=('epoch','count'))
  # A bucket is usable only after its close and with all component bars.
  agg=agg[(agg.index+seconds<=asof)&(agg['count']==seconds//60)]
  if len(agg)<20:markets[name]={'available':False};continue
  close=agg.close;prev=close.shift(1)
  tr=pd.concat([agg.high-agg.low,(agg.high-prev).abs(),(agg.low-prev).abs()],axis=1).max(axis=1)
  atr=float(tr.tail(14).mean())
  if atr<=0 or not math.isfinite(atr):raise ValueError('invalid volatility')
  if name=='M1':volatility=atr
  last=agg.iloc[-1];ema=float(close.ewm(span=20,adjust=False).mean().iloc[-1])
  markets[name]={'available':True,'return_1':float((close.iloc[-1]-close.iloc[-2])/atr),'return_5':float((close.iloc[-1]-close.iloc[-6])/atr),'trend':float((last.close-ema)/atr),'range':float((last.high-last.low)/atr),'level_low':float((last.close-agg.low.tail(20).min())/atr),'level_high':float((agg.high.tail(20).max()-last.close)/atr),'volatility_ratio':float(atr/last.close)}
 if volatility is None:raise ValueError('M1 warmup needs 20 completed bars')
 return markets,volatility,asof

def build_observation(df,equity,pool_share,positions,specs,tick,drawdown=0,news_events=None,last_result=None,recent=None):
 market,atr,asof=causal_market(df);dt=datetime.fromtimestamp(asof,timezone.utc)
 equity=max(float(equity),1e-9);csize=float(specs['contract_size']);normalized=[]
 for p in positions:
  side=p.get('type') or p.get('side');direction=1 if side in ('BUY','long') else -1
  entry=p['price_open'];risk=max(abs(entry-p['sl'])*p['volume']*csize,1e-9)
  current=tick['bid'] if direction==1 else tick['ask']
  normalized.append({'position_ref':str(p['ticket']),'direction':direction,'size_fraction':p['volume']*csize*current/equity,'entry_distance':direction*(current-entry)/atr,'profit_risk_units':float(p.get('profit',0))/risk,'time_open_minutes':max(0,(asof-p['time'])/60),'stop_distance':direction*(current-p['sl'])/atr,'target_distance':direction*(p.get('tp',0)-current)/atr if p.get('tp') else None})
 # Only archived events with a recorded_at <= asof may contribute outcomes.
 upcoming=[];recent_events=[]
 for event in news_events or []:
  known=int(event.get('known_epoch',event.get('recorded_epoch',asof+1)))
  if known>asof:continue
  event_time=int(event['epoch']);safe={k:event[k] for k in ('currency','impact','title','forecast','previous') if k in event}
  safe['minutes']=(event_time-asof)/60
  if event_time>asof:upcoming.append(safe)
  elif asof-event_time<=86400:
   safe.update({k:event[k] for k in ('reaction_5m','reaction_15m') if k in event and int(event.get(k+'_known_epoch',asof+1))<=asof});recent_events.append(safe)
 obs=Observation(market=market,costs={'spread_atr':(tick['ask']-tick['bid'])/atr,'swap_long':specs.get('swap_long'),'swap_short':specs.get('swap_short'),'commission':specs.get('commission_per_lot'),'commission_known':'commission_per_lot' in specs},session={'epoch':asof,'hour_sin':math.sin(dt.hour/24*2*math.pi),'hour_cos':math.cos(dt.hour/24*2*math.pi),'weekday':dt.weekday(),'london':7<=dt.hour<16,'new_york':12<=dt.hour<21},news={'coverage':bool(news_events),'upcoming':upcoming,'recent':recent_events},equity=equity,drawdown=float(drawdown),pool_share=float(pool_share),positions=normalized,recent_results=recent or [],last_action_result=last_result)
 return obs,atr

def vectorize(obs):
 d=obs.to_dict() if hasattr(obs,'to_dict') else obs
 if d.get('schema_version')!=VERSION:raise ValueError('unsupported observation schema')
 values=[]
 for name in TIMEFRAMES:
  m=d['market'].get(name,{})
  values+=[float(bool(m.get('available')))]
  values+=[float(m.get(k,0)) for k in ['return_1','return_5','trend','range','level_low','level_high','volatility_ratio']]
 ps=d['positions'];minutes=[e['minutes'] for e in d['news'].get('upcoming',[])];last=d.get('last_action_result') or {}
 values += [float(d['costs'].get('spread_atr',0)),float(d['costs'].get('commission_known',False)),d['drawdown'],d['equity']/max(d['pool_share'],1e-9),d['session']['hour_sin'],d['session']['hour_cos'],d['session']['weekday']/6,len(ps),sum(p['direction']*p['size_fraction'] for p in ps),sum(p['profit_risk_units'] for p in ps),max([p['time_open_minutes'] for p in ps] or [0])/1440,float(d['news'].get('coverage',False)),min(minutes or [1440])/1440,float(last.get('status')=='rejected'),sum(d.get('recent_results',[])[-10:])]
 x=np.array(values,dtype=np.float64)
 if not np.isfinite(x).all():raise ValueError('nonfinite Observation vector')
 return x
