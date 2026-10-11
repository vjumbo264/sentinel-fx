"""Pinned CLI for data-only CFD policy training, checking and delivery."""
import argparse,hashlib,json,os,sys,zipfile,urllib.request
from pathlib import Path

def cmd_guide(a):
 p=Path(__file__).with_name('training-playbook-v1.md')
 if not p.exists():raise ValueError('Bundled playbook missing; use verified release asset')
 print(p.read_text())
def cmd_init(a):
 target=Path(a.dir or ('train_'+a.symbol));target.mkdir(parents=True,exist_ok=True)
 (target/'manifest.json').write_text(json.dumps({'schema_version':2,'policy_schema_version':'sentinel.policy.v1','symbol':a.symbol,'version':1,'entry_timeframe':'M1','files':[]},indent=2))
 print('Workspace created; export trained models and embedded parity vectors here. Keep trainer source scripts OUTSIDE bundle directory.')
def cmd_build(a):
 from .bundle import BANNED_EXT,verify_bundle
 source=Path(a.dir);files=[];manifest=json.loads((source/'manifest.json').read_text());output=Path(a.out).resolve()
 for p in sorted(source.rglob('*')):
  if not p.is_file() or p.name=='manifest.json' or p.resolve()==output:continue
  rel=p.relative_to(source).as_posix()
  if rel.lower().endswith(BANNED_EXT):raise ValueError('Code/executable prohibited in model bundle: '+rel)
  raw=p.read_bytes();files.append({'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)})
 manifest.update(schema_version=2,policy_schema_version='sentinel.policy.v1',files=files)
 with zipfile.ZipFile(a.out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('manifest.json',json.dumps(manifest,indent=2))
  for f in files:z.write(source/f['path'],f['path'])
 ok,problems=verify_bundle(a.out)
 if not ok:raise ValueError('; '.join(problems))
 print('BUILT',a.out,hashlib.sha256(Path(a.out).read_bytes()).hexdigest())
def cmd_check(a):
 from .check import check_bundle
 report=check_bundle(a.bundle);print(json.dumps(report,indent=2));sys.exit(0 if report['ok'] else 1)
def cmd_sim(a):
 from .sim import simulate_bundle
 report=simulate_bundle(a.bundle,a.candles,a.balance,json.loads(Path(a.specs).read_text()));text=json.dumps(report,indent=2)
 if a.out:Path(a.out).write_text(text);print('Report:',a.out)
 else:print(text)
def cmd_publish(a):
 token=os.environ.get('GITHUB_TOKEN','')
 if not token:raise ValueError('GITHUB_TOKEN environment required; do not pass tokens on command line')
 # Upload staged bundle then trigger public secret-free checker. No trading.
 from urllib.parse import quote
 base='https://api.github.com/repos/vjumbo264/sentinel-fx'
 def req(url,method='GET',body=None,ctype='application/json'):
  request=urllib.request.Request(url,data=body,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':ctype,'User-Agent':'sentinel-cli'})
  with urllib.request.urlopen(request,timeout=120) as r:return json.load(r) if r.status!=204 else {}
 try:release=req(base+'/releases/tags/staging')
 except Exception:release=req(base+'/releases','POST',json.dumps({'tag_name':'staging','name':'staging'}).encode())
 name=a.symbol+'_v'+str(a.version)+'.sfxmodel.zip'
 for asset in release.get('assets',[]):
  if asset['name']==name:req(asset['url'],'DELETE')
 req(release['upload_url'].split('{')[0]+'?name='+quote(name),'POST',Path(a.bundle).read_bytes(),'application/zip')
 req(base+'/actions/workflows/publish-model.yml/dispatches','POST',json.dumps({'ref':'main','inputs':{'symbol':a.symbol,'version':str(a.version)}}).encode())
 print('Publication dispatched; checker must succeed before installation (installed disabled). https://github.com/vjumbo264/sentinel-fx/actions/workflows/publish-model.yml')
def main():
 ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='command',required=True)
 p=sub.add_parser('guide');p.set_defaults(fn=cmd_guide)
 p=sub.add_parser('init');p.add_argument('symbol');p.add_argument('--dir');p.set_defaults(fn=cmd_init)
 p=sub.add_parser('build');p.add_argument('dir');p.add_argument('out');p.set_defaults(fn=cmd_build)
 p=sub.add_parser('check');p.add_argument('bundle');p.set_defaults(fn=cmd_check)
 p=sub.add_parser('sim');p.add_argument('bundle');p.add_argument('--candles',required=True);p.add_argument('--specs',required=True);p.add_argument('--balance',type=float,default=1000);p.add_argument('--out');p.set_defaults(fn=cmd_sim)
 p=sub.add_parser('publish');p.add_argument('bundle');p.add_argument('--symbol',required=True);p.add_argument('--version',type=int,required=True);p.set_defaults(fn=cmd_publish)
 a=ap.parse_args()
 try:a.fn(a)
 except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()
