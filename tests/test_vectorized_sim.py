import time
import numpy as np
import pytest
from sentinel_engine.vectorized_sim import VectorizedCFDSimulator

def test_vectorized_simulator_throughput_and_correctness():
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
        "commission_per_lot": 0.0
    }
    num_envs = 32
    sim = VectorizedCFDSimulator(symbol_specs=specs, num_envs=num_envs, initial_balance=1000.0)
    
    # Generate 5,000 synthetic bars
    n_bars = 5000
    base_price = 1.1000
    epochs = [1700000000 + i * 60 for i in range(n_bars)]
    noise = np.random.normal(0, 0.0001, n_bars)
    closes = base_price + np.cumsum(noise)
    highs = closes + 0.0003
    lows = closes - 0.0003
    opens = closes - 0.00005
    
    # Pre-generate actions for all steps
    # Alternate buy/sell signals with 1% risk and 20 pt SL
    actions = np.zeros((num_envs, 4), dtype=np.float64)
    actions[:, 1] = 0.01 # 1% risk
    actions[:, 2] = 20 * specs["point"] # 20 pt SL
    actions[:, 3] = 40 * specs["point"] # 40 pt TP
    
    t0 = time.perf_counter()
    for i in range(n_bars):
        # vary action every 20 bars
        if i % 20 == 0:
            actions[:, 0] = np.random.choice([-1, 0, 1], size=num_envs)
        
        sim.step(
            epoch=epochs[i],
            b_o=opens[i], b_h=highs[i], b_l=lows[i], b_c=closes[i],
            a_o=opens[i] + 0.00015, a_h=highs[i] + 0.00015, a_l=lows[i] + 0.00015, a_c=closes[i] + 0.00015,
            actions=actions,
            prev_epoch=epochs[i-1] if i > 0 else 0
        )
    dur = time.perf_counter() - t0
    total_steps = n_bars * num_envs
    steps_per_sec = total_steps / dur
    rep = sim.report()
    
    print(f"\n[VECTORIZED SIMULATOR BENCHMARK]")
    print(f"Total steps: {total_steps:,} across {num_envs} environments in {dur:.3f}s")
    print(f"Throughput: {steps_per_sec:,.0f} steps/second on CPU")
    print(f"Mean Final Equity: ${rep['mean_final_equity']:.2f} (from $1000.00)")
    print(f"Trades per env: {rep['mean_trades_per_env']:.1f}, Win Rate: {rep['mean_win_rate']*100:.1f}%\n")
    
    assert steps_per_sec > 10000, f"Expected >10k steps/sec, got {steps_per_sec}"
    assert rep["mean_final_equity"] > 0
