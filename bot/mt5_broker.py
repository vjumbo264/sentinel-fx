"""SENTINEL-FX: MT5 CFD Execution & Broker Layer (bot/mt5_broker.py)

Provides a unified Broker interface for MT5 CFD trading with:
- Abstract BrokerBase interface allowing seamless bridge swap-in if needed
- MT5Broker implementation over mt5linux / RPyC / native MetaTrader5
- Safe credentials handling: mode demo/real, masked status in logs
- Strict safety rules:
    * Server-side Stop Loss ALWAYS required for all opened positions (Never send order without SL)
    * Pre-trade margin & free margin validation
    * Volume rounding to volume_step, clamped between volume_min and volume_max
    * Stops level distance validation (sl/tp distance >= stops_level * point)
    * Filling mode negotiation (FOK, IOC, RETURN based on symbol capability)
    * Magic number and structured comment tag (sfx:<model_id>:<decision_id>) for zero-gap ownership
    * Reconnect with exponential backoff and terminal health watchdog
"""

from __future__ import annotations

import abc
import logging
import math
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("sentinel.broker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class BrokerError(Exception):
    """Base broker error."""
    pass


class OrderValidationError(BrokerError):
    """Raised when an order violates risk or broker specifications."""
    pass


class MarginInsufficientError(BrokerError):
    """Raised when account does not have sufficient margin."""
    pass


class BrokerBase(abc.ABC):
    """Abstract interface for CFD broker operations."""

    @abc.abstractmethod
    def connect(self, mode: str = "demo") -> bool:
        """Connect and log in to broker in 'demo' or 'real' mode."""
        pass

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Return True if connection is alive and authorized."""
        pass

    @abc.abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Perform ping / tick check and return detailed health status."""
        pass

    @abc.abstractmethod
    def account_info(self) -> Dict[str, Any]:
        """Fetch current balance, equity, margin, free margin, and leverage."""
        pass

    @abc.abstractmethod
    def get_symbols(self) -> List[Dict[str, Any]]:
        """Fetch list of tradeable instruments and their specifications."""
        pass

    @abc.abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get specification for a single symbol."""
        pass

    @abc.abstractmethod
    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current live bid/ask/spread tick for symbol."""
        pass

    @abc.abstractmethod
    def is_market_open(self, symbol: str) -> bool:
        """Return True if market is currently open for new orders on symbol."""
        pass

    @abc.abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int = 100) -> List[Dict[str, Any]]:
        """Fetch historical completed candles."""
        pass

    @abc.abstractmethod
    def check_margin(self, symbol: str, action: str, volume: float, price: float) -> Dict[str, Any]:
        """Check required margin and free margin before order dispatch."""
        pass

    @abc.abstractmethod
    def order_check(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        sl: float,
        tp: Optional[float] = None,
        magic: int = 999001,
        comment: str = ""
    ) -> Dict[str, Any]:
        """Dry-run broker order check."""
        pass

    @abc.abstractmethod
    def open_position(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float,
        tp: Optional[float] = None,
        price: Optional[float] = None,
        magic: int = 999001,
        model_id: str = "default",
        decision_id: str = ""
    ) -> Dict[str, Any]:
        """Open a market position with mandatory Stop Loss."""
        pass

    @abc.abstractmethod
    def modify_sl_tp(
        self,
        ticket: int,
        symbol: str,
        sl: float,
        tp: Optional[float] = None
    ) -> Dict[str, Any]:
        """Modify existing position's SL and TP."""
        pass

    @abc.abstractmethod
    def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: Optional[float] = None,
        comment: str = "sfx:close"
    ) -> Dict[str, Any]:
        """Close an open position (full or partial)."""
        pass

    @abc.abstractmethod
    def get_open_positions(
        self,
        symbol: Optional[str] = None,
        magic: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch active open positions, optionally filtered by symbol or magic."""
        pass

    @abc.abstractmethod
    def get_history_deals(
        self,
        since_utc: datetime,
        magic: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch closed trade deals."""
        pass

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Disconnect and free resources."""
        pass


class MT5Broker(BrokerBase):
    """MT5 Python API broker client running over mt5linux / RPyC bridge or native."""

    DEFAULT_MAGIC = 999100

    def __init__(
        self,
        host: str = "localhost",
        port: int = 18812,
        demo_login: Optional[str] = None,
        demo_server: Optional[str] = None,
        real_login: Optional[str] = None,
        real_server: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 60,
    ):
        self.host = host
        self.port = port
        self.demo_login = demo_login or os.environ.get("MT5_DEMO_LOGIN", "41286446")
        self.demo_server = demo_server or os.environ.get("MT5_DEMO_SERVER", "Deriv-Demo")
        self.real_login = real_login or os.environ.get("MT5_REAL_LOGIN", "10357278")
        self.real_server = real_server or os.environ.get("MT5_REAL_SERVER", "DerivSVG-Server")
        self.password = password or os.environ.get("MT5_PASSWORD", "")
        self.timeout = timeout

        self.mode: str = "demo"
        self._mt5: Any = None
        self._conn: Any = None
        self._connected: bool = False
        self._symbols_cache: Dict[str, Any] = {}
        self._last_health_ts: float = 0.0
        self._backend_name: str = "none"

    def _get_api(self):
        """Lazy load and connect to MT5 bridge."""
        if self._mt5 is not None:
            return self._mt5

        # Windows always uses native MT5, never a localhost bridge.
        if os.name == "nt":
            import MetaTrader5 as native_mt5
            self._mt5 = native_mt5
            self._backend_name = "native-windows"
            return self._mt5

        # 1. Attempt RPyC classic connect (primary reliable Linux bridge)
        try:
            import rpyc
            logger.info(f"Connecting to MT5 RPyC bridge at {self.host}:{self.port}...")
            conn = rpyc.classic.connect(self.host, self.port)
            conn._config["sync_request_timeout"] = self.timeout
            try:
                conn.modules.sys.path.append("C:\\mt5libs")
                conn.modules.sys.path.append("C:\\Program Files\\Deriv - MetaTrader 5")
                conn.modules.sys.path.append("C:\\Program Files\\MetaTrader 5")
            except Exception:
                pass
            self._conn = conn
            # Root-cause fix (E2): conn.eval("MetaTrader5.order_send(...)") raised
            # NameError on every call because MetaTrader5 was never imported into
            # the RPyC server's eval global namespace -> all retcodes came back None.
            # Import it remotely once so eval-based order calls resolve correctly.
            try:
                conn.execute("import MetaTrader5")
            except Exception as imp_err:
                logger.warning(f"Remote 'import MetaTrader5' note: {imp_err}")
            self._mt5 = conn.modules.MetaTrader5
            self._backend_name = "rpyc-classic"
            logger.info(f"[MT5Broker] Successfully connected via backend: {self._backend_name} on {self.host}:{self.port}")
            return self._mt5
        except Exception as e:
            logger.debug(f"RPyC connect notice: {e}; trying mt5linux package client")

        # 2. Attempt mt5linux client wrapper
        try:
            from mt5linux import MetaTrader5 as MT5Linux
            logger.info("Initializing connection via mt5linux package client...")
            client = MT5Linux(host=self.host, port=self.port, search_on_init=True, timeout=self.timeout)
            self._mt5 = client
            self._backend_name = "mt5linux-package"
            logger.info(f"[MT5Broker] Successfully connected via backend: {self._backend_name}")
            return self._mt5
        except Exception as e:
            logger.debug(f"mt5linux package init notice: {e}; trying native MetaTrader5")

        # 3. Native MetaTrader5 (when running directly in Windows/Wine)
        try:
            import MetaTrader5 as native_mt5
            self._mt5 = native_mt5
            self._backend_name = "native-windows"
            logger.info(f"[MT5Broker] Connected via backend: {self._backend_name}")
            return self._mt5
        except Exception as e:
            raise RuntimeError(f"Could not connect to any MT5 backend: {e}")

    def _execute_order_check(self, req: Dict[str, Any]) -> Any:
        """Execute order_check ensuring native dictionary types across RPyC boundary."""
        if self._conn:
            try:
                return self._conn.eval(f"MetaTrader5.order_check({req!r})")
            except Exception as e:
                logger.warning(f"RPyC eval order_check fallback: {e}")
                return self._mt5.order_check(req)
        return self._mt5.order_check(req)

    def _execute_order_send(self, req: Dict[str, Any]) -> Any:
        """Execute order_send ensuring native dictionary types across RPyC boundary."""
        if self._conn:
            try:
                return self._conn.eval(f"MetaTrader5.order_send({req!r})")
            except Exception as e:
                logger.warning(f"RPyC eval order_send fallback: {e}")
                return self._mt5.order_send(req)
        return self._mt5.order_send(req)

    def get_server_time_offset_hours(self, symbol: str = "Volatility 10 Index") -> float:
        """Calculate and return MT5 server time offset relative to UTC with sanity checks."""
        mt5 = self._get_api()
        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            server_epoch = int(tick.time) if tick and getattr(tick, "time", 0) > 0 else 0
            if server_epoch <= 0:
                rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, "TIMEFRAME_M1", 1), 0, 1)
                if rates is not None and len(rates) > 0:
                    server_epoch = int(rates[0][0]) if hasattr(rates[0], "__getitem__") else int(rates[0].time)
            if server_epoch > 0:
                now_utc = int(datetime.now(timezone.utc).timestamp())
                raw_diff = server_epoch - now_utc
                # Round to nearest 30 minutes (1800s)
                rounded_diff = round(raw_diff / 1800.0) * 1800
                offset_h = rounded_diff / 3600.0
                if -14.0 <= offset_h <= 14.0:
                    return offset_h
                logger.warning(f"Sanity check rejected offset {offset_h}h (epoch={server_epoch})")
        except Exception as e:
            logger.warning(f"Failed to calculate server time offset: {e}")
        return 0.0

    def connect(self, mode: str = "demo") -> bool:
        """Connect to MT5 terminal and authenticate account."""
        self.mode = mode.lower()
        if self.mode not in ("demo", "real"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'demo' or 'real'.")

        target_login = int(self.demo_login if self.mode == "demo" else self.real_login)
        target_server = self.demo_server if self.mode == "demo" else self.real_server

        logger.info(f"Connecting to MT5 in mode='{self.mode}' on server='{target_server}' (login={target_login})...")

        # Reconnection with backoff
        for attempt in range(1, 4):
            try:
                mt5 = self._get_api()

                # Trigger broker server lookup in container watchdog if rpyc connection is active
                if self._conn:
                    try:
                        self._conn.execute(f'open("C:\\\\server", "w").write("{target_server}")')
                        time.sleep(1)
                    except Exception:
                        pass

                # Initialize
                init_ok = False
                for cfg in [{}, {"server": target_server}, {"login": target_login, "password": self.password, "server": target_server}]:
                    try:
                        if mt5.initialize(**cfg, timeout=10000):
                            init_ok = True
                            break
                    except Exception:
                        continue

                if not init_ok:
                    last_err = mt5.last_error() if hasattr(mt5, "last_error") else "unknown"
                    logger.warning(f"initialize attempt {attempt} returned False (last_err: {last_err})")
                    time.sleep(2 * attempt)
                    continue

                # Login
                login_ok = mt5.login(login=target_login, password=self.password, server=target_server)
                if not login_ok:
                    code, msg = mt5.last_error()
                    logger.warning(f"login failed on server {target_server}: code={code}, msg={msg}")
                    # Try alternative server names for Deriv
                    fallbacks = ["Deriv-Demo", "Deriv.com-Demo", "DerivSVG-Demo"] if self.mode == "demo" else ["DerivSVG-Server", "Deriv-Server"]
                    for fb in fallbacks:
                        if fb != target_server:
                            logger.info(f"Attempting fallback server: {fb}")
                            if mt5.login(login=target_login, password=self.password, server=fb):
                                login_ok = True
                                target_server = fb
                                break

                if login_ok:
                    self._connected = True
                    acct = mt5.account_info()
                    bal = getattr(acct, "balance", 0.0)
                    cur = getattr(acct, "currency", "USD")
                    lev = getattr(acct, "leverage", 100)
                    mode_val = getattr(acct, "margin_mode", 0)
                    mode_str = "HEDGING" if mode_val == 2 else "NETTING"
                    logger.info(f"MT5 Connected successfully! Server={target_server}, Balance={cur} {bal:.2f}, Lev=1:{lev}, MarginMode={mode_str}")
                    return True
                else:
                    logger.warning(f"Login failed on attempt {attempt}: {mt5.last_error()}")

            except Exception as e:
                logger.warning(f"Connection exception on attempt {attempt}: {e}")
                self._mt5 = None
                self._conn = None

            time.sleep(attempt * 2 + random.uniform(0.5, 1.5))

        self._connected = False
        return False

    def is_connected(self) -> bool:
        if not self._connected or self._mt5 is None:
            return False
        try:
            term = self._mt5.terminal_info()
            return bool(term and getattr(term, "connected", False))
        except Exception:
            return False

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of MT5 terminal and account."""
        mt5 = self._get_api()
        try:
            term = mt5.terminal_info()
            acct = mt5.account_info()
            connected = bool(term and getattr(term, "connected", False))
            trade_allowed = bool(acct and getattr(acct, "trade_allowed", False) and term and getattr(term, "trade_allowed", False))
            trade_expert = bool(acct and getattr(acct, "trade_expert", False))
            balance = float(getattr(acct, "balance", 0.0)) if acct else 0.0
            equity = float(getattr(acct, "equity", 0.0)) if acct else 0.0
            free_margin = float(getattr(acct, "margin_free", 0.0)) if acct else 0.0

            # Ping tick on EURUSD or Volatility 10 Index
            ping_sym = "EURUSD"
            tick = mt5.symbol_info_tick(ping_sym)
            if not tick:
                ping_sym = "Volatility 10 Index"
                tick = mt5.symbol_info_tick(ping_sym)

            self._last_health_ts = time.time()
            return {
                "ok": connected and trade_allowed,
                "connected": connected,
                "trade_allowed": trade_allowed,
                "trade_expert": trade_expert,
                "balance": balance,
                "equity": equity,
                "free_margin": free_margin,
                "ping_symbol": ping_sym,
                "ping_bid": float(getattr(tick, "bid", 0.0)) if tick else None,
                "ping_ask": float(getattr(tick, "ask", 0.0)) if tick else None,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            }

    def account_info(self) -> Dict[str, Any]:
        mt5 = self._get_api()
        acct = mt5.account_info()
        if not acct:
            raise BrokerError(f"account_info failed: {mt5.last_error()}")
        margin_mode = "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING" if getattr(acct, "margin_mode", 0) == 2 else "ACCOUNT_MARGIN_MODE_RETAIL_NETTING"
        return {
            "login": int(getattr(acct, "login", 0)),
            "server": str(getattr(acct, "server", "")),
            "currency": str(getattr(acct, "currency", "USD")),
            "balance": float(getattr(acct, "balance", 0.0)),
            "equity": float(getattr(acct, "equity", 0.0)),
            "profit": float(getattr(acct, "profit", 0.0)),
            "margin": float(getattr(acct, "margin", 0.0)),
            "margin_free": float(getattr(acct, "margin_free", 0.0)),
            "margin_level": float(getattr(acct, "margin_level", 0.0)),
            "leverage": int(getattr(acct, "leverage", 100)),
            "margin_mode": margin_mode,
            "trade_allowed": bool(getattr(acct, "trade_allowed", False)),
            "trade_expert": bool(getattr(acct, "trade_expert", False))
        }

    def get_symbols(self) -> List[Dict[str, Any]]:
        mt5 = self._get_api()
        syms = mt5.symbols_get() or []
        out = []
        for s in syms:
            out.append({
                "name": str(s.name),
                "digits": int(s.digits),
                "point": float(s.point),
                "contract_size": float(s.trade_contract_size),
                "volume_min": float(s.volume_min),
                "volume_max": float(s.volume_max),
                "volume_step": float(s.volume_step),
                "stops_level": int(s.trade_stops_level),
                "spread": int(s.spread),
                "swap_long": float(s.swap_long),
                "swap_short": float(s.swap_short),
                "filling_mode": int(getattr(s, "filling_mode", 0)),
                "path": str(getattr(s, "path", ""))
            })
        return out

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if symbol in self._symbols_cache:
            return self._symbols_cache[symbol]
        mt5 = self._get_api()
        s = mt5.symbol_info(symbol)
        if not s:
            return None
        info = {
            "name": str(s.name),
            "digits": int(s.digits),
            "point": float(s.point),
            "contract_size": float(s.trade_contract_size),
            "tick_size": float(s.trade_tick_size),
            "tick_value": float(s.trade_tick_value),
            "freeze_level": int(s.trade_freeze_level),
            "volume_min": float(s.volume_min),
            "volume_max": float(s.volume_max),
            "volume_step": float(s.volume_step),
            "stops_level": int(s.trade_stops_level),
            "spread": int(s.spread),
            "swap_long": float(s.swap_long),
            "swap_short": float(s.swap_short),
            "filling_mode": int(getattr(s, "filling_mode", 0)),
            "trade_mode": int(getattr(s, "trade_mode", 4)),
            "ask": float(getattr(s, "ask", 0.0)),
            "bid": float(getattr(s, "bid", 0.0))
        }
        self._symbols_cache[symbol] = info
        return info

    def is_market_open(self, symbol: str) -> bool:
        """Check if trading session is currently open for symbol using broker specifications."""
        if hasattr(self, '_test_market_closed') and symbol in self._test_market_closed:
            return not self._test_market_closed[symbol]

        info = self.get_symbol_info(symbol)
        if not info:
            return False
        # MT5 SYMBOL_TRADE_MODE_DISABLED is 0
        if info.get('trade_mode') == 0:
            return False

        # Deriv synthetics trade 24/7
        is_synthetic = any(symbol.startswith(p) for p in ['Volatility', '1HZ', 'R_']) or 'Index' in symbol
        if is_synthetic:
            return True

        # Check broker trading sessions if available
        try:
            mt5 = self._get_api()
            now_dt = datetime.now(timezone.utc)
            dow = now_dt.weekday()
            if hasattr(mt5, 'symbol_info_session_trade'):
                has_sessions = False
                in_session = False
                sec_of_day = (now_dt.hour * 3600 + now_dt.minute * 60 + now_dt.second)
                for s_idx in range(5):
                    sess = mt5.symbol_info_session_trade(symbol, dow, s_idx)
                    if sess is not None and getattr(sess, 'open', None) is not None:
                        has_sessions = True
                        if int(sess.open) <= sec_of_day <= int(sess.close):
                            in_session = True
                            break
                if has_sessions and not in_session:
                    return False
        except Exception:
            pass

        return True

    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        mt5 = self._get_api()
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return None
        return {
            "symbol": symbol,
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "time": int(tick.time),
            "time_msc": int(getattr(tick, "time_msc", tick.time * 1000)),
            "spread": float(round(tick.ask - tick.bid, 5))
        }

    def get_candles(self, symbol: str, timeframe: str = "M1", count: int = 100) -> List[Dict[str, Any]]:
        mt5 = self._get_api()
        mt5.symbol_select(symbol, True)
        tf_map = {
            "M1": getattr(mt5, "TIMEFRAME_M1", 1),
            "M5": getattr(mt5, "TIMEFRAME_M5", 5),
            "M15": getattr(mt5, "TIMEFRAME_M15", 15),
            "M30": getattr(mt5, "TIMEFRAME_M30", 30),
            "H1": getattr(mt5, "TIMEFRAME_H1", 60),
            "H4": getattr(mt5, "TIMEFRAME_H4", 240),
            "D1": getattr(mt5, "TIMEFRAME_D1", 1440),
        }
        tf_code = tf_map.get(timeframe.upper(), getattr(mt5, "TIMEFRAME_M1", 1))
        rates = mt5.copy_rates_from_pos(symbol, tf_code, 1, count)
        if rates is None or len(rates) == 0:
            return []

        out = []
        for r in rates:
            if hasattr(r, "time"):
                out.append({
                    "epoch": int(r.time),
                    "time": int(r.time),
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "tick_volume": int(r.tick_volume),
                    "spread": int(getattr(r, "spread", 0))
                })
            else:
                out.append({
                    "epoch": int(r[0]),
                    "time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "tick_volume": int(r[5]),
                    "spread": int(r[6]) if len(r) > 6 else 0
                })
        return out

    def loss_per_lot(self, symbol, side, price, stop):
        api=self._get_api();order_type=0 if side=='BUY' else 1
        if self._conn:
            result=self._conn.eval(f"MetaTrader5.order_calc_profit({order_type}, {symbol!r}, 1.0, {float(price)}, {float(stop)})")
        else:result=api.order_calc_profit(order_type,symbol,1.0,float(price),float(stop))
        if result is None:raise BrokerError('native loss conversion unavailable')
        return abs(float(result))

    def check_margin(self, symbol: str, action: str, volume: float, price: float) -> Dict[str, Any]:
        mt5 = self._get_api()
        acct = self.account_info()
        order_type = getattr(mt5, "ORDER_TYPE_BUY", 0) if action.upper() == "BUY" else getattr(mt5, "ORDER_TYPE_SELL", 1)
        req_margin = mt5.order_calc_margin(order_type, symbol, volume, price)
        if req_margin is None:
            # Fallback approximate formula: (volume * contract_size * price) / leverage
            sinfo = self.get_symbol_info(symbol)
            csize = sinfo["contract_size"] if sinfo else 100000.0
            lev = acct["leverage"] or 100
            req_margin = (volume * csize * price) / lev

        free = acct["margin_free"]
        return {
            "required_margin": float(req_margin),
            "free_margin": float(free),
            "sufficient": free > req_margin,
            "margin_level_after": float((acct["equity"] / (acct["margin"] + req_margin)) * 100.0) if (acct["margin"] + req_margin) > 0 else 999.0
        }

    def _determine_filling(self, symbol_info: Dict[str, Any]) -> int:
        """Choose allowed order filling mode."""
        mt5 = self._get_api()
        mode = symbol_info.get("filling_mode", 0)
        if mode & 2:
            return getattr(mt5, "ORDER_FILLING_IOC", 1)
        elif mode & 1:
            return getattr(mt5, "ORDER_FILLING_FOK", 0)
        else:
            return getattr(mt5, "ORDER_FILLING_RETURN", 2)

    def _round_volume(self, volume: float, symbol_info: Dict[str, Any]) -> float:
        """Round volume strictly to symbol volume_step within [volume_min, volume_max]."""
        vmin = symbol_info["volume_min"]
        vmax = symbol_info["volume_max"]
        vstep = symbol_info["volume_step"]
        if volume < vmin:
            raise OrderValidationError(f"Requested volume {volume} is below minimum {vmin}")
        if volume > vmax:
            volume = vmax

        steps = round((volume - vmin) / vstep)
        rounded = round(vmin + steps * vstep, 6)
        if rounded > vmax:
            rounded = vmax
        return rounded

    def order_check(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        sl: float,
        tp: Optional[float] = None,
        magic: int = 999001,
        comment: str = ""
    ) -> Dict[str, Any]:
        """Dry-run order check against MT5 broker."""
        if not sl or sl <= 0:
            raise OrderValidationError("SERVER-SIDE STOP LOSS IS STRICTLY MANDATORY! Every order must specify SL > 0.")

        mt5 = self._get_api()
        sinfo = self.get_symbol_info(symbol)
        if not sinfo:
            raise OrderValidationError(f"Unknown symbol: {symbol}")

        vol = self._round_volume(volume, sinfo)
        order_type = getattr(mt5, "ORDER_TYPE_BUY", 0) if side.upper() == "BUY" else getattr(mt5, "ORDER_TYPE_SELL", 1)
        filling = self._determine_filling(sinfo)

        req = {
            "action": int(getattr(mt5, "TRADE_ACTION_DEAL", 1)),
            "symbol": str(symbol),
            "volume": float(vol),
            "type": int(order_type),
            "price": float(price),
            "sl": float(sl),
            "deviation": 20,
            "magic": int(magic),
            "comment": str(comment[:31]),
            "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
            "type_filling": int(filling)
        }
        if tp and tp > 0:
            req["tp"] = float(tp)

        check_res = self._execute_order_check(req)
        retcode = getattr(check_res, "retcode", None)
        comment_res = getattr(check_res, "comment", "")
        free_m = getattr(check_res, "margin_free", None)

        return {
            "retcode": retcode,
            "ok": retcode == 0,
            "comment": comment_res,
            "margin_free": float(free_m) if free_m is not None else None,
            "volume": vol,
            "sl": sl,
            "tp": tp
        }

    def open_position(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float,
        tp: Optional[float] = None,
        price: Optional[float] = None,
        magic: int = 999100,
        model_id: str = "default",
        decision_id: str = ""
    ) -> Dict[str, Any]:
        """Open CFD position with guaranteed server-side stop loss."""
        # 1. HARD RULE: SL must exist
        if not sl or sl <= 0:
            raise OrderValidationError("CRITICAL SAFETY VIOLATION: Position rejected because SL is missing or zero.")

        mt5 = self._get_api()
        sinfo = self.get_symbol_info(symbol)
        if not sinfo:
            raise OrderValidationError(f"Symbol {symbol} not found on broker")

        vol = self._round_volume(volume, sinfo)
        tick = self.get_tick(symbol)
        if not tick:
            raise BrokerError(f"Could not fetch tick for {symbol}")

        is_buy = side.upper() == "BUY"
        exec_price = float(price or (tick["ask"] if is_buy else tick["bid"]))

        # Check stops level distance
        min_dist = sinfo["stops_level"] * sinfo["point"]
        if is_buy and (exec_price - sl) < min_dist:
            sl = round(exec_price - max(min_dist, 50 * sinfo["point"]), sinfo["digits"])
        elif (not is_buy) and (sl - exec_price) < min_dist:
            sl = round(exec_price + max(min_dist, 50 * sinfo["point"]), sinfo["digits"])

        # Check margin
        margin_check = self.check_margin(symbol, side, vol, exec_price)
        if not margin_check["sufficient"]:
            raise MarginInsufficientError(
                f"Insufficient free margin: need {margin_check['required_margin']:.2f}, free {margin_check['free_margin']:.2f}"
            )

        filling = self._determine_filling(sinfo)
        order_type = getattr(mt5, "ORDER_TYPE_BUY", 0) if is_buy else getattr(mt5, "ORDER_TYPE_SELL", 1)

        # Construct structured comment tag for zero-gap ownership survival
        tag = f"sfx:{model_id[:8]}:{decision_id[:8]}" if decision_id else f"sfx:{model_id[:12]}"
        tag = tag[:31]

        req = {
            "action": int(getattr(mt5, "TRADE_ACTION_DEAL", 1)),
            "symbol": str(symbol),
            "volume": float(vol),
            "type": int(order_type),
            "price": float(exec_price),
            "sl": float(sl),
            "deviation": 25,
            "magic": int(magic),
            "comment": tag,
            "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
            "type_filling": int(filling)
        }
        if tp and tp > 0:
            req["tp"] = float(tp)

        logger.info(f"Dispatching order_send: {side} {vol} {symbol} @ {exec_price} [SL: {sl}, TP: {tp}, Magic: {magic}, Tag: {tag}]")
        res = self._execute_order_send(req)

        retcode = getattr(res, "retcode", None)
        deal = getattr(res, "deal", 0)
        order = getattr(res, "order", 0)
        res_comment = getattr(res, "comment", "")

        if retcode != 10009 and retcode != 10008:  # 10009 = TRADE_RETCODE_DONE, 10008 = TRADE_RETCODE_PLACED
            logger.error(f"Order failed: retcode={retcode} ({res_comment})")
            raise BrokerError(f"order_send failed: retcode={retcode} ({res_comment})")

        logger.info(f"[SUCCESS] Position opened: order={order}, deal={deal}, price={exec_price}")
        return {
            "ok": True,
            "order": order,
            "ticket": order,
            "deal": deal,
            "symbol": symbol,
            "side": side.upper(),
            "volume": vol,
            "price": exec_price,
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": tag,
            "retcode": retcode
        }

    def modify_sl_tp(self, ticket: int, symbol: str, sl: float, tp: Optional[float] = None) -> Dict[str, Any]:
        """Modify existing position SL and TP."""
        if not sl or sl <= 0:
            raise OrderValidationError("SL modification cannot remove Stop Loss; SL must be > 0.")

        mt5 = self._get_api()
        sinfo = self.get_symbol_info(symbol)
        digits = sinfo["digits"] if sinfo else 5

        req = {
            "action": int(getattr(mt5, "TRADE_ACTION_SLTP", 6)),
            "position": int(ticket),
            "symbol": str(symbol),
            "sl": float(round(sl, digits)),
        }
        if tp is not None and tp > 0:
            req["tp"] = float(round(tp, digits))

        logger.info(f"Modifying position #{ticket} ({symbol}) -> new SL: {sl}, TP: {tp}")
        res = self._execute_order_send(req)
        retcode = getattr(res, "retcode", None)
        if retcode != 10009:
            logger.warning(f"Modify SL/TP returned retcode={retcode}: {getattr(res, 'comment', '')}")
        return {
            "ok": retcode == 10009,
            "retcode": retcode,
            "ticket": ticket,
            "sl": sl,
            "tp": tp
        }

    def close_position(self, ticket: int, symbol: str, volume: Optional[float] = None, comment: str = "sfx:close") -> Dict[str, Any]:
        """Close position either fully or partially."""
        mt5 = self._get_api()
        positions = mt5.positions_get(ticket=ticket) or []
        if not positions:
            # Fallback search by symbol
            all_pos = mt5.positions_get(symbol=symbol) or []
            for p in all_pos:
                if int(p.ticket) == ticket:
                    positions = [p]
                    break

        if not positions:
            raise BrokerError(f"Position #{ticket} on {symbol} not found to close")

        pos = positions[0]
        pos_vol = float(pos.volume)
        close_vol = float(volume) if volume and volume > 0 and volume <= pos_vol else pos_vol
        is_buy = int(pos.type) == getattr(mt5, "ORDER_TYPE_BUY", 0)

        tick = self.get_tick(symbol)
        close_price = tick["bid"] if is_buy else tick["ask"]
        close_type = getattr(mt5, "ORDER_TYPE_SELL", 1) if is_buy else getattr(mt5, "ORDER_TYPE_BUY", 0)

        sinfo = self.get_symbol_info(symbol)
        filling = self._determine_filling(sinfo) if sinfo else 0

        req = {
            "action": int(getattr(mt5, "TRADE_ACTION_DEAL", 1)),
            "symbol": str(symbol),
            "volume": float(close_vol),
            "type": int(close_type),
            "position": int(ticket),
            "price": float(close_price),
            "deviation": 25,
            "magic": int(getattr(pos, "magic", self.DEFAULT_MAGIC)),
            "comment": comment[:31],
            "type_time": int(getattr(mt5, "ORDER_TIME_GTC", 0)),
            "type_filling": int(filling)
        }

        logger.info(f"Closing position #{ticket}: volume={close_vol}, price={close_price}")
        res = self._execute_order_send(req)
        retcode = getattr(res, "retcode", None)
        deal = getattr(res, "deal", 0)

        return {
            "ok": retcode == 10009,
            "retcode": retcode,
            "ticket": ticket,
            "deal": deal,
            "volume_closed": close_vol,
            "price": close_price
        }

    def get_open_positions(self, symbol: Optional[str] = None, magic: Optional[int] = None) -> List[Dict[str, Any]]:
        mt5 = self._get_api()
        if symbol:
            raw = mt5.positions_get(symbol=symbol) or []
        else:
            raw = mt5.positions_get() or []

        out = []
        for p in raw:
            p_magic = int(getattr(p, "magic", 0))
            if magic is not None and p_magic != magic:
                continue

            out.append({
                "ticket": int(p.ticket),
                "symbol": str(p.symbol),
                "type": "BUY" if int(p.type) == 0 else "SELL",
                "volume": float(p.volume),
                "price_open": float(p.price_open),
                "price_current": float(p.price_current),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "profit": float(p.profit),
                "swap": float(getattr(p, "swap", 0.0)),
                "time": int(p.time),
                "magic": p_magic,
                "comment": str(getattr(p, "comment", ""))
            })
        return out

    def get_history_deals(self, since_utc: datetime, magic: Optional[int] = None) -> List[Dict[str, Any]]:
        mt5 = self._get_api()
        start = int(since_utc.timestamp())
        end = int(datetime.now(timezone.utc).timestamp()) + 60
        if self._conn:
            deals = self._conn.eval(f"MetaTrader5.history_deals_get({start}, {end})")
        else:
            deals = mt5.history_deals_get(start, end)
        if deals is None:
            raise BrokerError(f"history_deals_get failed: {mt5.last_error()}")
        out = []
        for d in deals:
            d_magic = int(getattr(d, "magic", 0))
            if magic is not None and d_magic != magic:
                continue
            out.append({
                "ticket": int(d.ticket),
                "order": int(d.order),
                "time": int(d.time),
                "type": int(d.type),
                "entry": int(d.entry),
                "magic": d_magic,
                "position_id": int(getattr(d, "position_id", 0)),
                "volume": float(d.volume),
                "price": float(d.price),
                "commission": float(getattr(d, "commission", 0.0)),
                "swap": float(getattr(d, "swap", 0.0)),
                "profit": float(d.profit),
                "fee": float(getattr(d, "fee", 0.0)),
                "symbol": str(d.symbol),
                "comment": str(getattr(d, "comment", ""))
            })
        return out

    def disconnect(self) -> None:
        try:
            if self._mt5 and hasattr(self._mt5, "shutdown"):
                self._mt5.shutdown()
        except Exception:
            pass
        self._connected = False
        self._mt5 = None
        self._conn = None
        logger.info("MT5 disconnected.")
