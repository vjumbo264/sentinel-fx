"""GitHub immutable assets, paginated overflow releases and JSON CAS commits."""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = os.environ.get('GITHUB_REPOSITORY', 'vjumbo264/sentinel-fx')

class GitHub:
    def __init__(self, token, repo=REPO):
        if not token or str(token).strip().lower() in ("true", "false"):
            token = os.environ.get("GH_CHAIN_PAT") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
            if str(token).strip().lower() in ("true", "false"):
                token = ""

        self.repo = repo
        self.base = f'https://api.github.com/repos/{repo}'
        self.session = requests.Session()
        self.session.headers.update(Authorization='Bearer ' + token,
                                    Accept='application/vnd.github+json', **{'User-Agent': 'sentinel-overhaul'})

    def request(self, method, path, **kwargs):
        url = path if path.startswith('https://') else self.base + path
        for attempt in range(6):
            response = self.session.request(method, url, timeout=180, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(max(float(response.headers.get('Retry-After', 0) or 0), 2 ** attempt))
                continue
            response.raise_for_status()
            return response
        response.raise_for_status()
        return response

    def releases(self):
        rows, page = [], 1
        while True:
            batch = self.request('GET', f'/releases?per_page=100&page={page}').json()
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            page += 1

    def ensure_release(self, tag):
        response = self.session.get(self.base + '/releases/tags/' + tag, timeout=30)
        if response.status_code == 404:
            return self.request('POST', '/releases', json={'tag_name': tag, 'name': tag}).json()
        response.raise_for_status()
        return response.json()

    def assets(self, release):
        rows, page = [], 1
        while True:
            batch = self.request('GET', f"/releases/{release['id']}/assets?per_page=100&page={page}").json()
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            page += 1

    def download(self, asset):
        return self.request('GET', asset['url'], headers={'Accept': 'application/octet-stream'}).content

    def upload(self, release, name, raw):
        # Asset names are immutable: a retry succeeds only with identical bytes.
        existing = next((a for a in self.assets(release) if a['name'] == name), None)
        if existing:
            if hashlib.sha256(self.download(existing)).digest() != hashlib.sha256(raw).digest():
                raise ValueError('immutable asset name collision: ' + name)
            return existing
        asset = self.request('POST', release['upload_url'].split('{')[0], params={'name': name},
                             data=raw, headers={'Content-Type': 'application/octet-stream'}).json()
        assert hashlib.sha256(self.download(asset)).digest() == hashlib.sha256(raw).digest(), 'upload digest mismatch'
        return asset

    def commit_json(self, path, mutate, message):
        # Contents API creates AND pushes a real commit, retrying concurrent writers.
        for attempt in range(8):
            response = self.session.get(self.base + '/contents/' + path, params={'ref': 'main'}, timeout=30)
            if response.status_code == 404:
                current, sha = {}, None
            else:
                response.raise_for_status()
                data = response.json()
                current, sha = json.loads(base64.b64decode(data['content'])), data['sha']
            result = mutate(current)
            text = json.dumps(result, indent=2) + '\n'
            body = {'message': message, 'content': base64.b64encode(text.encode()).decode(), 'branch': 'main'}
            if sha:
                body['sha'] = sha
            response = self.session.put(self.base + '/contents/' + path, json=body, timeout=30)
            if response.status_code in (409, 422):
                time.sleep(attempt + 1)
                continue
            response.raise_for_status()
            target = ROOT / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            return result
        raise RuntimeError('JSON CAS retries exhausted: ' + path)

    def dispatch(self, workflow, inputs=None):
        self.request('POST', '/actions/workflows/' + workflow + '/dispatches',
                     json={'ref': 'main', 'inputs': inputs or {}})


def pair_key(index, pair):
    return 'frx' + pair if 'frx' + pair in index or pair not in index else pair


def upload_asset_with_overflow(gh_token, repo, pair, filename, data_bytes, size_limit_mb=1800):
    gh = GitHub(gh_token, repo)
    limit = int(size_limit_mb * 1024 * 1024)
    if len(data_bytes) > limit:
        raise ValueError('single asset exceeds shard limit')
    prefix = 'data-' + pair.lower().removeprefix('frx') + '-'
    matching = sorted([(int(r['tag_name'][len(prefix):]), r) for r in gh.releases()
                       if re.fullmatch(re.escape(prefix) + r'\d+', r['tag_name'])], key=lambda item: item[0])
    # Recover an uploaded asset after a crash before index commit, without duplicates.
    for _, rel in matching:
        if any(a['name'] == filename for a in gh.assets(rel)):
            gh.upload(rel, filename, data_bytes)
            tag = rel['tag_name']
            break
    else:
        number, rel = matching[-1] if matching else (1, gh.ensure_release(prefix + '01'))
        total = sum(a['size'] for a in gh.assets(rel))
        if total >= limit or total + len(data_bytes) > limit:
            rel = gh.ensure_release(prefix + f'{number + 1:02d}')
        gh.upload(rel, filename, data_bytes)
        tag = rel['tag_name']
    clean = pair.upper().removeprefix('FRX')
    def merge(index):
        entry = index.setdefault(pair_key(index, clean), {})
        tags = entry.setdefault('shard_releases', [])
        if tag not in tags:
            tags.append(tag)
        return index
    gh.commit_json('data/index.json', merge, f'Q3: index verified {clean} shard {tag} [skip ci]')
    return tag
