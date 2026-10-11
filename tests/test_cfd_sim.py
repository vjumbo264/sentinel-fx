"""Tests for engine/sentinel_engine/sim.py: CFD Compounding Balance Simulator."""

import pytest
from sentinel_engine.sim import (
    CFDSimulator,
    replay,
    simulate_bundle,
    block_bootstrap_growth_ci,
)


def test_block_bootstrap_growth_ci():
    # Constant positive returns
    returns = [0.01, 0.02, 0.015, 0.01, 0.025, 0.012, 0.018]
    low, high = block_bootstrap_growth_ci(returns, n_boot=200, block_size=2)
    assert low > 0.0
    assert high >= low


def test_cfd_simulator_initialization_and_specs():
    specs = {
        "digits": 5,
        "point": 0.00001,
        "contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_max": 50.0,
        "volume_step": 0.01,
        "typical_spread_pts": 15,
        "swap_long": -5.0,
        "swap_short": 1.0,
    }
    sim = CFDSimulator(
        symbol_specs=specs,
        initial_balance=5000.0,
        leverage=100
    )
    assert sim.initial_balance == 5000.0
    assert sim.leverage == 100
    assert sim.specs["contract_size"] == 100000.0


def test_simulate_clean_v2_bundle_fixture():
    import os
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "clean_v2.sfxmodel.zip")
    res = simulate_bundle(fixture_path, initial_balance=1000.0)
    assert "final_balance" in res
    assert "total_trades" in res
    assert "costs" in res
