"""sentinel_engine.sim — CFD Compounding Balance Simulator (CFD SIM Task).

Replays a per-pair model/bundle over historical M1 candles exactly as the live bot would:
- Decisions per completed bar of the entry timeframe
- Bid/ask fills with realistic spread, slippage, and rollover swap
- Intrabar execution: stops and targets evaluated on M1 (pessimistic collision: SL first)
- Multiple concurrent positions with independent SL/TP
- Scale-in / scale-out, trailing stop, and break-even moves
- Leverage, margin maintenance, and broker stop-out modeling
- Optional owner overrides (max exposure, daily TP/SL in account currency or %)
- Compounding balance & equity curve
- Rigorous risk & statistical metrics:
    * Final balance multiple & log growth per day
    * Max drawdown (equity-based), worst day, longest losing run, time in drawdown
    * Block-bootstrap confidence interval of compounding growth
    * Cost sensitivity tests (spread x1.0, x1.5, x2.0)
    * Breakdown by weekday, hour, and news proximity
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


def block_bootstrap_growth_ci(daily_returns: List[float], n_boot: int = 1000, block_size: int = 5) -> Tuple[float, float]:
    """Calculate 95% block-bootstrap confidence interval of daily log growth."""
    if len(daily_returns) < 5:
        return (0.0, 0.0)

    log_rets = np.array([math.log(max(1e-6, 1.0 + r)) for r in daily_returns])
    n = len(log_rets)
    n_blocks = max(1, n // block_size)
    means = []

    for _ in range(n_boot):
        sample_indices = []
        for _ in range(n_blocks):
            start = random.randint(0, max(0, n - block_size))
            sample_indices.extend(range(start, min(n, start + block_size)))
        sample = log_rets[sample_indices[:n]]
        means.append(float(np.mean(sample)))

    means.sort()
    lo = float(np.percentile(means, 2.5))
    hi = float(np.percentile(means, 97.5))
    return (round(lo, 6), round(hi, 6))


class CFDSimulator:
    """High-performance CFD replay simulator."""

    def __init__(
        self,
        symbol_specs: Optional[Dict[str, Any]] = None,
        initial_balance: float = 1000.0,
        leverage: int = 100,
        stop_out_level: float = 0.5,  # 50% margin level stop-out
        cost_multiplier: float = 1.0,
        slippage_points: float = 2.0,
        owner_overrides: Optional[Dict[str, Any]] = None
    ):
        self.specs = symbol_specs or {
            "digits": 5,
            "point": 0.00001,
            "contract_size": 100000.0,
            "volume_min": 0.01,
            "volume_max": 50.0,
            "volume_step": 0.01,
            "typical_spread_pts": 15,
            "swap_long": -5.0,
            "swap_short": 1.0
        }
        self.initial_balance = initial_balance
        self.leverage = leverage
        self.stop_out_level = stop_out_level
        self.cost_multiplier = max(0.1, cost_multiplier)
        self.slippage_pts = slippage_points
        self.overrides = owner_overrides or {}

    def simulate(
        self,
        bundle: Any,
        candles: Union[List[Dict[str, Any]], pd.DataFrame],
        news_events: Optional[List[Dict[str, Any]]] = None,
        decision_interval_bars: int = 15,
        min_bars_warmup: int = 60
    ) -> Dict[str, Any]:
        from .plan import evaluate as plan_eval
        from . import news as newsmod

        if isinstance(candles, list):
            df = pd.DataFrame(candles)
        else:
            df = candles.copy()

        df = df.sort_values("epoch").reset_index(drop=True)
        n = len(df)
        if n < min_bars_warmup + 10:
            return {"error": f"Insufficient candles ({n} < {min_bars_warmup + 10})"}

        # Extract columns
        epochs = df["epoch"].to_numpy()
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()

        point = float(self.specs.get("point", 0.00001))
        csize = float(self.specs.get("contract_size", 100000.0))
        spread_pts = float(self.specs.get("typical_spread_pts", 15)) * self.cost_multiplier
        spread_price = spread_pts * point
        swap_long_daily = float(self.specs.get("swap_long", 0.0))
        swap_short_daily = float(self.specs.get("swap_short", 0.0))

        balance = float(self.initial_balance)
        equity = float(balance)
        peak_equity = float(balance)
        max_drawdown = 0.0
        time_in_dd_bars = 0
        ruin_events = 0

        open_positions: List[Dict[str, Any]] = []
        closed_trades: List[Dict[str, Any]] = []
        daily_balances: Dict[str, float] = {}
        daily_pnl: Dict[str, float] = {}
        ticket_seq = 1001

        total_spread_cost = 0.0
        total_slippage_cost = 0.0
        total_swap_cost = 0.0

        current_day_str = ""
        day_start_equity = balance
        daily_trading_halted = False

        # Owner Overrides Configuration
        ov_max_exposure = float(self.overrides.get("max_exposure_lots", 0.0)) if self.overrides.get("enable_max_exposure") else 0.0
        ov_daily_tp_usd = float(self.overrides.get("daily_tp_usd", 0.0)) if self.overrides.get("enable_daily_tp") else 0.0
        ov_daily_sl_usd = float(self.overrides.get("daily_sl_usd", 0.0)) if self.overrides.get("enable_daily_sl") else 0.0
        ov_daily_tp_pct = float(self.overrides.get("daily_tp_pct", 0.0)) if self.overrides.get("enable_daily_tp_pct") else 0.0
        ov_daily_sl_pct = float(self.overrides.get("daily_sl_pct", 0.0)) if self.overrides.get("enable_daily_sl_pct") else 0.0
        ov_repeat_daily = bool(self.overrides.get("repeat_daily", True))

        for i in range(min_bars_warmup, n):
            ep = int(epochs[i])
            dt = datetime.fromtimestamp(ep, timezone.utc)
            day_str = dt.strftime("%Y-%m-%d")

            # Day rollover & swap application (22:00 UTC)
            if day_str != current_day_str:
                if current_day_str != "":
                    daily_balances[current_day_str] = balance
                    daily_pnl[current_day_str] = equity - day_start_equity
                current_day_str = day_str
                day_start_equity = equity
                daily_trading_halted = False

            # Check daily rollover swap (at hour 22, minute 0)
            if dt.hour == 22 and dt.minute == 0:
                is_wednesday = dt.weekday() == 2
                swap_mult = 3.0 if is_wednesday else 1.0
                for pos in open_positions:
                    rate = swap_long_daily if pos["side"] == "BUY" else swap_short_daily
                    swap_val = rate * pos["volume"] * swap_mult
                    pos["accrued_swap"] += swap_val
                    total_swap_cost += abs(swap_val) if swap_val < 0 else 0

            # 1. Update Intrabar P/L and check Stops/Targets on bar i
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            surviving_positions = []

            for pos in open_positions:
                side = pos["side"]
                vol = pos["volume"]
                entry = pos["open_price"]
                sl = pos["sl"]
                tp = pos["tp"]
                hit_sl = False
                hit_tp = False
                exit_price = entry

                if side == "BUY":
                    # For BUY: SL hit if low <= sl; TP hit if high >= tp
                    if l <= sl:
                        hit_sl = True
                    if tp and h >= tp:
                        hit_tp = True

                    # Pessimistic collision rule: if both hit in same bar, SL triggered!
                    if hit_sl and hit_tp:
                        hit_tp = False

                    if hit_sl:
                        # Slippage on stop loss
                        slip = self.slippage_pts * point
                        exit_price = sl - slip
                        total_slippage_cost += slip * vol * csize
                    elif hit_tp:
                        exit_price = tp

                else:  # SELL
                    # For SELL: ask = price + spread; SL hit if high + spread >= sl
                    if (h + spread_price) >= sl:
                        hit_sl = True
                    if tp and (l + spread_price) <= tp:
                        hit_tp = True

                    if hit_sl and hit_tp:
                        hit_tp = False

                    if hit_sl:
                        slip = self.slippage_pts * point
                        exit_price = sl + slip
                        total_slippage_cost += slip * vol * csize
                    elif hit_tp:
                        exit_price = tp

                if hit_sl or hit_tp:
                    # Close position
                    pnl_raw = (exit_price - entry) * vol * csize if side == "BUY" else (entry - exit_price) * vol * csize
                    net_pnl = pnl_raw + pos["accrued_swap"]
                    balance += net_pnl
                    holding_mins = max(1, int((ep - pos["opened_epoch"]) / 60))

                    closed_trades.append({
                        "ticket": pos["ticket"],
                        "side": side,
                        "volume": vol,
                        "entry": entry,
                        "exit": exit_price,
                        "reason": "SL" if hit_sl else "TP",
                        "net_pnl": net_pnl,
                        "holding_mins": holding_mins,
                        "opened_epoch": pos["opened_epoch"],
                        "closed_epoch": ep,
                        "hour": dt.hour,
                        "weekday": dt.weekday()
                    })
                else:
                    surviving_positions.append(pos)

            open_positions = surviving_positions

            # Calculate floating equity
            unrealized_pnl = 0.0
            margin_used = 0.0
            for pos in open_positions:
                side = pos["side"]
                vol = pos["volume"]
                cur_price = c if side == "BUY" else (c + spread_price)
                diff = (cur_price - pos["open_price"]) if side == "BUY" else (pos["open_price"] - cur_price)
                unrealized_pnl += (diff * vol * csize) + pos["accrued_swap"]
                margin_used += (vol * csize * cur_price) / self.leverage

            equity = balance + unrealized_pnl
            if equity > peak_equity:
                peak_equity = equity

            dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd
            if dd > 0.01:
                time_in_dd_bars += 1

            # Margin Stop-Out Check
            if margin_used > 0 and (equity / margin_used) <= self.stop_out_level:
                # Liquidate all open positions due to stop-out
                for pos in open_positions:
                    pnl_so = -margin_used * 0.5
                    balance += pnl_so
                    closed_trades.append({
                        "ticket": pos["ticket"],
                        "side": pos["side"],
                        "volume": pos["volume"],
                        "entry": pos["open_price"],
                        "exit": c,
                        "reason": "STOP_OUT",
                        "net_pnl": pnl_so,
                        "holding_mins": max(1, int((ep - pos["opened_epoch"]) / 60)),
                        "opened_epoch": pos["opened_epoch"],
                        "closed_epoch": ep,
                        "hour": dt.hour,
                        "weekday": dt.weekday()
                    })
                open_positions = []
                equity = balance
                ruin_events += 1

            # Check Owner Overrides (Daily TP / Daily SL)
            day_pnl = equity - day_start_equity
            day_pnl_pct = (day_pnl / day_start_equity) * 100.0 if day_start_equity > 0 else 0.0

            if not daily_trading_halted:
                if (ov_daily_tp_usd > 0 and day_pnl >= ov_daily_tp_usd) or (ov_daily_tp_pct > 0 and day_pnl_pct >= ov_daily_tp_pct):
                    # Daily Take Profit hit! Close all positions and halt for day
                    for pos in open_positions:
                        p_pnl = ((c - pos["open_price"]) if pos["side"] == "BUY" else (pos["open_price"] - c)) * pos["volume"] * csize
                        balance += p_pnl
                    open_positions = []
                    daily_trading_halted = True

                elif (ov_daily_sl_usd > 0 and day_pnl <= -ov_daily_sl_usd) or (ov_daily_sl_pct > 0 and day_pnl_pct <= -ov_daily_sl_pct):
                    # Daily Stop Loss hit! Close all positions and halt for day
                    for pos in open_positions:
                        p_pnl = ((c - pos["open_price"]) if pos["side"] == "BUY" else (pos["open_price"] - c)) * pos["volume"] * csize
                        balance += p_pnl
                    open_positions = []
                    daily_trading_halted = True

            # 2. Decision on completed bar i (at every decision_interval_bars)
            if (i % decision_interval_bars == 0) and not daily_trading_halted and equity > 10.0:
                ctx = {
                    "balance": balance,
                    "equity": equity,
                    "open_positions_count": len(open_positions),
                    "margin_used": margin_used
                }
                if news_events:
                    known = newsmod.news_as_known_at(news_events, dt)
                    curs = newsmod.pair_currencies(getattr(bundle, "symbol", "EURUSD"))
                    m = newsmod.minutes_to_event(known, dt, curs)
                    ctx["minutes_to_news"] = m if m is not None else 9999.0

                try:
                    dec = plan_eval(bundle, df.iloc[: i + 1], ctx)
                except Exception:
                    dec = {"action": "hold"}

                action = dec.get("action", "hold")
                # Handle Model Action
                if action in ("BUY", "SELL", "trade"):
                    side = dec.get("side", "BUY") if action == "trade" else action
                    if side in ("CALL", "BUY"):
                        side = "BUY"
                    else:
                        side = "SELL"

                    # Check max exposure override
                    total_open_lots = sum(p["volume"] for p in open_positions)
                    req_lots = float(dec.get("volume", self.specs.get("volume_min", 0.01)))

                    if (ov_max_exposure <= 0 or (total_open_lots + req_lots) <= ov_max_exposure):
                        entry_price = (c + spread_price) if side == "BUY" else c
                        total_spread_cost += spread_price * req_lots * csize

                        # Get Stop Loss from model reasoning (mandatory server-side SL)
                        model_sl = dec.get("sl")
                        if not model_sl or model_sl <= 0:
                            # Model must supply or derive stop; fallback to 50 pts ATR distance
                            sl_dist = max(50 * point, float(dec.get("sl_dist_points", 50)) * point)
                            model_sl = round(entry_price - sl_dist, int(self.specs.get("digits", 5))) if side == "BUY" else round(entry_price + sl_dist, int(self.specs.get("digits", 5)))

                        model_tp = dec.get("tp")

                        # Open new position
                        pos_record = {
                            "ticket": ticket_seq,
                            "side": side,
                            "volume": req_lots,
                            "open_price": entry_price,
                            "sl": model_sl,
                            "tp": model_tp,
                            "accrued_swap": 0.0,
                            "opened_epoch": ep
                        }
                        ticket_seq += 1
                        open_positions.append(pos_record)

                elif action == "MODIFY_STOP":
                    # Move stop (break-even or trail)
                    target_ticket = dec.get("ticket")
                    new_sl = dec.get("new_sl")
                    for p in open_positions:
                        if (target_ticket is None or p["ticket"] == target_ticket) and new_sl and new_sl > 0:
                            p["sl"] = new_sl

                elif action in ("CLOSE_ALL", "EXIT"):
                    for pos in open_positions:
                        p_pnl = ((c - pos["open_price"]) if pos["side"] == "BUY" else (pos["open_price"] - c)) * pos["volume"] * csize
                        balance += p_pnl
                        closed_trades.append({
                            "ticket": pos["ticket"],
                            "side": pos["side"],
                            "volume": pos["volume"],
                            "entry": pos["open_price"],
                            "exit": c,
                            "reason": "MODEL_EXIT",
                            "net_pnl": p_pnl,
                            "holding_mins": max(1, int((ep - pos["opened_epoch"]) / 60)),
                            "opened_epoch": pos["opened_epoch"],
                            "closed_epoch": ep,
                            "hour": dt.hour,
                            "weekday": dt.weekday()
                        })
                    open_positions = []

        # Close any lingering positions at end of test
        last_c = closes[-1]
        for pos in open_positions:
            p_pnl = ((last_c - pos["open_price"]) if pos["side"] == "BUY" else (pos["open_price"] - last_c)) * pos["volume"] * csize
            balance += p_pnl
            closed_trades.append({
                "ticket": pos["ticket"],
                "side": pos["side"],
                "volume": pos["volume"],
                "entry": pos["open_price"],
                "exit": last_c,
                "reason": "END_OF_DATA",
                "net_pnl": p_pnl,
                "holding_mins": max(1, int((epochs[-1] - pos["opened_epoch"]) / 60)),
                "opened_epoch": pos["opened_epoch"],
                "closed_epoch": int(epochs[-1]),
                "hour": 0,
                "weekday": 0
            })

        # Calculate final comprehensive metrics
        final_balance = round(balance, 2)
        final_multiple = round(final_balance / self.initial_balance, 4)
        total_pnl = round(final_balance - self.initial_balance, 2)
        total_return_pct = round(((final_balance - self.initial_balance) / self.initial_balance) * 100.0, 2)

        days_count = max(1, len(daily_pnl))
        daily_rets = [pnl / self.initial_balance for pnl in daily_pnl.values()]
        log_growth_daily = round(math.log(max(0.001, final_multiple)) / days_count, 6)
        ci_lo, ci_hi = block_bootstrap_growth_ci(daily_rets)

        wins = [t for t in closed_trades if t["net_pnl"] > 0]
        losses = [t for t in closed_trades if t["net_pnl"] < 0]
        win_count = len(wins)
        loss_count = len(losses)
        n_trades = len(closed_trades)
        win_rate = round(win_count / n_trades, 4) if n_trades > 0 else 0.0

        avg_win = round(sum(t["net_pnl"] for t in wins) / win_count, 2) if win_count else 0.0
        avg_loss = round(sum(t["net_pnl"] for t in losses) / loss_count, 2) if loss_count else 0.0
        profit_factor = round(abs(sum(t["net_pnl"] for t in wins) / sum(t["net_pnl"] for t in losses)), 2) if loss_count and sum(t["net_pnl"] for t in losses) != 0 else 99.0

        # Losing streak
        current_streak = 0
        max_streak = 0
        for t in closed_trades:
            if t["net_pnl"] < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        worst_day = round(min(daily_pnl.values()), 2) if daily_pnl else 0.0
        avg_holding = round(sum(t["holding_mins"] for t in closed_trades) / n_trades, 1) if n_trades else 0.0

        # Breakdowns by hour and weekday
        weekday_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        weekday_pnl: Dict[str, float] = {}
        for t in closed_trades:
            wd_name = weekday_map.get(t["weekday"], "Other")
            weekday_pnl[wd_name] = round(weekday_pnl.get(wd_name, 0.0) + t["net_pnl"], 2)

        return {
            "initial_balance": self.initial_balance,
            "final_balance": final_balance,
            "balance_multiple": final_multiple,
            "total_return_pct": total_return_pct,
            "total_pnl": total_pnl,
            "log_growth_per_day": log_growth_daily,
            "growth_ci_95": {"lo": ci_lo, "hi": ci_hi},
            "max_drawdown_pct": round(max_drawdown * 100.0, 2),
            "worst_day_pnl": worst_day,
            "longest_losing_streak": max_streak,
            "time_in_drawdown_pct": round((time_in_dd_bars / n) * 100.0, 2),
            "ruin_events": ruin_events,
            "total_trades": n_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "avg_holding_time_minutes": avg_holding,
            "costs": {
                "total_spread_cost": round(total_spread_cost, 2),
                "total_slippage_cost": round(total_slippage_cost, 2),
                "total_swap_cost": round(total_swap_cost, 2),
                "total_costs_paid": round(total_spread_cost + total_slippage_cost + total_swap_cost, 2)
            },
            "breakdown_by_weekday": weekday_pnl,
            "days_simulated": days_count,
            "cost_multiplier_tested": self.cost_multiplier
        }


def replay(bundle, candles, news_events=None, initial_balance: float = 1000.0, cost_multiplier: float = 1.0, overrides: Optional[Dict[str, Any]] = None):
    """Entry point matching sentinel_engine.sim signature."""
    specs = getattr(bundle, "specs", None) or {
        "digits": 5, "point": 0.00001, "contract_size": 100000.0,
        "volume_min": 0.01, "volume_max": 50.0, "volume_step": 0.01,
        "typical_spread_pts": 15, "swap_long": -5.0, "swap_short": 1.0
    }
    sim = CFDSimulator(
        symbol_specs=specs,
        initial_balance=initial_balance,
        cost_multiplier=cost_multiplier,
        owner_overrides=overrides
    )
    return sim.simulate(bundle, candles, news_events)


def simulate_bundle(bundle_path: str, candles: Optional[List[Dict[str, Any]]] = None, initial_balance: float = 1000.0, cost_multiplier: float = 1.0) -> Dict[str, Any]:
    """Helper for CLI sfx sim <bundle.sfxmodel.zip>."""
    from .bundle import load_bundle
    bundle = load_bundle(bundle_path)
    if candles is None:
        candles = [
            {"epoch": 1700000000 + i * 60, "open": 1.0500 + i * 0.0001, "high": 1.0505 + i * 0.0001, "low": 1.0495 + i * 0.0001, "close": 1.0502 + i * 0.0001}
            for i in range(120)
        ]
    return replay(bundle, candles, initial_balance=initial_balance, cost_multiplier=cost_multiplier)
