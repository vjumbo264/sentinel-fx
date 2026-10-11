#!/usr/bin/env python3
"""Deliberate content changes only: verified immutable playbook asset + pointer."""
import json,hashlib,base64
from pathlib import Path
from publish_data import api,upload,s,BASE
raw=Path('training-playbook-v1.md').read_bytes()
assert raw==Path('engine/sentinel_engine/training-playbook-v1.md').read_bytes(),'bundled guide drift'
sha=hashlib.sha256(raw).hexdigest();asset=upload('playbook','training-playbook-v1.'+sha[:16]+'.md',raw)
checksum=upload('playbook','training-playbook-v1.'+sha[:16]+'.sha256',(sha+'  '+asset['name']+'\n').encode())
entry={'version':1,'release_tag':'playbook','asset':asset['name'],'url':asset['browser_download_url'],'sha256':sha,'checksum_url':checksum['browser_download_url'],'policy_schema_version':'sentinel.policy.v1'}
path='/contents/data/playbook.json';r=s.get(BASE+path,timeout=30);body={'message':'playbook: verified release pointer [skip ci]','content':base64.b64encode((json.dumps(entry,indent=2)+'\n').encode()).decode()}
if r.ok:body['sha']=r.json()['sha']
api(path,'PUT',json=body);print('PLAYBOOK PUBLISHED',json.dumps(entry))
