"""FIX-C unit tests: US/Eastern -> UTC conversion, Aurelia-style fetch
fallback order, rate-limit guard, and stale-cache behaviour."""
import json
from datetime import datetime, timezone

import pytest

from sentinel_engine import news as newsmod

# Captured-shape sample (ForexFactory weekly file carries US/Eastern offsets)
SAMPLE = [
    {"title": "Non-Farm Employment Change", "country": "USD",
     "date": "2026-10-02T08:30:00-04:00", "impact": "High",
     "forecast": "51K", "previous": "22K"},
    {"title": "ECB Press Conference", "country": "EUR",
     "date": "2026-10-08T14:45:00-04:00", "impact": "Medium",
     "forecast": "", "previous": ""},
]


def test_eastern_offset_converts_to_utc():
    ev = newsmod.normalize(SAMPLE)
    # 08:30 at UTC-4 == 12:30 UTC
    assert ev[0]["utc_time"] == "2026-10-02T12:30:00Z"
    assert ev[0]["currency"] == "USD"
    assert ev[0]["impact"] == "high"
    assert ev[1]["utc_time"] == "2026-10-08T18:45:00Z"


def test_shape_validation_rejects_garbage():
    with pytest.raises(RuntimeError, match="unexpected schema"):
        newsmod._validate_shape({"not": "a list"})
    with pytest.raises(RuntimeError, match="schema mismatch"):
        newsmod._validate_shape([{"foo": 1}])


def test_rate_limit_guard(monkeypatch):
    monkeypatch.setattr(newsmod, "_REQUEST_TS", [1e18] * 2)  # far-future stamps
    with pytest.raises(RuntimeError, match="rate-limit guard"):
        newsmod.fetch_calendar("http://127.0.0.1:1/x", max_per_300s=2)


def test_minutes_to_event_and_state():
    ev = newsmod.normalize(SAMPLE)
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    m = newsmod.minutes_to_event(ev, now, {"USD"})
    assert m == pytest.approx(30.0)
    assert newsmod.news_state("CALL", 5.0) == "for"
    assert newsmod.news_state("PUT", 5.0) == "against"
    assert newsmod.news_state("CALL", None) == "none"


def test_stale_cache_fallback():
    cache = {"fetched_utc": "2026-10-01T00:00:00Z", "events": SAMPLE}

    def boom(url, timeout=30, max_per_300s=2):
        raise RuntimeError("news fetch failed: HTTP 502 Bad Gateway")

    import sentinel_engine.news as n
    orig = n.fetch_calendar
    n.fetch_calendar = boom
    try:
        events, meta = newsmod.fetch_weeks(cache_get=lambda: cache,
                                           cache_set=lambda p: None,
                                           refresh_s=0)
    finally:
        n.fetch_calendar = orig
    assert meta["stale"] is True
    assert "HTTP 502" in meta["error"]
    assert events == SAMPLE
