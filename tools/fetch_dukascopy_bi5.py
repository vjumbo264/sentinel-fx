#!/usr/bin/env python3
"""Serial UTC hourly tick decoder, bid/ask M1 OHLC, resumable month chunks.
Failures are never represented as empty hours. Months in the URL are zero-based.
"""
import argparse,csv,gzip,hashlib,json,lzma,struct,time,urllib.request,urllib.error
from datetime import datetime,timezone,timedelta
from pathlib import Path
BASE='https://datafeed.dukascopy.com/datafeed'
def price_scale(instrument):return 1000 if instrument.upper().endswith('JPY') else 100000

def fetch_bi5(url,retries=6,base_pause=2):
 for attempt in range(retries):
  try:
   with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:
    if response.status==202:raise RuntimeError('HTTP 202 asynchronous/throttled response')
    raw=response.read()
   if not raw:return b''
   return lzma.decompress(raw,format=lzma.FORMAT_ALONE)
  except urllib.error.HTTPError as error:
   if error.code==404:return b''
   print(f'RETRY {attempt+1} HTTP {error.code} {url}',flush=True)
   if error.code not in (202,429,500,502,503,504):raise
  except (OSError,ValueError,RuntimeError,lzma.LZMAError) as error:print(f'RETRY {attempt+1} {type(error).__name__}: {error} {url}',flush=True)
  time.sleep(min(60,base_pause*2**attempt))
 raise RuntimeError(f'Unresolved hour after {retries} attempts: {url}')

def decode_ticks(data,epoch_hour,scale):
 if len(data)%20:raise ValueError('truncated 20-byte record')
 for ms,ask,bid,av,bv in struct.iter_unpack('>iiiff',data):
  if not 0<=ms<3600000 or bid<=0 or ask<bid:raise ValueError('invalid timestamp or crossed bid/ask')
  yield epoch_hour*1000+ms,bid/scale,ask/scale

def aggregate_m1(ticks,scale=None):
 candles={}
 for ts,bid,ask in ticks:
  key=(ts//60000)*60
  if key not in candles:candles[key]=[bid,bid,bid,bid,ask,ask,ask,ask,1]
  else:
   c=candles[key];c[1]=max(c[1],bid);c[2]=min(c[2],bid);c[3]=bid;c[5]=max(c[5],ask);c[6]=min(c[6],ask);c[7]=ask;c[8]+=1
 return candles

def build_range(instrument,start,end,pause=.25,cache=None):
 cache=Path(cache or '.bi5-cache')/instrument;cache.mkdir(parents=True,exist_ok=True)
 result={};t=start.replace(minute=0,second=0,microsecond=0);hours=empty=0
 while t<end:
  # Known weekend hours only. Sunday/Friday boundaries remain fetched (DST).
  if t.weekday()==5:t+=timedelta(hours=1);continue
  name=t.strftime('%Y%m%d%H')+'.raw';file=cache/name
  url=f'{BASE}/{instrument.upper()}/{t.year}/{t.month-1:02d}/{t.day:02d}/{t.hour:02d}h_ticks.bi5'
  data=file.read_bytes() if file.exists() else fetch_bi5(url)
  if not file.exists():
   temp=file.with_suffix('.tmp');temp.write_bytes(data);temp.replace(file);time.sleep(pause)
  if data:result.update(aggregate_m1(decode_ticks(data,int(t.timestamp()),price_scale(instrument))))
  else:empty+=1
  hours+=1
  if hours%24==0:print(f'PROGRESS hours={hours} empty={empty} rows={len(result)} through={t.isoformat()}',flush=True)
  t+=timedelta(hours=1)
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--instrument',required=True);ap.add_argument('--from',dest='start',required=True);ap.add_argument('--to',dest='end',required=True);ap.add_argument('--out',required=True);ap.add_argument('--cache',default='.bi5-cache');ap.add_argument('--pause',type=float,default=.4);ap.add_argument('--granularity',type=int,default=60);a=ap.parse_args()
 assert a.granularity==60,'M1 only; resample causally in shared features'
 start=datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc);end=datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc)
 rows=build_range(a.instrument,start,end,a.pause,a.cache);assert rows,'refusing to publish an empty dataset'
 columns=['epoch','open','high','low','close','bid_open','bid_high','bid_low','bid_close','ask_open','ask_high','ask_low','ask_close','tick_volume']
 path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(str(path)+'.tmp','wt',newline='') as f:
  w=csv.writer(f);w.writerow(columns)
  for ep in sorted(rows):
   bid=rows[ep][:4];ask=rows[ep][4:8];w.writerow([ep,*bid,*bid,*ask,rows[ep][8]])
 Path(str(path)+'.tmp').replace(path)
 epochs=sorted(rows);gaps=[]
 for before,after in zip(epochs,epochs[1:]):
  if after-before>60:gaps.append({'from':before,'to':after,'seconds':after-before,'weekend':any(datetime.fromtimestamp(before+offset,timezone.utc).weekday()>=5 for offset in range(0,after-before,3600))})
 report={'symbol':'frx'+a.instrument.upper(),'granularity':60,'rows':len(rows),'first_epoch':epochs[0],'last_epoch':epochs[-1],'first_utc':datetime.fromtimestamp(epochs[0],timezone.utc).isoformat(),'last_utc':datetime.fromtimestamp(epochs[-1],timezone.utc).isoformat(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source':'dukascopy-bi5-bid-ask-ticks','columns':columns,'duplicates':0,'crossed_bid_ask':0,'gaps':gaps,'requested_from':start.isoformat(),'requested_to_exclusive':end.isoformat(),'file':path.name,'last_checked_utc':datetime.now(timezone.utc).isoformat()}
 Path(str(path)+'.report.json').write_text(json.dumps(report,indent=2));print('STATS '+json.dumps(report),flush=True)
if __name__=='__main__':main()
