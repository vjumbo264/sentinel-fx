"""Shared causal observation and deterministic vectorization, training == live.
Input rows are COMPLETED M1 bars. Epoch is bar-open UTC; asof is bar close.
"""
import math
from datetime import datetime,timezone
try:
 import numpy as np
 import pandas as pd
except ImportError:
 np = None
 pd = None
from .policy_schema import Observation,VERSION,OBSERVATION_DIM
TIMEFRAMES={'M1':60,'M5':300,'M15':900,'H1':3600}

def causal_market(df):
 df=df.copy()
 if 'epoch' not in df and 'time' in df:df['epoch']=df['time']
 for field in ('open','high','low','close'):
  if field not in df and 'bid_'+field in df:df[field]=df['bid_'+field]
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
  if atr<=0 or not math.isfinite(atr):atr=max(1e-5,float(close.iloc[-1]*1e-5) if len(close) and close.iloc[-1]>0 else 1e-5)
  if name=='M1':volatility=atr
  last=agg.iloc[-1];ema=float(close.ewm(span=20,adjust=False).mean().iloc[-1])
  m={'available':True,'return_1':float((close.iloc[-1]-close.iloc[-2])/atr),'return_5':float((close.iloc[-1]-close.iloc[-6])/atr),'trend':float((last.close-ema)/atr),'range':float((last.high-last.low)/atr),'level_low':float((last.close-agg.low.tail(20).min())/atr),'level_high':float((agg.high.tail(20).max()-last.close)/atr),'volatility_ratio':float(atr/last.close)}
  if name in ('M1','H1'):
   delta=close.diff()
   gain=delta.clip(lower=0).ewm(com=13,adjust=False).mean()
   loss=(-delta.clip(upper=0)).ewm(com=13,adjust=False).mean()
   rs=gain/loss.replace(0,1e-9)
   rsi=100-(100/(1+rs))
   rsi_val=float(rsi.iloc[-1]) if len(rsi) and math.isfinite(rsi.iloc[-1]) else 50.0
   m['rsi']=float((rsi_val-50)/50)
   sma20=close.rolling(20).mean()
   std20=close.rolling(20).std().replace(0,1e-9)
   upper=sma20+2*std20
   lower=sma20-2*std20
   band_width=(upper-lower).replace(0,1e-9)
   bb_pos=(close-lower)/band_width
   bb_val=float(bb_pos.iloc[-1]) if len(bb_pos) and math.isfinite(bb_pos.iloc[-1]) else 0.5
   m['bb_position']=float(np.clip(bb_val,0,1)*2-1)
   ema9=close.ewm(span=9,adjust=False).mean()
   ema21=close.ewm(span=21,adjust=False).mean()
   m['ema_cross']=float((ema9.iloc[-1]-ema21.iloc[-1])/atr)
  if name=='M1':
   current_width=float((upper-lower).iloc[-1])
   hist_width=(upper-lower).tail(100)
   m['bb_squeeze']=1.0 if current_width<float(hist_width.quantile(0.2)) else 0.0
   atr_series=tr.ewm(span=14,adjust=False).mean()
   atr_20_mean=float(atr_series.tail(20).mean())
   m['atr_regime']=1.0 if atr>atr_20_mean else 0.0
   m['volatility_percentile']=float((atr_series<atr).tail(100).mean())
   body=abs(last.close-last.open)
   wick=last.high-last.low
   body_ratio=float(body/max(wick,atr*0.01))
   m['body_direction']=float(np.sign(last.close-last.open))*body_ratio
   price_high_5=bool(close.tail(5).max()==close.iloc[-1])
   rsi_high_5=bool(rsi.tail(5).max()==rsi.iloc[-1])
   price_low_5=bool(close.tail(5).min()==close.iloc[-1])
   rsi_low_5=bool(rsi.tail(5).min()==rsi.iloc[-1])
   div=0.0
   if price_high_5 and not rsi_high_5:div=-1.0
   elif price_low_5 and not rsi_low_5:div=1.0
   m['rsi_divergence']=div
   directions=np.sign(close.diff().tail(5))
   consecutive=0
   last_dir=directions.iloc[-1]
   for d in reversed(directions.values):
    if d==last_dir and d!=0:consecutive+=1
    else:break
   m['consecutive_bars']=float(consecutive*last_dir)/5.0
  markets[name]=m
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
 upcoming=[];recent_events=[]
 for event in news_events or []:
  known=int(event.get('known_epoch',event.get('recorded_epoch',asof+1)))
  if known>asof:continue
  event_time=int(event['epoch']);safe={k:event[k] for k in ('currency','impact','title','forecast','previous') if k in event}
  safe['minutes']=(event_time-asof)/60
  if event_time>asof:upcoming.append(safe)
  elif asof-event_time<=86400:
   safe.update({k:event[k] for k in ('reaction_5m','reaction_15m') if k in event and int(event.get(k+'_known_epoch',asof+1))<=asof});recent_events.append(safe)
 session_bars=df[df['epoch']>=(asof-8*3600)]
 if len(session_bars)==0:session_bars=df.tail(1)
 s_high=session_bars['high'] if 'high' in session_bars else session_bars['bid_high']
 s_low=session_bars['low'] if 'low' in session_bars else session_bars['bid_low']
 l_close=df.iloc[-1]['close'] if 'close' in df else df.iloc[-1]['bid_close']
 session_high=float(s_high.max())
 session_low=float(s_low.min())
 last_close=float(l_close)
 dist_from_high=float((session_high-last_close)/atr)
 dist_from_low=float((last_close-session_low)/atr)
 current_spread=float(tick['ask']-tick['bid'])
 typical_spread=float(specs.get('typical_spread_pts',1.5)*specs.get('point',0.00001))
 spread_spike=1.0 if current_spread>2.5*typical_spread else 0.0
 obs=Observation(market=market,costs={'spread_atr':(tick['ask']-tick['bid'])/atr,'swap_long':specs.get('swap_long'),'swap_short':specs.get('swap_short'),'commission':specs.get('commission_per_lot'),'commission_known':'commission_per_lot' in specs},session={'epoch':asof,'hour_sin':math.sin(dt.hour/24*2*math.pi),'hour_cos':math.cos(dt.hour/24*2*math.pi),'weekday':dt.weekday(),'london':7<=dt.hour<16,'new_york':12<=dt.hour<21},news={'coverage':bool(news_events),'upcoming':upcoming,'recent':recent_events},equity=equity,drawdown=float(drawdown),pool_share=float(pool_share),positions=normalized,recent_results=recent or [],last_action_result=last_result,session_dist_high=dist_from_high,session_dist_low=dist_from_low,spread_spike=spread_spike)
 return obs,atr

def vectorize(obs):
 d=obs.to_dict() if hasattr(obs,'to_dict') else obs
 if d.get('schema_version')!=VERSION:raise ValueError('unsupported observation schema')
 values=[]
 for name in TIMEFRAMES:
  m=d['market'].get(name,{})
  values+=[float(bool(m.get('available')))]
  values+=[float(m.get(k,0)) for k in ['return_1','return_5','trend','range','level_low','level_high','volatility_ratio']]
  if name in ('M1','H1'):
   values+=[float(m.get(k,0)) for k in ['rsi','bb_position','ema_cross']]
  if name=='M1':
   values+=[float(m.get(k,0)) for k in ['bb_squeeze','atr_regime','volatility_percentile','body_direction','rsi_divergence','consecutive_bars']]
 ps=d['positions'];minutes=[e['minutes'] for e in d['news'].get('upcoming',[])];last=d.get('last_action_result') or {}
 values += [float(d['costs'].get('spread_atr',0)),float(d['costs'].get('commission_known',False)),d['drawdown'],d['equity']/max(d['pool_share'],1e-9),d['session']['hour_sin'],d['session']['hour_cos'],d['session']['weekday']/6,len(ps),sum(p['direction']*p['size_fraction'] for p in ps),sum(p['profit_risk_units'] for p in ps),max([p['time_open_minutes'] for p in ps] or [0])/1440,float(d['news'].get('coverage',False)),min(minutes or [1440])/1440,float(last.get('status')=='rejected'),sum(d.get('recent_results',[])[-10:]),float(d.get('session_dist_high',0.0)),float(d.get('session_dist_low',0.0)),float(d.get('spread_spike',0.0))]
 x=np.array(values,dtype=np.float64)
 if x.shape!=(OBSERVATION_DIM,):raise ValueError(f'observation size mismatch: expected {OBSERVATION_DIM}, got {x.size}; retired models must not be loaded')
 if not np.isfinite(x).all():raise ValueError('nonfinite Observation vector')
 return x
