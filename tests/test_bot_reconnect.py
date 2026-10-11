"""Tests for bot/main.py: CFD Supervisor, Circuit Breaker, and Fail-Closed Safety."""

import pytest
import bot.main as bm


def test_model_registry_circuit_breaker():
    registry = bm.ModelRegistry()
    sym = "EURUSD"

    assert registry.error_counts.get(sym, 0) == 0
    assert not registry.circuit_breakers.get(sym)

    # 1st error
    registry.record_error(sym)
    assert registry.error_counts[sym] == 1
    assert not registry.circuit_breakers.get(sym)

    # 2nd error
    registry.record_error(sym)
    assert registry.error_counts[sym] == 2
    assert not registry.circuit_breakers.get(sym)

    # 3rd error triggers circuit breaker
    registry.record_error(sym)
    assert registry.error_counts[sym] == 3
    assert registry.circuit_breakers[sym] is True


def test_fail_closed_worker_http_swallows_errors(monkeypatch):
    # Ensure network errors to Worker never crash the supervisor
    def faulty_urlopen(*args, **kwargs):
        raise ConnectionRefusedError("Simulated worker connection failure")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", faulty_urlopen)

    res = bm.http_worker("POST", "/api/bot/heartbeat", {"ping": 1})
    assert res == {}
