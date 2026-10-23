"""Tests for bot/mt5_broker.py: MT5 CFD Execution Layer & Safety Invariants."""

import pytest
from bot.mt5_broker import (
    MT5Broker,
    BrokerBase,
    BrokerError,
    OrderValidationError,
    MarginInsufficientError,
)


class MockMT5Backend:
    """Mock implementation of MetaTrader5 Python API."""
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2

    def __init__(self):
        self.init_calls = 0
        self.login_calls = 0

    def initialize(self, *args, **kwargs):
        self.init_calls += 1
        return True

    def login(self, login, password, server):
        self.login_calls += 1
        return True

    def terminal_info(self):
        class Info:
            connected = True
            trade_allowed = True
            trade_expert = True
        return Info()

    def account_info(self):
        class Acct:
            login = 41286446
            server = "Deriv-Demo"
            currency = "USD"
            balance = 10000.0
            equity = 10000.0
            profit = 0.0
            margin = 0.0
            margin_free = 10000.0
            margin_level = 999.0
            leverage = 1000
            margin_mode = 2  # Hedging
            trade_allowed = True
            trade_expert = True
        return Acct()

    def symbol_info(self, symbol):
        class SInfo:
            name = symbol
            digits = 5 if "EUR" in symbol else 3
            point = 0.00001 if "EUR" in symbol else 0.001
            trade_contract_size = 100000.0 if "EUR" in symbol else 1.0
            trade_tick_size = point
            trade_tick_value = 1.0
            trade_freeze_level = 0
            volume_min = 0.01
            volume_max = 50.0
            volume_step = 0.01
            trade_stops_level = 20
            spread = 15
            swap_long = -5.0
            swap_short = 2.0
            filling_mode = 2  # IOC
            ask = 1.08500
            bid = 1.08485
        return SInfo()

    def symbol_select(self, symbol, enable):
        return True

    def symbol_info_tick(self, symbol):
        class Tick:
            bid = 1.08485
            ask = 1.08500
            time = 1700000000
            time_msc = 1700000000000
        return Tick()

    def order_calc_margin(self, action, symbol, volume, price):
        return (volume * 100000.0 * price) / 1000.0

    def order_check(self, req):
        class CheckRes:
            retcode = 0
            comment = "Done"
            margin_free = 9800.0
        return CheckRes()

    def order_send(self, req):
        class SendRes:
            retcode = 10009  # TRADE_RETCODE_DONE
            order = 123456
            deal = 789012
            volume = req["volume"]
            price = req["price"]
            comment = req.get("comment", "")
        return SendRes()

    def positions_get(self, *args, **kwargs):
        return ()

    def history_deals_get(self, *args, **kwargs):
        return ()

    def last_error(self):
        return (0, "Success")


def test_mandatory_stop_loss_on_order_check():
    broker = MT5Broker()
    broker._mt5 = MockMT5Backend()
    broker._connected = True

    # Order without SL MUST raise OrderValidationError
    with pytest.raises(OrderValidationError) as excinfo:
        broker.order_check(
            symbol="EURUSD",
            side="BUY",
            volume=0.1,
            price=1.0850,
            sl=0.0  # Missing SL
        )
    assert "SERVER-SIDE STOP LOSS IS STRICTLY MANDATORY" in str(excinfo.value)


def test_mandatory_stop_loss_on_open_position():
    broker = MT5Broker()
    broker._mt5 = MockMT5Backend()
    broker._connected = True

    with pytest.raises(OrderValidationError) as excinfo:
        broker.open_position(
            symbol="EURUSD",
            side="BUY",
            volume=0.1,
            sl=0.0
        )
    assert "SL is missing" in str(excinfo.value) or "MANDATORY" in str(excinfo.value)


def test_volume_rounding_and_clamping():
    broker = MT5Broker()
    sinfo = {
        "volume_min": 0.01,
        "volume_max": 10.0,
        "volume_step": 0.01
    }
    # Below min raises
    with pytest.raises(OrderValidationError):
        broker._round_volume(0.005, sinfo)

    # Normal step round
    assert broker._round_volume(0.024, sinfo) == 0.02
    assert broker._round_volume(0.026, sinfo) == 0.03

    # Clamping at max
    assert broker._round_volume(15.0, sinfo) == 10.0


def test_successful_order_check_and_open():
    broker = MT5Broker()
    broker._mt5 = MockMT5Backend()
    broker._connected = True

    check = broker.order_check(
        symbol="EURUSD",
        side="BUY",
        volume=0.01,
        price=1.08500,
        sl=1.08200,
        tp=1.08900
    )
    assert check["ok"] is True
    assert check["retcode"] == 0
    assert check["sl"] == 1.08200

    deal = broker.open_position(
        symbol="EURUSD",
        side="BUY",
        volume=0.01,
        sl=1.08200,
        tp=1.08900,
        model_id="eurusd_v2"
    )
    assert deal["ticket"] == 123456
    assert deal["deal"] == 789012
    assert deal["sl"] == 1.08200
    assert "sfx:eurusd_v2" in deal["comment"]


def test_windows_selects_native_without_importing_bridges(monkeypatch):
    import sys
    import types
    import bot.mt5_broker as module
    native = types.ModuleType("MetaTrader5")
    monkeypatch.setitem(sys.modules, "MetaTrader5", native)
    monkeypatch.setattr(module.os, "name", "nt")
    broker = MT5Broker()
    assert broker._get_api() is native
    assert broker._backend_name == "native-windows"
