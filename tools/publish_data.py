#!/usr/bin/env python3
"""Verified immutable release asset followed by SHA-CAS index update.
Existing history is merged; an index never points at an unverified upload.
"""
import os,sys,json,csv,gzip,hashlib,base64,time,io
from pathlib import Path
import requests
BASE='https://api.github.com/repos/'+os.environ.get('GITHUB_REPOSITORY','vjumbo264/sentinel-fx')
s=requests.Session();s.headers.update({'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
def api(path,method='GET',**kw):
 r=s.request(method,BASE+path,timeout=120,**kw);r.raise_for_status();return r

def load_asset(asset):
 r=s.get(asset['url'],headers={'Accept':'application/octet-stream'},timeout=120);r.raise_for_status();return r.content

def upload(tag,name,data):
 r=s.get(BASE+'/releases/tags/'+tag,timeout=30)
 if r.status_code==404:r=api('/releases','POST',json={'tag_name':tag,'name':tag,'body':'Verified immutable training datasets'})
 r.raise_for_status();release=r.json();existing=next((x for x in release['assets'] if x['name']==name),None)
 if not existing:
  r=s.post(release['upload_url'].split('{')[0],params={'name':name},data=data,headers={'Content-Type':'application/octet-stream'},timeout=120);r.raise_for_status();existing=r.json()
 assert hashlib.sha256(load_asset(existing)).digest()==hashlib.sha256(data).digest(),'uploaded release SHA256 mismatch'
 return existing

def main():
 path=Path(sys.argv[1]);report=json.loads(Path(str(path)+'.report.json').read_text());sym=report['symbol']
 if report.get('no_new_data'):
  print('NO_NEW_DATA '+sym);return
 content=api('/contents/data/index.json').json();index=json.loads(base64.b64decode(content['content']));old=index.get(sym)
 rows={}
 if old and old.get("asset"):
  release=api('/releases/tags/'+old['release_tag']).json();asset=next(x for x in release['assets'] if x['name']==old['asset']);raw=load_asset(asset)
  assert hashlib.sha256(raw).hexdigest()==old['sha256'],'previous data checksum mismatch'
  rows.update({int(row['epoch']):row for row in csv.DictReader(io.StringIO(gzip.decompress(raw).decode()))})
 new=list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
 assert new,'empty input forbidden';rows.update({int(row['epoch']):row for row in new});columns=list(new[0])
 assert all(set(row)==set(columns) for row in rows.values()),'incompatible columns: do not silently fabricate bid/ask'
 text=io.StringIO();w=csv.DictWriter(text,columns);w.writeheader();w.writerows(rows[e] for e in sorted(rows));raw=gzip.compress(text.getvalue().encode(),mtime=0)
 sha=hashlib.sha256(raw).hexdigest();name=f'{sym}_60s.{sha[:16]}.csv.gz';asset=upload('data-01',name,raw)
 epochs=sorted(rows)
 from datetime import datetime,timezone
 report.update(rows=len(rows),first_epoch=epochs[0],last_epoch=epochs[-1],first_utc=datetime.fromtimestamp(epochs[0],timezone.utc).isoformat(),last_utc=datetime.fromtimestamp(epochs[-1],timezone.utc).isoformat(),sha256=sha,asset=name,release_tag='data-01',url=asset['browser_download_url'])
 report_asset=upload('data-01',name+'.report.json',json.dumps(report,indent=2).encode());report['report_url']=report_asset['browser_download_url']
 for attempt in range(6):
  current=api('/contents/data/index.json').json();index=json.loads(base64.b64decode(current['content']));index[sym]={**index.get(sym,{}),**report}
  r=s.put(BASE+'/contents/data/index.json',json={'message':'data: verified '+sym+' immutable release [skip ci]','content':base64.b64encode((json.dumps(index,indent=2)+'\n').encode()).decode(),'sha':current['sha']},timeout=30)
  if r.ok:break
  if r.status_code not in (409,422):r.raise_for_status()
  time.sleep(2**attempt)
 else:raise RuntimeError('index CAS conflicts exhausted')
 print('PUBLISHED '+json.dumps({k:report[k] for k in ['symbol','rows','first_utc','last_utc','sha256','url','report_url']}))
if __name__=='__main__':main()
