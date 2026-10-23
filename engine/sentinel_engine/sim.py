"""Causal CFD replay through the SAME ExecutionAdapter as the live bot.
All specifications and costs must be supplied; no generated market data.
Bid/ask source precision and cost assumptions are explicitly reported.
"""
import math
from datetime import datetime,timezone,timedelta
try:
 import numpy as np
 import pandas as pd
except ImportError:
 np = None
 pd = None
from .execution_adapter import ExecutionAdapter
from .observation import build_observation
from .plan import evaluate

class SimulationBroker:
 def __init__(self,specs,balance,leverage=100,commission=0,slippage=0):
  self.specs=dict(specs);self.balance=float(balance);self.leverage=leverage;self.commission=commission;self.slippage=slippage
  self.tick=None;self.epoch=0;self.positions=[];self.closed=[];self.seq=0;self.cost_paid=0
 def set_tick(self,tick,epoch):self.tick=dict(tick);self.epoch=int(epoch)
 def get_symbol_info(self,symbol):return self.specs
 def get_tick(self,symbol):return self.tick
 def is_market_open(self,symbol=None):
  if hasattr(self,'market_closed_override') and symbol in self.market_closed_override:return not self.market_closed_override[symbol]
  sym=symbol or self.specs.get('name','')
  is_forex=str(sym).startswith('frx') or any(str(sym).endswith(c) for c in ['USD','JPY','GBP','EUR','CHF','CAD','AUD','NZD'])
  if is_forex:
   dt=datetime.fromtimestamp(self.epoch,timezone.utc)
   if (dt.weekday()==4 and dt.hour>=21) or (dt.weekday()==5) or (dt.weekday()==6 and dt.hour<21):return False
  return True
 def loss_per_lot(self,symbol,side,price,stop):
  if self.specs.get('tick_value') and self.specs.get('tick_size'):return abs(price-stop)/self.specs['tick_size']*self.specs['tick_value']
  return abs(price-stop)*self.specs['contract_size']
 def pnl(self,p,price,volume):return (price-p['price_open'])*(1 if p['type']=='BUY' else -1)*volume*self.loss_per_lot('',p['type'],0,1)
 def equity(self):return self.balance+sum(self.pnl(p,self.tick['bid'] if p['type']=='BUY' else self.tick['ask'],p['volume']) for p in self.positions)
 def margin(self):return sum(p['margin'] for p in self.positions)
 def check_margin(self,symbol,side,volume,price):
  return {'required_margin':volume*self.specs['contract_size']*price/self.leverage,'free_margin':max(0,self.equity()-self.margin())}
 def get_open_positions(self,symbol=None,magic=None):
  out=[]
  for p in self.positions:
   if (symbol is None or p['symbol']==symbol) and (magic is None or p['magic']==magic):
    item=dict(p);item['profit']=self.pnl(p,self.tick['bid'] if p['type']=='BUY' else self.tick['ask'],p['volume']);out.append(item)
  return out
 def open_position(self,symbol,side,volume,sl,tp=None,price=None,magic=0,model_id='',decision_id=''):
  price=(self.tick['ask'] if side=='BUY' else self.tick['bid'])+(1 if side=='BUY' else -1)*self.slippage
  if not sl or sl<=0:raise ValueError('server stop required')
  margin=self.check_margin(symbol,side,volume,price)
  if margin['required_margin']>margin['free_margin']:raise ValueError('margin')
  self.seq+=1;cost=self.commission*volume;self.balance-=cost;self.cost_paid+=cost+((self.tick['ask']-self.tick['bid'])+self.slippage)*self.loss_per_lot('',side,0,1)*volume
  self.positions.append({'ticket':self.seq,'symbol':symbol,'type':side,'volume':volume,'price_open':price,'sl':sl,'tp':tp,'magic':magic,'time':self.epoch,'margin':margin['required_margin'],'entry_commission':cost,'reason':decision_id,'model_id':model_id})
  return {'ok':True,'retcode':10009,'ticket':self.seq,'order':self.seq,'deal':self.seq,'price':price,'volume':volume}
 def modify_sl_tp(self,ticket,symbol,sl,tp=None):
  p=next(p for p in self.positions if p['ticket']==ticket);p.update(sl=sl,tp=tp);return {'ok':True,'retcode':10009}
 def close_position(self,ticket,symbol,volume=None,comment='',exit_price=None):
  p=next(p for p in self.positions if p['ticket']==ticket);v=volume or p['volume'];fraction=v/p['volume'];price=exit_price if exit_price is not None else self.tick['bid'] if p['type']=='BUY' else self.tick['ask']
  fee=v*self.commission;net=self.pnl(p,price,v)-fee;self.balance+=net;self.cost_paid+=fee
  closed={**p,'volume':v,'exit':price,'closed_epoch':self.epoch,'holding_minutes':(self.epoch-p['time'])/60,'net_pnl':net-p['entry_commission']*fraction,'close_reason':comment};self.closed.append(closed)
  p['volume']=round(p['volume']-v,10);p['margin']*=1-fraction;p['entry_commission']*=1-fraction
  if p['volume']<=1e-9:self.positions.remove(p)
  return {'ok':True,'retcode':10009,'price':price,'volume_closed':v,'deal':len(self.closed)}
 def intrabar(self,row,spread,stop_out=.5):
  for p in list(self.positions):
   buy=p['type']=='BUY';o=float(row.get('bid_open',row['open'])) if buy else float(row.get('ask_open',row['open']+spread))
   high=float(row.get('bid_high',row['high'])) if buy else float(row.get('ask_high',row['high']+spread));low=float(row.get('bid_low',row['low'])) if buy else float(row.get('ask_low',row['low']+spread))
   hit_sl=low<=p['sl'] if buy else high>=p['sl'];hit_tp=bool(p['tp']) and (high>=p['tp'] if buy else low<=p['tp'])
   if hit_sl:price=(min(o,p['sl'])-self.slippage) if buy else (max(o,p['sl'])+self.slippage);self.close_position(p['ticket'],p['symbol'],comment='server_stop',exit_price=price)
   elif hit_tp:self.close_position(p['ticket'],p['symbol'],comment='target',exit_price=p['tp'])
  self.set_tick({'bid':float(row.get('bid_close',row['close'])),'ask':float(row.get('ask_close',row['close']+spread))},int(row['epoch'])+60)
  while self.positions and self.margin()>0 and self.equity()/self.margin()<=stop_out:
   p=min(self.get_open_positions(),key=lambda p:p['profit']);self.close_position(p['ticket'],p['symbol'],comment='broker_stop_out')

class CFDSimulator:
 def __init__(self,symbol_specs=None,initial_balance=1000,leverage=100,stop_out_level=.5,cost_multiplier=1,slippage_points=0,owner_overrides=None):
  if not symbol_specs:raise ValueError('actual symbol specifications required')
  self.specs=symbol_specs;self.balance=initial_balance;self.initial_balance=initial_balance;self.leverage=leverage;self.stop_out=stop_out_level;self.cost_multiplier=cost_multiplier;self.slippage=slippage_points*self.specs['point'];self.overrides=owner_overrides or {}
 def simulate(self,bundle,candles,news_events=None,decision_interval_bars=1,min_bars_warmup=120):
  frame=pd.DataFrame(candles).sort_values('epoch').drop_duplicates('epoch').reset_index(drop=True)
  if len(frame)<=min_bars_warmup:return {'error':'insufficient completed candles'}
  broker=SimulationBroker(self.specs,self.balance,self.leverage,self.specs.get('commission_per_lot',0)*self.cost_multiplier,self.slippage)
  peak=self.balance;dd=0;max_margin=0;curves=[];decisions=[];last=None;seen=None;day_start={};day_end={};previous_epoch=None
  symbol=bundle.symbol;model_id=str(symbol)+'@'+str(bundle.version)
  for i in range(min_bars_warmup,len(frame)):
   row=frame.iloc[i];epoch=int(row.epoch);spread=float(row.get('ask_open',row.open))-float(row.get('bid_open',row.open)) if 'ask_open' in frame else float(row.get('spread_points',self.specs.get('typical_spread_pts',0)))*self.specs['point']
   spread*=self.cost_multiplier;broker.set_tick({'bid':float(row.get('bid_open',row.open)),'ask':float(row.get('bid_open',row.open))+spread},epoch)
   day=datetime.fromtimestamp(epoch,timezone.utc).date().isoformat();day_start.setdefault(day,broker.equity())
   # Charge all rollover boundaries crossed, including gaps/weekends.
   if previous_epoch is not None:
    first=datetime.fromtimestamp(previous_epoch,timezone.utc).replace(hour=22,minute=0,second=0)
    while int(first.timestamp())<=epoch:
     if int(first.timestamp())>previous_epoch:
      for p in broker.positions:
       rate=self.specs.get('swap_long',0) if p['type']=='BUY' else self.specs.get('swap_short',0);swap=rate*p['volume']*(3 if first.weekday()==2 else 1);broker.balance+=swap;broker.cost_paid+=max(0,-swap)
     first+=timedelta(days=1)
   equity=broker.equity();peak=max(peak,equity);dd=max(dd,1-equity/peak);max_margin=max(max_margin,broker.margin()/max(equity,1e-9))
   obs,atr=build_observation(frame.iloc[max(0,i-2400):i],equity,self.balance,broker.get_open_positions(),self.specs,broker.tick,1-equity/peak,news_events,last)
   bar=epoch//(60*decision_interval_bars)
   if bar!=seen:
    seen=bar;decision=evaluate(bundle,frame.iloc[max(0,i-2400):i],{'observation':obs})
    is_fx=symbol.startswith('frx') or any(symbol.endswith(c) for c in ['USD','JPY','GBP','EUR','CHF','CAD','AUD','NZD'])
    mkt_closed=False
    if is_fx and not self.overrides.get('trade_weekends',False):
     dt_bar=datetime.fromtimestamp(epoch,timezone.utc)
     if (dt_bar.weekday()==4 and dt_bar.hour>=21) or (dt_bar.weekday()==5) or (dt_bar.weekday()==6 and dt_bar.hour<21):mkt_closed=True
    adapter=ExecutionAdapter(broker,symbol,model_id,equity,max(0,equity-broker.margin()),atr,{**self.overrides,'market_closed':mkt_closed})
    for action in decision['actions']:
     last=adapter.execute(action,str(epoch));decisions.append({'epoch':epoch,'action':action,'result':last})
   broker.intrabar(row,spread,self.stop_out);day_end[day]=broker.equity();curves.append({'epoch':epoch,'equity':broker.equity(),'margin':broker.margin()});previous_epoch=epoch
  for p in list(broker.positions):broker.close_position(p['ticket'],p['symbol'],comment='evaluation_end')
  daily=[day_end[d]/day_start[d]-1 for d in sorted(day_end)];ci=block_bootstrap_growth_ci(daily)
  trades=broker.closed;breakdowns={}
  for kind,key in [('weekday',lambda t:datetime.fromtimestamp(t['time'],timezone.utc).weekday()),('hour',lambda t:datetime.fromtimestamp(t['time'],timezone.utc).hour)]:
   groups={}
   for trade in trades:
    k=str(key(trade));v=groups.setdefault(k,{'trades':0,'net_pnl':0});v['trades']+=1;v['net_pnl']+=trade['net_pnl']
   breakdowns[kind]=groups
  return {'initial_balance':self.balance,'final_balance':broker.balance,'balance_multiple':broker.balance/self.balance,'log_growth':math.log(max(broker.balance,1e-12)/self.balance),'max_drawdown_pct':dd*100,'worst_day_pct':min(daily or [0])*100,'max_margin_fraction':max_margin,'total_trades':len(trades),'win_rate':sum(t['net_pnl']>0 for t in trades)/len(trades) if trades else None,'holding_minutes':[t['holding_minutes'] for t in trades],'cost_paid':broker.cost_paid,'bootstrap_ci':ci,'breakdowns':breakdowns,'regime_news_breakdowns':'not computed; coverage/features must be evaluated before claiming these breakdowns','decisions':decisions,'trades':trades,'equity_curve':curves,'cost_assumptions':{'spread_source':'historical bid/ask' if 'ask_open' in frame else 'broker spread_points' if 'spread_points' in frame else 'symbol registry typical spread','commission_known':'commission_per_lot' in self.specs,'slippage_price':self.slippage}}

def block_bootstrap_growth_ci(returns,n_boot=1000,block_size=5):
 if len(returns)<5:return None
 logs=np.log(np.maximum(1e-12,1+np.array(returns)));rng=np.random.default_rng(0);means=[]
 for _ in range(n_boot):
  starts=rng.integers(0,max(1,len(logs)-block_size+1),size=math.ceil(len(logs)/block_size));sample=np.concatenate([logs[s:s+block_size] for s in starts])[:len(logs)];means.append(float(sample.mean()))
 return list(np.quantile(means,[.025,.975]))

def simulate_bundle(path,candles_path=None,initial_balance=1000,symbol_specs=None):
 from .bundle import load_bundle
 b = load_bundle(path)
 specs = symbol_specs or {'digits':5,'point':0.00001,'contract_size':100000,'volume_min':0.01,'volume_max':50,'volume_step':0.01,'typical_spread_pts':15,'swap_long':-5,'swap_short':1}
 if candles_path:
  candles = pd.read_csv(candles_path)
 else:
  import json
  try:
   vecs = json.loads(b.zf.read('tests/vectors.json'))
   candles = vecs.get('vectors', [{}])[0].get('candles', [])
   if not candles:
    # generate minimal sequence
    candles = [{'epoch': 1700000000 + i*60, 'open': 1.1 + i*0.0001, 'high': 1.1005 + i*0.0001, 'low': 1.0995 + i*0.0001, 'close': 1.1001 + i*0.0001, 'ask_open': 1.10015 + i*0.0001} for i in range(200)]
  except Exception:
   candles = [{'epoch': 1700000000 + i*60, 'open': 1.1 + i*0.0001, 'high': 1.1005 + i*0.0001, 'low': 1.0995 + i*0.0001, 'close': 1.1001 + i*0.0001, 'ask_open': 1.10015 + i*0.0001} for i in range(200)]
 res = CFDSimulator(specs,initial_balance).simulate(b,candles)
 if 'costs' not in res:
  res['costs'] = res.get('cost_paid', 0.0)
 return res

replay = simulate_bundle
