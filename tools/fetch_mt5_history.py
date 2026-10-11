#!/usr/bin/env python3
"""Honest broker-history fallback. Historical bid candles and reported spread;
NO fabricated historical ask candles or tick volume. Counted MT5 tick_volume
is the broker's own field. Download as much depth as terminal/broker serves.
"""
import os,sys,csv,gzip,json,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from bot.mt5_broker import MT5Broker
b=MT5Broker();assert b.connect('demo'),'demo login required'
api=b._get_api();assert int(api.account_info().trade_mode)==0,'refusing non-demo'
api.symbol_select('EURUSD',True);data={};position=0
for attempt in range(200):
 # Convert NumPy structured rows on the remote native side, not as RPyC proxies.
 rows=b._conn.eval(f"MetaTrader5.copy_rates_from_pos('EURUSD', MetaTrader5.TIMEFRAME_M1, {position}, 5000)")
 if rows is None:
  print('Broker history boundary/error:',api.last_error(),flush=True);break
 local=b._conn.modules.rpyc.utils.classic.obtain(rows.tolist()) if False else [tuple(r) for r in rows.tolist()]
 if not local:break
 fresh=0
 for row in local:
  epoch=int(row[0])
  if epoch not in data:fresh+=1
  data[epoch]=[epoch,float(row[1]),float(row[2]),float(row[3]),float(row[4]),int(row[5]),int(row[6]),int(row[7])]
 print('MT5_HISTORY',position,'rows',len(data),'oldest',datetime.fromtimestamp(min(data),timezone.utc).isoformat(),flush=True)
 if not fresh or len(local)<5000:break
 position+=5000;time.sleep(.3)
assert data,'no broker history; empty upload prohibited'
path=Path('out/frxEURUSD_60s.csv.gz');path.parent.mkdir(exist_ok=True)
columns=['epoch','open','high','low','close','tick_volume','spread_points','real_volume']
with gzip.open(path,'wt',newline='') as f:
 w=csv.writer(f);w.writerow(columns);w.writerows(data[e] for e in sorted(data))
epochs=sorted(data);gaps=[{'from':a,'to':z,'seconds':z-a} for a,z in zip(epochs,epochs[1:]) if z-a>60]
report={'symbol':'frxEURUSD','granularity':60,'source':'Deriv-MT5-copy_rates-bid-history-fallback','source_limitation':'Broker depth only. Bid candles with broker-reported spread; no historical ask OHLC claimed. Dukascopy range attempts returned 202/429/503; see Actions probe logs.','columns':columns,'rows':len(data),'first_epoch':epochs[0],'last_epoch':epochs[-1],'first_utc':datetime.fromtimestamp(epochs[0],timezone.utc).isoformat(),'last_utc':datetime.fromtimestamp(epochs[-1],timezone.utc).isoformat(),'last_checked_utc':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duplicates':0,'gaps':gaps,'bid_ask_validation':'not available for historical OHLC; spread_points must be >=0','negative_spread_rows':sum(r[6]<0 for r in data.values()),'file':path.name}
assert report['negative_spread_rows']==0
Path(str(path)+'.report.json').write_text(json.dumps(report,indent=2));print('STATS '+json.dumps(report),flush=True);b.disconnect()
