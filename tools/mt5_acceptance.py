#!/usr/bin/env python3
"""Seven ordered native MT5 demo acceptance checks. Never invent live evidence."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from bot.mt5_broker import MT5Broker
from sentinel_engine.observation import build_observation, vectorize
from sentinel_engine.execution_adapter import ExecutionAdapter
from tools.trade_test import lifecycle

PAIRS = 'EURUSD GBPUSD USDJPY USDCHF AUDUSD USDCAD NZDUSD EURGBP EURJPY GBPJPY AUDJPY EURAUD GBPAUD'.split()

def run():
    report = {'status': 'failed', 'executed': True,
              'updated_utc': datetime.now(timezone.utc).isoformat(),
              'steps': [{'step': i, 'status': 'not_run'} for i in range(1, 8)]}
    broker = MT5Broker()
    current = 0
    def passed(data):
        report['steps'][current].update(status='passing', evidence=data)
    try:
        assert broker.connect('demo'), 'demo login failed'
        acct = broker.account_info()
        assert acct['balance'] > 0 and acct['mode'] == 'demo', 'invalid demo account'
        assert int(broker._get_api().account_info().trade_mode) == 0, 'non-demo terminal refused'
        passed({'balance': acct['balance'], 'mode': acct['mode'], 'login': acct['login']})
        current = 1
        ticks = {}
        for pair in PAIRS:
            info = broker.get_symbol_info(pair)
            tick = broker.get_tick(pair)
            assert info is not None, pair + ' symbol info missing'
            assert tick and tick['bid'] > 0 and tick['ask'] >= tick['bid'], pair + ' tick missing'
            ticks[pair] = tick
        passed(ticks)
        current = 2
        candles = broker.get_candles('EURUSD', 'M1', count=100)
        assert len(candles) >= 50, f'only {len(candles)} candles'
        passed({'candle_count': len(candles)})
        current = 3
        tick = broker.get_tick('EURUSD')
        info = broker.get_symbol_info('EURUSD')
        sl = round(tick['bid'] - .0020, info['digits'])
        tp = round(tick['ask'] + .0040, info['digits'])
        check = broker.order_check('EURUSD', 'BUY', info['volume_min'], tick['ask'], sl, tp,
                                   magic=999001, comment='sfx:acceptance')
        assert check['retcode'] in (0, 10018), f'unexpected order_check: {check}'
        passed(check)
        if check['retcode'] == 10018:
            report['steps'][current]['status'] = 'pending'
        current = 4
        result = lifecycle(broker, 'EURUSD', is_forex=True)
        report['steps'][current].update(status=result['status'], evidence=result)
        assert result['status'] in ('passing', 'pending'), str(result)
        current = 5
        obs, atr = build_observation(pd.DataFrame(candles), equity=10000, pool_share=10000,
                                     positions=[], specs=info, tick=tick)
        vec = vectorize(obs)
        assert vec.shape == (47,) and np.isfinite(vec).all(), 'invalid observation vector'
        passed({'dim': list(vec.shape), 'atr': atr})
        current = 6
        adapter = ExecutionAdapter(broker, 'EURUSD', 'test-model', pool_equity=10000,
                                   pool_free_margin=10000, volatility=atr)
        result = adapter.execute({'type': 'hold', 'reason': 'acceptance test'})
        assert result['status'] == 'filled', f'hold failed: {result}'
        passed(result)
        report['status'] = 'pending' if any(s['status'] == 'pending' for s in report['steps']) else 'passing'
    except Exception as exc:
        report['steps'][current].update(status='failed', error=str(exc))
        report['error'] = str(exc)
    finally:
        try:
            broker.disconnect()
        finally:
            out = Path('docs/mt5_windows_acceptance.json')
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2, default=str) + '\n')
            print(json.dumps(report, indent=2, default=str))
    return 1 if report['status'] == 'failed' else 0

if __name__ == '__main__':
    sys.exit(run())
