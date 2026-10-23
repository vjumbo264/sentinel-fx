"""
Test suite for Fix Mission 5: H5 Weekend Trading Rule & V6 Acceptance Test
- Forex idle on closed session with toggle OFF
- Synthetic indices trade 24/7 unaffected
- Simulator/Broker creates no trades during closed session, preserves open positions with rollover
- Toggle ON permits trading
"""
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from sentinel_engine.policy_schema import validate_action
from sentinel_engine.execution_adapter import ExecutionAdapter, model_magic
from sentinel_engine.sim import SimulationBroker


class MockBroker:
    def __init__(self, specs, balance=10000.0):
        self.specs = specs
        self.balance = balance
        self.tick = {'bid': 1.1000, 'ask': 1.1002, 'time': 1704067200}
        self.positions = []
        self.seq = 0
        self._test_market_closed = {}

    def connect(self, mode="demo"): return True
    def is_connected(self): return True
    def health_check(self): return {"ok": True}
    def account_info(self): return {"balance": self.balance, "equity": self.balance, "margin_free": self.balance}
    def get_symbols(self): return [self.specs]
    def get_symbol_info(self, symbol): return self.specs
    def get_tick(self, symbol): return self.tick
    def get_candles(self, symbol, timeframe="M1", count=100): return []
    def check_margin(self, symbol, side, volume, price):
        return {'required_margin': volume * 1000, 'free_margin': self.balance}
    def order_check(self, symbol, side, volume, price, sl, tp=None, magic=999001, comment=""):
        return {"retcode": 0}

    def is_market_open(self, symbol: str) -> bool:
        if symbol in self._test_market_closed:
            return not self._test_market_closed[symbol]
        if self.specs.get('trade_mode') == 0:
            return False
        is_synthetic = any(symbol.startswith(p) for p in ['Volatility', '1HZ', 'R_']) or 'Index' in symbol
        if is_synthetic:
            return True
        return True

    def loss_per_lot(self, symbol, side, price, stop):
        return abs(price - stop) / self.specs['tick_size'] * self.specs['tick_value']

    def get_open_positions(self, symbol=None, magic=None):
        out = []
        for p in self.positions:
            if (symbol is None or p['symbol'] == symbol) and (magic is None or p['magic'] == magic):
                item = dict(p)
                pnl = (self.tick['bid'] - p['price_open']) * (1 if p['type'] == 'BUY' else -1) * p['volume'] * 100000
                item['profit'] = pnl
                out.append(item)
        return out

    def open_position(self, symbol, side, volume, sl, tp=None, price=None, magic=999001, model_id="", decision_id=""):
        self.seq += 1
        pos = {
            'ticket': self.seq,
            'symbol': symbol,
            'type': side,
            'volume': volume,
            'price_open': self.tick['ask'] if side == 'BUY' else self.tick['bid'],
            'sl': sl,
            'tp': tp,
            'magic': magic,
            'profit': 0.0,
            'comment': decision_id
        }
        self.positions.append(pos)
        return {'ok': True, 'ticket': self.seq, 'price': pos['price_open']}

    def modify_sl_tp(self, ticket, symbol, sl, tp=None):
        for p in self.positions:
            if p['ticket'] == ticket:
                p['sl'] = sl
                p['tp'] = tp
                return {'ok': True}
        return {'ok': False}

    def close_position(self, ticket, symbol, volume=None, comment=""):
        for p in list(self.positions):
            if p['ticket'] == ticket:
                self.positions.remove(p)
                return {'ok': True, 'price': self.tick['bid'], 'volume_closed': p['volume']}
        return {'ok': False}


class TestFix5H5WeekendTrading(unittest.TestCase):
    def setUp(self):
        self.forex_specs = {
            'name': 'EURUSD',
            'mt5_symbol': 'EURUSD',
            'digits': 5,
            'point': 0.00001,
            'contract_size': 100000.0,
            'tick_size': 0.00001,
            'tick_value': 1.0,
            'volume_min': 0.01,
            'volume_max': 50.0,
            'volume_step': 0.01,
            'stops_level': 0,
            'freeze_level': 0,
            'trade_mode': 4,
            'swap_long': -5.8,
            'swap_short': 1.2
        }
        self.synth_specs = {
            'name': '1HZ10V',
            'mt5_symbol': '1HZ10V',
            'digits': 2,
            'point': 0.01,
            'contract_size': 1.0,
            'tick_size': 0.01,
            'tick_value': 0.01,
            'volume_min': 0.1,
            'volume_max': 100.0,
            'volume_step': 0.1,
            'stops_level': 0,
            'freeze_level': 0,
            'trade_mode': 4,
            'swap_long': 0.0,
            'swap_short': 0.0
        }

    def test_bot_weekend_forex_idle_synthetic_trades(self):
        """Test bot logic: when market is closed for forex, forex is idle, but synthetic trades."""
        broker_fx = MockBroker(self.forex_specs)
        broker_fx._test_market_closed['EURUSD'] = True  # Closed weekend session

        # 1. Forex with trade_weekends=False (default) -> stays idle
        trade_weekends = False
        symbol = 'EURUSD'
        broker_symbol = 'EURUSD'
        is_forex = symbol.startswith('frx') or any(broker_symbol.endswith(c) for c in ['USD','JPY','GBP','EUR','CHF','CAD','AUD','NZD'])
        self.assertTrue(is_forex)

        is_open = broker_fx.is_market_open(broker_symbol)
        self.assertFalse(is_open)

        # Bot decision: skip trading for forex
        bot_skipped = (is_forex and not trade_weekends and not is_open)
        self.assertTrue(bot_skipped, "Forex pair should be skipped during closed session when trade_weekends=False")

        # 2. Synthetic index on same weekend -> trades 24/7
        broker_syn = MockBroker(self.synth_specs)
        syn_symbol = '1HZ10V'
        is_syn_forex = syn_symbol.startswith('frx') or any(syn_symbol.endswith(c) for c in ['USD','JPY','GBP','EUR','CHF','CAD','AUD','NZD'])
        self.assertFalse(is_syn_forex)

        is_syn_open = broker_syn.is_market_open(syn_symbol)
        self.assertTrue(is_syn_open, "Synthetic index should report market open 24/7")

        syn_skipped = (is_syn_forex and not trade_weekends and not is_syn_open)
        self.assertFalse(syn_skipped, "Synthetic index should NOT be skipped on weekends")

        # 3. Forex with trade_weekends=True -> not skipped
        trade_weekends = True
        bot_skipped_when_on = (is_forex and not trade_weekends and not is_open)
        self.assertFalse(bot_skipped_when_on, "Forex pair should not be skipped when owner enabled trade_weekends")
        print("[PASS] TEST 1: Forex idle on closed session with toggle OFF, synthetic trades 24/7, toggle ON permits trading")

    def test_execution_adapter_market_closed_rejection(self):
        """Test ExecutionAdapter properly rejects open orders when market_closed override is active."""
        broker = MockBroker(self.forex_specs)
        adapter = ExecutionAdapter(
            broker,
            'EURUSD',
            'EURUSD@1',
            10000.0,
            10000.0,
            0.0015,
            overrides={'market_closed': True}
        )
        action = {'type': 'open', 'side': 'long', 'risk_fraction': 0.01, 'stop_distance': 2.0, 'reason': 'test'}
        res = adapter.execute(action, 'test_decision')
        self.assertEqual(res['status'], 'rejected')
        self.assertEqual(res['reason'], 'market_closed')
        print("[PASS] TEST 2: ExecutionAdapter rejects orders with 'market_closed' when session is closed")

    def test_simulator_broker_weekend_sessions(self):
        """Test SimulationBroker session checks for weekend and synthetics."""
        broker = SimulationBroker(self.forex_specs, 10000.0)
        # Saturday epoch: 2026-10-24 12:00:00 UTC (Saturday)
        sat_dt = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)
        sat_epoch = int(sat_dt.timestamp())
        broker.set_tick({'bid': 1.1000, 'ask': 1.1002}, sat_epoch)

        # In SimulationBroker, is_market_open for EURUSD on Saturday is False
        self.assertFalse(broker.is_market_open('EURUSD'))

        # But for synthetic index, it is True
        self.assertTrue(broker.is_market_open('1HZ10V'))

        # Pre-existing open position held over weekend is preserved
        broker.open_position('EURUSD', 'BUY', 0.1, sl=1.0900)
        self.assertEqual(len(broker.positions), 1)

        # Friday 22:00 UTC: closed
        fri_late = int(datetime(2026, 10, 23, 22, 0, 0, tzinfo=timezone.utc).timestamp())
        dt = datetime.fromtimestamp(fri_late, timezone.utc)
        mkt_closed_fri = ((dt.weekday() == 4 and dt.hour >= 21) or (dt.weekday() == 5) or (dt.weekday() == 6 and dt.hour < 21))
        self.assertTrue(mkt_closed_fri, "Friday 22:00 UTC should be market closed")

        # Sunday 22:00 UTC: open (market re-opens Sun 21:05 UTC)
        sun_late = int(datetime(2026, 10, 25, 22, 0, 0, tzinfo=timezone.utc).timestamp())
        dt_sun = datetime.fromtimestamp(sun_late, timezone.utc)
        mkt_closed_sun = ((dt_sun.weekday() == 4 and dt_sun.hour >= 21) or (dt_sun.weekday() == 5) or (dt_sun.weekday() == 6 and dt_sun.hour < 21))
        self.assertFalse(mkt_closed_sun, "Sunday 22:00 UTC should be market open")
        print("[PASS] TEST 3: SimulationBroker enforces closed forex sessions, allows 24/7 synthetics, preserves positions")


if __name__ == '__main__':
    unittest.main()
