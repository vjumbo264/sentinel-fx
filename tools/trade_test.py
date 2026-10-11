#!/usr/bin/env python3
"""Real demo-only lifecycle acceptance. Any missing evidence exits nonzero.
Always attempts cleanup of this test's positions, even if an assertion fails.
"""
import os,sys,json,time,argparse,urllib.request
from datetime import datetime,timezone,timedelta
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from bot.mt5_broker import MT5Broker
MAGIC=999201

def post(path,payload):
 secret=os.environ.get('BOT_SHARED_SECRET');assert secret,'BOT_SHARED_SECRET missing; cannot verify D1'
 req=urllib.request.Request(os.environ.get('WORKER_URL','https://sentinel-fx-worker.vjumbo264.workers.dev')+path,data=json.dumps(payload).encode(),headers={'X-Bot-Secret':secret,'Content-Type':'application/json','Accept':'application/json','User-Agent':'sentinel-trade-test/3.0'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def lifecycle(b,symbol,is_forex=False):
 result={'symbol':symbol,'steps':{},'status':'failed'};start=datetime.now(timezone.utc)-timedelta(seconds=2)
 before=b.account_info()['balance'];opened=[]
 try:
  spec=b.get_symbol_info(symbol);assert spec,'symbol unavailable'
  tick=b.get_tick(symbol);assert tick,'live tick unavailable'
  distance=max(spec['stops_level']*spec['point']*5,(tick['ask']-tick['bid'])*20,500*spec['point'])
  sl=round(tick['bid']-distance,spec['digits']);tp=round(tick['ask']+2*distance,spec['digits']);v=spec['volume_min']
  check=b.order_check(symbol,'BUY',v,tick['ask'],sl,tp,magic=MAGIC,comment='sfx:acceptance')
  result['steps']['order_check']=check
  if is_forex and check['retcode']==10018:
   result.update(status='pending',resume_command='python tools/trade_test.py --forex-only --forex-symbol EURUSD --demo');return result
  assert check['retcode']==0,check
  for index,size in enumerate([v,round(v*2,8)]):
   fill=b.open_position(symbol,'BUY',size,sl,tp,magic=MAGIC,model_id='lifecycle',decision_id=str(index))
   assert fill['retcode'] in (10009,10010) and fill['order'] and fill['deal'],fill
   opened.append(int(fill['order']));result['steps']['open_'+str(index+1)]=fill;time.sleep(1)
  positions=b.get_open_positions(symbol,MAGIC);assert len(positions)>=2,'two hedging positions not found'
  result['steps']['positions']=positions
  p1=next(p for p in positions if p['ticket']==opened[0]);p2=next(p for p in positions if p['ticket']==opened[1])
  mod=b.modify_sl_tp(p1['ticket'],symbol,round(sl-distance,spec['digits']),tp)
  assert mod['retcode']==10009,mod
  result['steps']['modify_stop']=mod
  partial=b.close_position(p2['ticket'],symbol,volume=v,comment='sfx:lifecycle:partial')
  assert partial['retcode']==10009 and partial['deal'],partial
  time.sleep(1);remaining=b.get_open_positions(symbol,MAGIC)
  assert abs(next(p for p in remaining if p['ticket']==p2['ticket'])['volume']-v)<1e-7,'partial size mismatch'
  result['steps']['partial_close']=partial
  for p in remaining:
   if p['ticket'] in opened:
    close=b.close_position(p['ticket'],symbol,comment='sfx:lifecycle:close')
    assert close['retcode']==10009 and close['deal'],close
    result['steps']['close_'+str(p['ticket'])]=close
  time.sleep(2);assert not any(p['ticket'] in opened for p in b.get_open_positions(symbol,MAGIC)),'positions still open'
  deals=[]
  for attempt in range(10):
   deals=[d for d in b.get_history_deals(start,MAGIC) if d['position_id'] in opened]
   if len(deals)>=5:break
   time.sleep(2)
  result['steps']['history_count']=len(deals)
  assert len(deals)>=5 and all(d['ticket'] and d['order'] for d in deals),'missing broker history'
  result['steps']['deals']=deals
  pnl=sum(d['profit']+d['swap']+d['commission']+d['fee'] for d in deals)
  after=b.account_info()['balance'];assert abs((after-before)-pnl)<0.02,'balance/deal reconciliation mismatch'
  assert abs(after-before)>0,'no real balance change'
  result.update(balance_before=before,balance_after=after,realized_net=pnl)
  sync=post('/api/bot/cfd-sync',{'positions':[],'deals':deals,'mode':'demo','balance':after,'model_id':'lifecycle','reason':'real demo lifecycle acceptance'})
  assert sync.get('ok') and abs(sync['net']-pnl)<0.02,'D1 reconciliation failed'
  result['steps']['d1']=sync;result['status']='passing'
 except Exception as error:
  if is_forex and '10018' in str(error):result.update(status='pending',resume_command='python tools/trade_test.py --forex-only --forex-symbol EURUSD --demo')
  else:result['error']=str(error)
 finally:
  for position in b.get_open_positions(symbol,MAGIC):
   if position['ticket'] in opened:
    try:b.close_position(position['ticket'],symbol,comment='sfx:lifecycle:cleanup')
    except Exception as error:result['cleanup_error']=str(error);result['status']='failed'
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--synthetic-symbol',default='Volatility 10 Index');ap.add_argument('--forex-symbol',default='EURUSD');ap.add_argument('--synthetic-only',action='store_true');ap.add_argument('--forex-only',action='store_true');ap.add_argument('--demo',action='store_true');ap.add_argument('--out',default='docs/cfd_trade_test_report.json');a=ap.parse_args()
 report={'status':'failed','tests':{}};b=MT5Broker()
 try:
  assert b.connect('demo'),'demo login failed'
  api=b._get_api();account=api.account_info();terminal=api.terminal_info()
  assert account and int(account.trade_mode)==0,'not a demo account'
  assert terminal and terminal.trade_allowed,'terminal AutoTrading disabled'
  report['terminal_trade_allowed']=True;report['server_offset_hours']=b.get_server_time_offset_hours()
  if not a.forex_only:report['tests']['synthetic']=lifecycle(b,a.synthetic_symbol)
  if not a.synthetic_only:report['tests']['forex']=lifecycle(b,a.forex_symbol,True)
  report['status']='failed' if any(t['status']=='failed' for t in report['tests'].values()) else 'pending' if any(t['status']=='pending' for t in report['tests'].values()) else 'passing'
 except Exception as e:report['error']=str(e)
 finally:
  os.makedirs(os.path.dirname(a.out) or '.',exist_ok=True);open(a.out,'w').write(json.dumps(report,indent=2));print(json.dumps(report,indent=2));b.disconnect()
 sys.exit(1 if report['status']=='failed' else 0)
if __name__=='__main__':main()
