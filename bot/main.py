"""Fail-closed demo CFD supervisor: learned policy -> shared adapter.
No fixture/model fallback, no lot/price decisions, no hard position cap.
Completed bar inference; atomically leased execution; READY-before-transfer.
"""
import os,sys,time,json,hashlib,logging,urllib.request
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bot.mt5_broker import MT5Broker
from sentinel_engine.bundle import load_bundle
from sentinel_engine.check import check_bundle
from sentinel_engine.plan import evaluate
from sentinel_engine.observation import build_observation
from sentinel_engine.execution_adapter import ExecutionAdapter,model_magic
import pandas as pd
logging.basicConfig(level=logging.INFO);log=logging.getLogger('sentinel.bot')
WORKER=os.environ.get('WORKER_URL') or 'https://sentinel-fx-worker.vjumbo264.workers.dev'
OWNER=os.environ.get('GITHUB_RUN_ID') or ('local-'+str(os.getpid()))
SECRET=os.environ.get('BOT_SHARED_SECRET','');TOKEN=os.environ.get('GH_CHAIN_PAT','');REPO='vjumbo264/sentinel-fx'
WALL=int(os.environ.get('BOT_WALL_SECONDS','17100'))
HARD_STOP=int(os.environ.get('BOT_HARD_STOP_SECONDS','18000'))
HANDOFF=int(os.environ.get('BOT_HANDOFF_LEAD_S','300'));STOP=int(os.environ.get('BOT_STOP_OPEN_LEAD_S','120'))

def http_worker(method,path,body=None,timeout=20):
 req=urllib.request.Request(WORKER+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'X-Bot-Secret':SECRET,'Content-Type':'application/json','Accept':'application/json','User-Agent':'sentinel-bot/4.0'})
 with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
def gh(path):
 req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','User-Agent':'sentinel-bot'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
def decision_log(symbol,obs,out,results):
 http_worker('POST','/api/bot/decision',{'symbol':symbol,'owner':OWNER,'schema_version':obs.schema_version,'inputs_summary':{'equity':obs.equity,'drawdown':obs.drawdown,'positions':len(obs.positions),'news_coverage':obs.news['coverage'],'session':obs.session},'actions':out['actions'],'reason':out['reason'],'results':results,'timestamp_utc':datetime.now(timezone.utc).isoformat()})
def dispatch_next_runner():
 req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/actions/workflows/bot.yml/dispatches',data=json.dumps({'ref':'main','inputs':{'mode':'demo'}}).encode(),headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'sentinel-bot'})
 with urllib.request.urlopen(req,timeout=30) as r:assert r.status==204

class ModelRegistry:
 def __init__(self):self.bundles={};self.errors={};self.last_refresh=0
 def refresh(self,enabled,broker):
  if time.time()-self.last_refresh<30:return
  self.last_refresh=time.time();content=gh('/contents/models/index.json');import base64
  index=json.loads(base64.b64decode(content['content']));cache=Path('cache/models');cache.mkdir(parents=True,exist_ok=True)
  for symbol in enabled:
   if self.errors.get(symbol,0)>=3:continue
   entry=index.get(symbol)
   if not entry:continue
   version=next((v for v in entry['versions'] if v['N']==entry['active_version']),None)
   if not version:continue
   old=self.bundles.get(symbol)
   if old and (old.version==version['N'] or broker.get_open_positions(old.manifest.get('mt5_symbol') or symbol.removeprefix('frx'),model_magic(symbol+'@'+str(old.version)))):continue
   # Hot swaps only at flat state are checked by the supervisor.
   release=gh('/releases/tags/'+version['release_tag']);asset=next(a for a in release['assets'] if a['name']==version['asset'])
   req=urllib.request.Request(asset['browser_download_url'],headers={'User-Agent':'sentinel-bot'})
   with urllib.request.urlopen(req,timeout=120) as response:raw=response.read()
   if hashlib.sha256(raw).hexdigest()!=version['sha256']:raise ValueError('model archive SHA mismatch')
   file=cache/(version['sha256']+'.zip');file.write_bytes(raw)
   report=check_bundle(str(file))
   if not report['ok']:raise ValueError('unhealthy bundle '+str(report['problems']))
   self.bundles[symbol]=load_bundle(str(file));self.errors[symbol]=0
  self.bundles={s:b for s,b in self.bundles.items() if s in enabled}

def main_loop(mode='demo'):
 if not SECRET or not TOKEN:raise ValueError('Worker shared secret and GitHub token required')
 session=http_worker('GET','/api/bot/session')
 settings=session.get('settings',{})
 mode=settings.get('mode',mode)
 broker=MT5Broker();assert broker.connect(mode),f'{mode} login failed'
 if mode=='demo':assert int(broker._get_api().account_info().trade_mode)==0,'non-demo account refused'
 assert broker.health_check()['ok'],'terminal not trading-ready'
 # Startup must be fully ready before claiming/advertising execution lease.
 registry=ModelRegistry();start=time.time();lastbars={};lastresults={};peaks={};dispatched=False;was_leader=False
 since=datetime.now(timezone.utc)-timedelta(days=7)
 try:
  while time.time()-start<HARD_STOP:
   remaining=HARD_STOP-(time.time()-start)
   try:
    session=http_worker('GET','/api/bot/session');settings=session.get('settings',{})
    mode=settings.get('mode',mode)
    enabled=http_worker('GET','/api/bot/models')['symbols']
    registry.refresh(enabled,broker)
    http_worker('POST','/api/bot/ready',{'owner':OWNER,'models':list(registry.bundles),'mode':mode})
    lease=http_worker('POST','/api/bot/lock',{'owner':OWNER})
    if not lease.get('acquired'):time.sleep(5);continue
    was_leader=True
    positions=broker.get_open_positions();deals=broker.get_history_deals(since)
    http_worker('POST','/api/bot/heartbeat',{'mode':mode,'balance':acct['balance'],'equity':acct['equity'],'free_margin':acct['margin_free'],'loginid':str(acct['login'])[:2]+'***','currency':acct['currency'],'note':'active runner '+OWNER})
    ownership=[];ledgers={l['symbol']:l for l in session.get('ledger',[])}
    for symbol,bundle in registry.bundles.items():
     model_id=symbol+'@'+str(bundle.version);magic=model_magic(model_id)
     ownership += [{'position_id':p['ticket'],'model_symbol':symbol,'reason':p.get('comment','')} for p in positions if p['magic']==magic]
     # Also adopt closed deals after restart from deterministic model magic.
     ownership += [{'position_id':d['position_id'],'model_symbol':symbol,'reason':d.get('comment','')} for d in deals if d['magic']==magic]
    http_worker('POST','/api/bot/cfd-sync',{'positions':positions,'deals':deals,'ownership':ownership,'mode':'demo','balance':acct['balance']})
    
    # Risk overrides & UTC daily target / loss limit
    risk_ov=settings.get('risk_overrides_'+mode,{})
    test_day=settings.get('test_day_key')
    today_key=test_day or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    deals_today=[d for d in deals if datetime.fromtimestamp(d.get('time',0),timezone.utc).strftime('%Y-%m-%d')==today_key]
    realized_today=sum(float(d.get('profit',0))+float(d.get('swap',0))+float(d.get('commission',0)) for d in deals_today)
    floating_today=sum(float(p.get('profit',0))+float(p.get('swap',0)) for p in positions)
    today_pnl=realized_today+floating_today

    daily_halt=False
    daily_status='normal'
    daily_reason=''

    dpt=risk_ov.get('daily_profit_target',{})
    if dpt.get('enabled') and dpt.get('value') not in (None,''):
     val=float(dpt['value'])
     target_thresh=val if dpt.get('unit','money')=='money' else (val/100.0)*float(acct['balance'])
     if today_pnl>=target_thresh:
      daily_halt=True;daily_status='daily_target_reached'
      daily_reason=f'Daily profit target reached: +{today_pnl:.2f} >= +{target_thresh:.2f}'
      if dpt.get('close_open_on_hit'):
       for p in positions:
        if p['magic'] in [model_magic(s+'@'+str(b.version)) for s,b in registry.bundles.items()]:broker.close_position(p['ticket'],p['symbol'],comment='sfx:daily_target')

    dll=risk_ov.get('daily_loss_limit',{})
    if dll.get('enabled') and dll.get('value') not in (None,''):
     val=float(dll['value'])
     limit_thresh=val if dll.get('unit','money')=='money' else (val/100.0)*float(acct['balance'])
     if today_pnl<=-limit_thresh:
      daily_halt=True;daily_status='daily_limit_reached'
      daily_reason=f'Daily loss limit reached: {today_pnl:.2f} <= -{limit_thresh:.2f}'
      if dll.get('close_open_on_hit'):
       for p in positions:
        if p['magic'] in [model_magic(s+'@'+str(b.version)) for s,b in registry.bundles.items()]:broker.close_position(p['ticket'],p['symbol'],comment='sfx:daily_limit')

    http_worker('POST','/api/bot/risk-status',{'mode':mode,'today_date':today_key,'realized_pnl':realized_today,'floating_pnl':floating_today,'today_pnl':today_pnl,'status':daily_status,'reason':daily_reason})

    halted=settings.get('halt') or settings.get('stop_all') or daily_halt;ov=http_worker('GET','/api/bot/overrides').get('overrides',[])
    halted=halted or any(o.get('symbol')=='*' and o.get('action')=='stop_all' for o in ov)
    if halted:
     for p in positions:
      if p['magic'] in [model_magic(s+'@'+str(b.version)) for s,b in registry.bundles.items()]:broker.close_position(p['ticket'],p['symbol'],comment='sfx:owner:halt')

    fixed_tp=risk_ov.get('take_profit',{})
    fixed_sl=risk_ov.get('stop_loss',{})
    trade_weekends=bool(risk_ov.get('trade_weekends',False))

    for symbol,bundle in registry.bundles.items():
     if registry.errors.get(symbol,0)>=3:continue
     led=ledgers.get(symbol)
     # No account-balance fallback. Allocation is an owner prerequisite.
     if not led or not led.get('active') or float(led.get('allocated',0))<=0:continue
     broker_symbol=bundle.manifest.get('mt5_symbol') or symbol.removeprefix('frx');model_id=symbol+'@'+str(bundle.version);magic=model_magic(model_id)
     owned=broker.get_open_positions(broker_symbol,magic)
     specs=broker.get_symbol_info(broker_symbol)
     if not specs:continue

     # Weekend check for forex (H5): if market closed and trade_weekends is False, stay idle
     is_forex=symbol.startswith('frx') or any(broker_symbol.endswith(c) for c in ['USD','JPY','GBP','EUR','CHF','CAD','AUD','NZD'])
     if is_forex and not trade_weekends:
      trade_mode=specs.get('trade_mode',4)
      if trade_mode==0:
       log.info('Market closed for forex %s — weekend idle',broker_symbol)
       continue

     candles=broker.get_candles(broker_symbol,'M1',2400)
     if len(candles)<120:continue
     entry_seconds=int(bundle.manifest.get('entry_seconds',60));completed=int(candles[-1]['epoch'])//entry_seconds
     if lastbars.get(symbol)==completed:continue
     lastbars[symbol]=completed
     share=float(led['balance']);equity=share+sum(p['profit']+p.get('swap',0) for p in owned);peaks[symbol]=max(peaks.get(symbol,equity),equity)
     tick=broker.get_tick(broker_symbol);frame=pd.DataFrame(candles)
     obs,atr=build_observation(frame,equity,float(led['allocated']),owned,specs,tick,max(0,1-equity/peaks[symbol]),last_result=lastresults.get(symbol))
     out=evaluate(bundle,frame,{'observation':obs})
     if out.get('error'):
      registry.errors[symbol]=registry.errors.get(symbol,0)+1;decision_log(symbol,obs,out,[]);continue
     pause=any(o.get('symbol')==symbol and o.get('action')=='pause' for o in ov)
     overrides={
      'halt':bool(halted or pause or remaining<STOP),
      'max_exposure_enabled':bool(settings.get('ov_max_lot_enabled')),
      'max_exposure_lots':float(settings.get('ov_max_lot',0)),
      'fixed_tp_enabled':bool(fixed_tp.get('enabled')),
      'fixed_tp_unit':fixed_tp.get('unit','money'),
      'fixed_tp_value':fixed_tp.get('value'),
      'fixed_sl_enabled':bool(fixed_sl.get('enabled')),
      'fixed_sl_unit':fixed_sl.get('unit','money'),
      'fixed_sl_value':fixed_sl.get('value')
     }
     used=sum(broker.check_margin(broker_symbol,p['type'],p['volume'],p['price_current'])['required_margin'] for p in owned)
     adapter=ExecutionAdapter(broker,broker_symbol,model_id,equity,min(acct['margin_free'],max(0,float(led['allocated'])-used)),atr,overrides)
     results=[]
     for action in out['actions']:
      # Renew/verify lease immediately before each broker mutation.
      if not http_worker('POST','/api/bot/lock',{'owner':OWNER}).get('acquired'):break
      result=adapter.execute(action,str(candles[-1]['epoch']));results.append(result);lastresults[symbol]=result
     decision_log(symbol,obs,out,results)
    if time.time()-start>=WALL and not dispatched and os.environ.get('BOT_CHAIN','true')=='true':dispatch_next_runner();dispatched=True
    if remaining<STOP and dispatched:
     ready=http_worker('GET','/api/bot/ready').get('runners',[]);successor=next((r for r in ready if r['owner']!=OWNER),None)
     if successor:
      transfer=http_worker('POST','/api/bot/transfer',{'owner':OWNER,'new_owner':successor['owner']})
      if transfer.get('transferred'):log.info('HANDOVER confirmed READY successor=%s',successor['owner']);was_leader=False;break
    log.info('HEARTBEAT owner=%s elapsed=%.0fs balance=%.2f models=%s',OWNER,time.time()-start,acct['balance'],len(registry.bundles))
   except Exception as error:
    log.error('FAIL CLOSED: %s',error)
   time.sleep(10)
 finally:
  if was_leader:
   try:http_worker('POST','/api/bot/unlock',{'owner':OWNER})
   except Exception:pass
  broker.disconnect()
if __name__=='__main__':main_loop(os.environ.get('BOT_MODE','demo'))
