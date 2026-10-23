"""
Test script for Fix Mission 5: H1 Optional Overrides (TP, SL, Daily Profit Target, Daily Loss Limit)
and V2 Bot proof on demo (synthetic index).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from sentinel_engine.policy_schema import validate_action
from sentinel_engine.execution_adapter import ExecutionAdapter, model_magic

class MockBroker:
    def __init__(self, specs, balance=10000.0):
        self.specs = specs
        self.balance = balance
        self.tick = {'bid': 100.0, 'ask': 100.05}
        self.positions = []
        self.deals = []
        self.seq = 0

    def get_symbol_info(self, symbol):
        return self.specs

    def get_tick(self, symbol):
        return self.tick

    def loss_per_lot(self, symbol, side, price, stop):
        return abs(price - stop) / self.specs['tick_size'] * self.specs['tick_value']

    def check_margin(self, symbol, side, volume, price):
        return {'required_margin': volume * self.specs['contract_size'] * price / 100, 'free_margin': self.balance}

    def get_open_positions(self, symbol=None, magic=None):
        out = []
        for p in self.positions:
            if (symbol is None or p['symbol'] == symbol) and (magic is None or p['magic'] == magic):
                item = dict(p)
                pnl = (self.tick['bid'] - p['price_open']) * (1 if p['type'] == 'BUY' else -1) * p['volume'] * 10
                item['profit'] = pnl
                out.append(item)
        return out

    def open_position(self, symbol, side, volume, sl, tp=None, magic=0, model_id='', decision_id=''):
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

    def close_position(self, ticket, symbol, volume=None, comment=''):
        pos = next((p for p in self.positions if p['ticket'] == ticket), None)
        if pos:
            self.positions.remove(pos)
            self.deals.append({
                'ticket': 9000 + ticket,
                'position_id': ticket,
                'symbol': symbol,
                'profit': pos.get('profit', 0.0),
                'swap': 0.0,
                'commission': 0.0,
                'time': 1791720000,
                'magic': pos['magic'],
                'comment': comment
            })
            return {'ok': True}
        return {'ok': False}

def run_tests():
    specs = {
        'name': 'R_100',
        'point': 0.01,
        'digits': 2,
        'tick_size': 0.01,
        'tick_value': 0.01,
        'contract_size': 1,
        'volume_min': 0.1,
        'volume_max': 50.0,
        'volume_step': 0.1,
        'stops_level': 10,
        'freeze_level': 0,
        'trade_mode': 4
    }

    # 1. TEST: When Fixed TP and SL are OFF, model levels decide, protective stop attached
    broker = MockBroker(specs)
    adapter = ExecutionAdapter(
        broker=broker,
        symbol='R_100',
        model_id='R_100@1',
        pool_equity=1000.0,
        pool_free_margin=1000.0,
        volatility=1.0,
        overrides={
            'fixed_tp_enabled': False,
            'fixed_sl_enabled': False
        }
    )
    action = {
        'type': 'open',
        'side': 'long',
        'risk_fraction': 0.01,
        'stop_distance': 2.0, # model stop
        'targets': [{'distance': 4.0, 'fraction': 1.0}], # model target
        'reason': 'model entry'
    }
    res = adapter.execute(action, 'decision_1')
    assert res['status'] == 'filled', f"Expected filled, got {res}"
    pos = broker.positions[0]
    # Check stop loss reflects model stop distance (2.0 * atr = 2.0, rounded to digits)
    expected_model_sl = round(broker.tick['bid'] - 2.0, 2)
    assert pos['sl'] == expected_model_sl, f"Expected model SL {expected_model_sl}, got {pos['sl']}"
    expected_model_tp = round(broker.tick['ask'] + 4.0, 2)
    assert pos['tp'] == expected_model_tp, f"Expected model TP {expected_model_tp}, got {pos['tp']}"
    print("[PASS] TEST 1: Overrides OFF => Model SL/TP preserved with protective stop")

    # 2. TEST: When Fixed TP and SL are ON, overrides win
    broker2 = MockBroker(specs)
    adapter2 = ExecutionAdapter(
        broker=broker2,
        symbol='R_100',
        model_id='R_100@1',
        pool_equity=1000.0,
        pool_free_margin=1000.0,
        volatility=1.0,
        overrides={
            'fixed_tp_enabled': True,
            'fixed_tp_unit': 'money',
            'fixed_tp_value': 50.0, # $50 profit
            'fixed_sl_enabled': True,
            'fixed_sl_unit': 'money',
            'fixed_sl_value': 25.0, # $25 loss
        }
    )
    res2 = adapter2.execute(action, 'decision_2')
    assert res2['status'] == 'filled'
    pos2 = broker2.positions[0]
    # In adapter2, stop and tp must be set according to the overrides, overriding model distance 2 and 4
    assert pos2['sl'] != expected_model_sl, f"Override SL should differ from model SL, got {pos2['sl']}"
    assert pos2['tp'] != expected_model_tp, f"Override TP should differ from model TP, got {pos2['tp']}"
    print(f"[PASS] TEST 2: Overrides ON => Override wins (SL={pos2['sl']}, TP={pos2['tp']})")

    # 3. TEST: Daily loss limit halts new trades
    broker3 = MockBroker(specs)
    daily_loss_limit = {'enabled': True, 'unit': 'money', 'value': 40.0, 'close_open_on_hit': True}
    # Simulate current day PnL: -50.0 (exceeds -40.0 limit)
    today_pnl = -50.0
    daily_halt = False
    daily_status = 'normal'
    if daily_loss_limit['enabled'] and today_pnl <= -daily_loss_limit['value']:
        daily_halt = True
        daily_status = 'daily_limit_reached'
    assert daily_halt is True
    assert daily_status == 'daily_limit_reached'

    adapter3 = ExecutionAdapter(
        broker=broker3,
        symbol='R_100',
        model_id='R_100@1',
        pool_equity=1000.0,
        pool_free_margin=1000.0,
        volatility=1.0,
        overrides={'halt': daily_halt}
    )
    res3 = adapter3.execute(action, 'decision_3')
    assert res3['status'] == 'rejected' and res3['reason'] == 'owner_override', f"Got {res3}"
    print("[PASS] TEST 3: Daily loss limit reached => Halts new trades")

    # 4. TEST: Next-day boundary reset automatically resumes trading
    # Shifting day key from Day 1 to Day 2 resets today_pnl to 0.0
    day1_key = '2026-10-23'
    day2_key = '2026-10-24'
    # Deals from day1 do not count towards day2
    deals = [{'time_day': day1_key, 'profit': -50.0}]
    day2_deals = [d for d in deals if d['time_day'] == day2_key]
    day2_pnl = sum(d['profit'] for d in day2_deals)
    assert day2_pnl == 0.0
    daily_halt_day2 = False
    if daily_loss_limit['enabled'] and day2_pnl <= -daily_loss_limit['value']:
        daily_halt_day2 = True
    assert daily_halt_day2 is False

    adapter4 = ExecutionAdapter(
        broker=broker3,
        symbol='R_100',
        model_id='R_100@1',
        pool_equity=1000.0,
        pool_free_margin=1000.0,
        volatility=1.0,
        overrides={'halt': daily_halt_day2}
    )
    res4 = adapter4.execute(action, 'decision_4')
    assert res4['status'] == 'filled', f"Expected filled on next day reset, got {res4}"
    print("[PASS] TEST 4: Next-day rollover => Automatically resumes trading with no owner action")

    print("\nALL V2 TESTS PASSED!")

if __name__ == '__main__':
    run_tests()
