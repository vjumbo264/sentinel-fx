#!/usr/bin/env python3
import os, sys, json, hashlib, urllib.request, urllib.parse
from pathlib import Path

GH_TOKEN = os.environ.get('GH_TOKEN') 
REPO = 'vjumbo264/sentinel-fx'
BASE = f'https://api.github.com/repos/{REPO}'

def api_call(url, data=None, headers=None, method='GET'):
    req_headers = {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'sentinel-fx-data-publisher'
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read()

def get_release(tag='data-01'):
    status, body = api_call(f'{BASE}/releases/tags/{tag}')
    return json.loads(body.decode('utf-8'))

def upload_asset(upload_url_tmpl, name, file_path):
    upload_url = upload_url_tmpl.split('{')[0] + '?' + urllib.parse.urlencode({'name': name})
    data = Path(file_path).read_bytes()
    expected_sha = hashlib.sha256(data).hexdigest()
    headers = {'Content-Type': 'application/octet-stream'}
    print(f'Uploading {name} ({len(data)} bytes)...', flush=True)
    status, body = api_call(upload_url, data=data, headers=headers, method='POST')
    asset = json.loads(body.decode('utf-8'))
    download_url = asset['browser_download_url']
    
    # Verify download and sha256
    print(f'Verifying live asset {name} from {download_url}...', flush=True)
    req = urllib.request.Request(download_url, headers={'User-Agent': 'sentinel-fx-verifier'})
    with urllib.request.urlopen(req, timeout=120) as r:
        live_data = r.read()
    live_sha = hashlib.sha256(live_data).hexdigest()
    assert live_sha == expected_sha, f'Verification failed for {name}: expected {expected_sha}, got {live_sha}'
    print(f'VERIFIED {name}: sha256={live_sha[:16]}... matched perfectly.', flush=True)
    return download_url, live_sha

def publish_pair(symbol, cache_dir='data/forex_cache', release_tag='data-01'):
    cache_path = Path(cache_dir)
    rep_file = cache_path / f'{symbol}_60s.csv.gz.report.json'
    assert rep_file.exists(), f'Report not found: {rep_file}'
    rep = json.loads(rep_file.read_text())
    
    rel = get_release(release_tag)
    upload_url_tmpl = rel['upload_url']
    existing_assets = {a['name']: a for a in rel.get('assets', [])}
    
    shards_published = []
    for shard in rep.get('shards', []):
        y = shard['year']
        f_path = cache_path / shard['file']
        sha = shard['sha256']
        name = f'{symbol}_{y}_60s.{sha[:16]}.csv.gz'
        
        if name in existing_assets:
            download_url = existing_assets[name]['browser_download_url']
            verified_sha = sha
            print(f'Shard {name} already in release: {download_url}')
        else:
            download_url, verified_sha = upload_asset(upload_url_tmpl, name, f_path)
            
        shards_published.append({
            'year': y,
            'asset': name,
            'url': download_url,
            'rows': shard['rows'],
            'sha256': verified_sha,
            'first_utc': shard['first_utc'],
            'last_utc': shard['last_utc']
        })
        
    c_sha = rep['sha256']
    c_name = f'{symbol}_60s.{c_sha[:16]}.csv.gz'
    if c_name in existing_assets:
        c_url = existing_assets[c_name]['browser_download_url']
        print(f'Consolidated {c_name} already in release: {c_url}')
    else:
        c_url, _ = upload_asset(upload_url_tmpl, c_name, cache_path / f'{symbol}_60s.csv.gz')
        
    rep['shards'] = shards_published
    rep['asset'] = c_name
    rep['url'] = c_url
    rep['release_tag'] = release_tag
    rep['source'] = 'histdata-verified-forex-m1'
    
    rep_file.write_text(json.dumps(rep, indent=2))
    r_name = f'{c_name}.report.json'
    if r_name not in existing_assets:
        r_url, _ = upload_asset(upload_url_tmpl, r_name, rep_file)
        rep['report_url'] = r_url
    else:
        rep['report_url'] = existing_assets[r_name]['browser_download_url']
        
    idx_path = Path('data/index.json')
    idx = json.loads(idx_path.read_text())
    idx[symbol] = rep
    idx_path.write_text(json.dumps(idx, indent=2) + chr(10))
    print(f'Updated index.json entry for {symbol} ({rep["rows"]} rows, {len(shards_published)} shards).')
    return rep

if __name__ == '__main__':
    sym = sys.argv[1] if len(sys.argv) > 1 else 'frxEURUSD'
    publish_pair(sym)
