"""Append verified UTC Deriv deltas; existing HistData/base assets are immutable."""
import asyncio, collections, csv, gzip, hashlib, io, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.fetch_candles import pull
from tools.release_utils import GitHub


def utc(epoch=None):
    return datetime.fromtimestamp(epoch,timezone.utc).isoformat() if epoch is not None else datetime.now(timezone.utc).isoformat()


def read_tail(gh,entry):
    metas=entry.get('appends',[])
    if metas:meta=metas[-1]
    elif entry.get('asset'):meta=entry
    else:meta=max(entry.get('bulk_years',{}).values(),key=lambda m:m.get('last_epoch',0),default=None)
    if not meta:return {}
    rel=gh.ensure_release(meta['release_tag'])
    asset=next(a for a in gh.assets(rel) if a['name']==meta['asset'])
    raw=gh.download(asset)
    if meta.get('sha256') and hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Reference checksum mismatch')
    tail=collections.deque(csv.DictReader(io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)))),maxlen=6000)
    return {int(r['epoch'])//60*60:r for r in tail}


def is_closed_fx(epoch):
    d=datetime.fromtimestamp(epoch,timezone.utc)
    return d.weekday()==5 or (d.weekday()==6 and d.hour<21) or (d.weekday()==4 and d.hour>=21)


def check_gap(a,b,is_fx):
    if b-a<=300:return
    if is_fx and sum(not is_closed_fx(t) for t in range(a+60,b,60))<=5:return
    raise ValueError(f'DATA JOIN GAP: {utc(a)} to {utc(b)} ({b-a}s). No asset/index published.')


async def fetch(symbol,boundary):
    return await asyncio.wait_for(pull(symbol,60,boundary),timeout=900)


def main():
    import numpy as np
    symbol=os.environ.get('SYMBOL') or sys.argv[1]
    gh=GitHub(os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN'))
    # Fresh API index, not checkout, because matrix jobs commit independently.
    import base64
    doc=gh.request('GET','/contents/data/index.json?ref=main').json()
    index=json.loads(base64.b64decode(doc['content']));entry=index.get(symbol,{})
    reference=read_tail(gh,entry)
    last=int(entry.get('last_epoch') or max(reference,default=0))//60*60
    boundary=(min(reference) - 1) if reference else int(datetime.now(timezone.utc).timestamp())-7*86400
    bars,source=asyncio.run(fetch(symbol,boundary))
    if getattr(pull,'handoff_required',False):raise ValueError('Deriv pagination incomplete; retry from unchanged boundary')
    current=int(datetime.now(timezone.utc).timestamp())//60*60
    candles={int(c['epoch'])//60*60:c for c in bars if int(c['epoch'])//60*60<current}
    is_fx=symbol.startswith('frx')
    overlap=sorted(set(reference)&set(candles))
    if reference:
        if len(overlap)<20:raise ValueError(f'No usable UTC overlap ({len(overlap)} bars); refuse blind source join')
        differences=[float(candles[t]['close'])-float(reference[t].get('bid_close',reference[t].get('close'))) for t in overlap]
        median=float(np.median(differences));prices=[float(candles[t]['close']) for t in overlap]
        spread=float(np.median([float(candles[t]['high'])-float(candles[t]['low']) for t in overlap]))
        threshold=max(abs(float(np.median(prices)))*.002,spread*10)
        print(f'JOIN {symbol}: epoch=UTC/minute overlap={len(overlap)} median_price_difference={median:.8g} limit={threshold:.8g}',flush=True)
        if abs(median)>threshold:raise ValueError('Large overlap price offset; inspect timezone/source before appending')
    new=sorted(t for t in candles if t>last)
    if not new:
        gh.commit_json('data/index.json',lambda idx:mark_checked(idx,symbol),f'data: {symbol} no newer Deriv candles [skip ci]')
        print('NO NEW CANDLES; no empty asset published',symbol);return
    if last:check_gap(last,new[0],is_fx)
    for a,b in zip(new,new[1:]):check_gap(a,b,is_fx)
    specs={}
    if is_fx:
        specs=json.loads((Path(__file__).resolve().parents[1]/'data/symbols.json').read_text())['symbols'][symbol[3:]]
    rows=[]
    for epoch in new:
        c=candles[epoch];row={'epoch':epoch}
        for field in ('open','high','low','close'):
            value=float(c[field])
            if not np.isfinite(value) or value<=0:raise ValueError('Nonfinite/nonpositive Deriv candle')
            if is_fx:
                row['bid_'+field]=value
                row['ask_'+field]=value+specs['point']*specs.get('typical_spread_pts',15)
            else:row[field]=value
        rows.append(row)
    output=io.StringIO();writer=csv.DictWriter(output,list(rows[0]));writer.writeheader();writer.writerows(rows)
    raw=gzip.compress(output.getvalue().encode(),mtime=0);digest=hashlib.sha256(raw).hexdigest()
    name=f'{symbol}_{new[0]}_{new[-1]}.{digest[:16]}.csv.gz'
    release=gh.ensure_release('data-deriv-appends-01');gh.upload(release,name,raw)
    delta={'asset':name,'release_tag':release['tag_name'],'sha256':digest,'rows':len(rows),
           'first_epoch':new[0],'last_epoch':new[-1],'source':'Deriv UTC','last_update_utc':utc()}
    def merge(idx):
        item=idx.setdefault(symbol,{'symbol':symbol,'rows':0,'first_epoch':new[0]})
        if int(item.get('last_epoch',0) or 0)>last:raise ValueError('Concurrent append boundary changed; retry fresh')
        appends=item.setdefault('appends',[])
        if not any(a['asset']==name for a in appends):
            appends.append(delta);item['rows']=int(item.get('rows',0))+len(rows)
        first=min([int(item.get('first_epoch') or new[0])]+[int(m['first_epoch']) for m in item.get('bulk_years',{}).values() if m.get('first_epoch')])
        item.update(first_epoch=first,first_utc=utc(first),last_epoch=new[-1],last_utc=utc(new[-1]),
                    last_update_utc=utc(),last_checked_utc=utc(),join_median_difference=median if reference else None,
                    join_overlap_rows=len(overlap),timezone='UTC')
        return idx
    gh.commit_json('data/index.json',merge,f'data: append {len(rows)} verified Deriv {symbol} candles [skip ci]')
    print('APPENDED',symbol,len(rows),'data up to',utc(new[-1]),flush=True)


def mark_checked(index,symbol):
    index.setdefault(symbol,{})['last_checked_utc']=utc()
    return index

if __name__=='__main__':main()
