import csv
import gzip
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest
from tools.fetch_histdata_bulk import parse_zip, completed_pair
from tools import release_utils as ru

def test_existing_eurusd_is_skipped():
    index = json.loads((ru.ROOT / 'data/index.json').read_text())
    assert completed_pair(index, 'EURUSD')
    assert not completed_pair(index, 'GBPAUD')

def test_histdata_fixed_est_and_ask_synthesis(tmp_path):
    path = tmp_path / 'year.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('bars.csv', '20240101 000000;1.1;1.2;1.0;1.15;0\n')
    rows = parse_zip(path, {'point': .00001})
    epoch, row = next(iter(rows.items()))
    assert epoch == 1704085200  # 00:00 fixed EST = 05:00 UTC.
    assert row[5] - row[1] == pytest.approx(.000015)

class FakeGitHub:
    releases_data = []
    recorded = None
    def __init__(self, *a): pass
    def releases(self): return self.releases_data
    def assets(self, rel): return rel.get('assets', [])
    def ensure_release(self, tag): return {'tag_name': tag, 'assets': []}
    def upload(self, rel, name, raw): return {'name': name}
    def commit_json(self, path, mutate, message):
        FakeGitHub.recorded = mutate({})

def test_overflow_accounts_for_incoming_asset(monkeypatch):
    FakeGitHub.releases_data = [{'tag_name': 'data-eurusd-01', 'assets': [{'name': 'old', 'size': 1048570}]}]
    monkeypatch.setattr(ru, 'GitHub', FakeGitHub)
    assert ru.upload_asset_with_overflow('unused', 'r', 'EURUSD', 'new', b'1234567890', 1) == 'data-eurusd-02'
    assert FakeGitHub.recorded['frxEURUSD']['shard_releases'] == ['data-eurusd-02']

def test_incremental_forex_writer_uses_bid_ask(monkeypatch, tmp_path):
    import tools.fetch_candles as fetch
    monkeypatch.chdir(ru.ROOT)
    epoch = json.loads((ru.ROOT / 'data/index.json').read_text())['frxEURUSD']['last_epoch']
    async def fake_pull(symbol, gran, start_after):
        assert start_after == epoch
        return [{'epoch': epoch + 60, 'open': 1.1, 'high': 1.2, 'low': 1., 'close': 1.15}], 'test-only'
    monkeypatch.setattr(fetch, 'pull', fake_pull)
    monkeypatch.setattr('sys.argv', ['fetch_candles', '--symbol', 'frxEURUSD', '--out', str(tmp_path)])
    fetch.main()
    with gzip.open(tmp_path / 'frxEURUSD_60s.csv.gz', 'rt') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1 and int(rows[0]['epoch']) > epoch
    assert float(rows[0]['ask_close']) > float(rows[0]['bid_close'])
