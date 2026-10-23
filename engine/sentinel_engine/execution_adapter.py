"""The single translation layer for live MT5 AND simulator broker ports.
Never rounds volume UP to broker minimum; that would increase intended risk.
Always attaches a server-side stop, including when a policy omits its distance.
"""
import hashlib,math,time
from .policy_schema import validate_action,ActionResult

def model_magic(model_id):return 100000+int(hashlib.sha256(model_id.encode()).hexdigest()[:7],16)

def floor_step(value,step):return round(math.floor((value+1e-10)/step)*step,10)

class ExecutionAdapter:
 def __init__(self,broker,symbol,model_id,pool_equity,pool_free_margin,volatility,overrides=None):
  self.broker=broker;self.symbol=symbol;self.model_id=model_id;self.magic=model_magic(model_id)
  self.equity=float(pool_equity);self.free=float(pool_free_margin);self.atr=float(volatility) if math.isfinite(float(volatility)) and float(volatility)>0 else 1e-5;self.overrides=overrides or {}
 def positions(self):return self.broker.get_open_positions(self.symbol,self.magic)
 def reject(self,reason,details=None):return ActionResult('rejected',reason,clamped=details or {}).to_dict()
 def execute(self,action,decision_id=''):
  try:
   validate_action(action)
   kind=action['type']
   if kind=='hold':return ActionResult('filled','hold',size=0).to_dict()
   ps=self.positions();position=None
   if kind not in ('open','hold'):
    position=next((p for p in ps if str(p['ticket'])==str(action['position_ref'])),None)
    if position is None:return self.reject('invalid',{'detail':'position_ref not owned by model'})
   if kind=='open':return self.open(action,decision_id)
   if kind=='add':
    side='long' if position['type']=='BUY' else 'short';tick=self.broker.get_tick(self.symbol);price=tick['ask'] if side=='long' else tick['bid']
    intent={'type':'open','side':side,'risk_fraction':action['risk_fraction'],'stop_distance':abs(price-position['sl'])/self.atr,'targets':[{'distance':abs(position['tp']-price)/self.atr,'fraction':1}] if position.get('tp') else [],'reason':action['reason']}
    return self.open(intent,decision_id)
   if kind in ('reduce','close','reverse'):
    fraction=action.get('fraction',1) if kind=='reduce' else 1
    specs=self.broker.get_symbol_info(self.symbol);volume=floor_step(position['volume']*fraction,specs['volume_step'])
    if volume<specs['volume_min']:return self.reject('broker_limit',{'detail':'partial volume below minimum'})
    remainder=position['volume']-volume
    if 0<remainder<specs['volume_min']:volume=position['volume']
    result=self.broker.close_position(position['ticket'],self.symbol,volume=volume,comment='sfx:'+decision_id[:20])
    if not result.get('ok'):return self.reject('broker_limit',{'retcode':result.get('retcode')})
    self.free=min(self.equity,self.free+float(position.get('margin',0))*fraction)
    if kind=='reverse':
     # Reverse only after the close succeeded, preserving the old risk budget.
     specs=self.broker.get_symbol_info(self.symbol)
     risk=abs(position['price_open']-position['sl'])*position['volume']*specs['contract_size']/max(self.equity,1e-9)
     intent={'type':'open','side':'short' if position['type']=='BUY' else 'long','risk_fraction':min(1,risk),'stop_distance':abs(position['price_open']-position['sl'])/self.atr,'reason':action['reason']}
     return self.open(intent,decision_id)
    return ActionResult('partial' if volume<position['volume'] else 'filled',price=result.get('price'),size=volume,clamped={'fraction':volume/position['volume']},tickets=[position['ticket']]).to_dict()
   if kind=='move_stop':
    specs=self.broker.get_symbol_info(self.symbol);tick=self.broker.get_tick(self.symbol);sign=1 if position['type']=='BUY' else -1;price=tick['bid'] if sign==1 else tick['ask']
    min_dist=max(specs.get('stops_level',0),specs.get('freeze_level',0))*specs['point']+specs['point']
    if action.get('to_breakeven'):stop=position['price_open']
    else:stop=price-sign*self.atr*action.get('new_stop_distance',action.get('trail'))
    if action.get('trail') and (stop-position['sl'])*sign<=0:return ActionResult('filled','trailing stop unchanged',size=0).to_dict()
    stop=round(stop,specs['digits'])
    if (price-stop)*sign<min_dist or stop<=0:return self.reject('broker_limit',{'detail':'stop inside stops/freeze boundary'})
    result=self.broker.modify_sl_tp(position['ticket'],self.symbol,stop,position.get('tp'))
    if not result.get('ok'):return self.reject('broker_limit',{'retcode':result.get('retcode')})
    return ActionResult('filled',size=position['volume'],clamped={'sl':stop},tickets=[position['ticket']]).to_dict()
   return self.reject('invalid')
  except (ValueError,KeyError,TypeError) as error:return self.reject('invalid',{'detail':str(error)})
  except Exception as error:
   text=str(error).lower();reason='market_closed' if '10018' in text or 'closed' in text else 'margin' if 'margin' in text else 'broker_limit'
   return self.reject(reason,{'detail':str(error)})
 def open(self,action,decision_id):
  if self.overrides.get('halt') or self.overrides.get('pause'):return self.reject('owner_override')
  if self.overrides.get('market_closed'):return self.reject('market_closed',{'detail':'trading session closed'})
  if hasattr(self.broker,'is_market_open') and not self.broker.is_market_open(self.symbol):return self.reject('market_closed',{'detail':'broker session closed'})
  specs=self.broker.get_symbol_info(self.symbol);tick=self.broker.get_tick(self.symbol)
  if not specs or not tick or tick['ask']<=0 or tick['bid']<=0:return self.reject('market_closed')
  side='BUY' if action['side']=='long' else 'SELL';sign=1 if side=='BUY' else -1;price=tick['ask'] if sign==1 else tick['bid'];opposite=tick['bid'] if sign==1 else tick['ask']
  protective=action.get('stop_distance') is None;distance=self.atr*(action.get('stop_distance') or 2)
  min_dist=max(specs.get('stops_level',0),specs.get('freeze_level',0))*specs['point']+specs['point']
  stop=round(opposite-sign*max(distance,min_dist),specs['digits'])
  if self.overrides.get('fixed_sl_enabled') and self.overrides.get('fixed_sl_value') not in (None, ''):
   sl_val=float(self.overrides['fixed_sl_value'])
   if sl_val>0:
    sl_unit=self.overrides.get('fixed_sl_unit','money')
    target_loss=sl_val if sl_unit=='money' else (sl_val/100.0)*self.equity
    tick_pt=float(specs.get('tick_value') or specs['point'])/max(float(specs.get('tick_size') or specs['point']),1e-9)
    sl_pts=target_loss/max(self.equity*action['risk_fraction']*tick_pt,1e-9)
    sl_delta=max(sl_pts*specs['point'],min_dist)
    stop=round(opposite-sign*sl_delta,specs['digits'])
  if stop<=0:return self.reject('invalid',{'detail':'nonpositive server stop'})
  loss_per_lot=abs(price-stop)/float(specs.get('tick_size') or specs['point'])*float(specs.get('tick_value') or 0)
  if hasattr(self.broker,'loss_per_lot'):loss_per_lot=self.broker.loss_per_lot(self.symbol,side,price,stop)
  if loss_per_lot<=0:return self.reject('invalid',{'detail':'broker tick-value or native profit conversion unavailable'})
  requested=self.equity*action['risk_fraction']/loss_per_lot;step=specs['volume_step'];volume=floor_step(min(requested,specs['volume_max']),step)
  if self.overrides.get('max_exposure_enabled'):
   max_lots=float(self.overrides['max_exposure_lots']);room=max_lots-sum(p['volume'] for p in self.positions());volume=floor_step(min(volume,max(0,room)),step)
  if volume<specs['volume_min']:return self.reject('owner_override' if self.overrides.get('max_exposure_enabled') else 'broker_limit',{'requested_lots':requested,'detail':'size below minimum; never rounded upward'})
  margin=self.broker.check_margin(self.symbol,side,volume,price)
  available=min(self.free,float(margin['free_margin']))
  if margin['required_margin']>available:
   volume=floor_step(volume*available/max(margin['required_margin'],1e-12),step)
   if volume<specs['volume_min']:return self.reject('margin')
  targets=action.get('targets',[]);parts=[];left=volume
  if self.overrides.get('fixed_tp_enabled') and self.overrides.get('fixed_tp_value') not in (None, ''):
   tp_val=float(self.overrides['fixed_tp_value'])
   if tp_val>0:
    tp_unit=self.overrides.get('fixed_tp_unit','money')
    target_profit=tp_val if tp_unit=='money' else (tp_val/100.0)*self.equity
    tick_pt=float(specs.get('tick_value') or specs['point'])/max(float(specs.get('tick_size') or specs['point']),1e-9)
    tp_pts=target_profit/max(volume*tick_pt,1e-9)
    tp_delta=max(tp_pts*specs['point'],min_dist)
    tp_override=round(price+sign*tp_delta,specs['digits'])
    parts=[[volume,tp_override]]
  if not parts:
   for target in targets:
    size=floor_step(volume*target['fraction'],step)
    if size>=specs['volume_min']:
     tp=round(price+sign*max(target['distance']*self.atr,min_dist),specs['digits']);parts.append([size,tp]);left=round(left-size,10)
   if left>=specs['volume_min']:parts.append([left,None])
   elif left>0 and parts:parts[-1][0]+=left
   if not parts:parts=[[volume,round(price+sign*max(targets[-1]['distance']*self.atr,min_dist),specs['digits']) if targets else None]]
  # Plans below a target's minimum size are conservatively combined; risk never increases.
  tickets=[];filled=0;weighted_price=0
  for size,tp in parts:
   for attempt in range(3):
    try:
     fill=self.broker.open_position(self.symbol,side,size,stop,tp,magic=self.magic,model_id=self.model_id,decision_id=decision_id+str(len(tickets)))
     if not fill.get('ok'):raise RuntimeError('order rejected retcode '+str(fill.get('retcode')))
     tickets.append(fill.get('ticket') or fill.get('order'));filled+=size;weighted_price+=float(fill['price'])*size
     used=self.broker.check_margin(self.symbol,side,size,fill['price'])['required_margin'];self.free=max(0,self.free-used)
     break
    except Exception as error:
     if attempt==2 or not any(c in str(error) for c in ('10004','10020','10021','10016')):
      if filled:return ActionResult('partial',str(error),price=weighted_price/filled,size=filled,clamped={'sl':stop,'risk_fraction':filled*loss_per_lot/self.equity,'protective_stop':protective},tickets=tickets).to_dict()
      raise
     tick=self.broker.get_tick(self.symbol);price=tick['ask'] if sign==1 else tick['bid'];opposite=tick['bid'] if sign==1 else tick['ask'];stop=round(opposite-sign*max(distance,min_dist*1.5),specs['digits'])
     # Recompute risk: a widened retry stop must not increase allocated loss.
     retry_loss=self.broker.loss_per_lot(self.symbol,side,price,stop) if hasattr(self.broker,'loss_per_lot') else abs(price-stop)/specs['tick_size']*specs['tick_value']
     size=floor_step(min(size,self.equity*action['risk_fraction']/retry_loss),step)
     if size<specs['volume_min']:raise ValueError('retry size below broker minimum')
  return ActionResult('filled',price=weighted_price/filled,size=filled,clamped={'sl':stop,'risk_fraction':filled*loss_per_lot/self.equity,'protective_stop':protective,'targets':parts},tickets=tickets).to_dict()
