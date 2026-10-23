"""Gymnasium M1 environment using the exact live engine observation/adapter."""
import gymnasium as gym
import numpy as np
import pandas as pd
from sentinel_engine.observation import build_observation, vectorize
from sentinel_engine.execution_adapter import ExecutionAdapter
from sentinel_engine.sim import SimulationBroker

ACTION_CATALOG = [
    [{'type': 'hold', 'reason': 'agent_hold'}],
    [{'type': 'open', 'side': 'long', 'risk_fraction': .01, 'stop_distance': 1.5, 'reason': 'agent_long'}],
    [{'type': 'open', 'side': 'short', 'risk_fraction': .01, 'stop_distance': 1.5, 'reason': 'agent_short'}],
    [{'type': 'close', 'position_ref': 'oldest', 'reason': 'agent_close'}],
    [{'type': 'move_stop', 'position_ref': 'oldest', 'to_breakeven': True, 'reason': 'agent_be'}],
]

class SentinelScalpEnv(gym.Env):
    metadata = {'render_modes': []}
    observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(47,), dtype=np.float64)
    action_space = gym.spaces.Discrete(5)

    def __init__(self, candles, specs, symbol='EURUSD', initial_balance=10000, leverage=100):
        super().__init__()
        self.frame = pd.DataFrame(candles).sort_values('epoch').drop_duplicates('epoch').reset_index(drop=True)
        # Release data are bid/ask; shared observation builder consumes the same bid OHLC as live.
        for field in ('open', 'high', 'low', 'close'):
            if field not in self.frame and 'bid_' + field in self.frame:
                self.frame[field] = self.frame['bid_' + field]
        required = ['epoch', 'open', 'high', 'low', 'close']
        if len(self.frame) < 63 or not np.isfinite(self.frame[required].to_numpy()).all():
            raise ValueError('at least 63 finite completed M1 bars required')
        self.specs, self.symbol = dict(specs), symbol
        self.initial_balance, self.leverage = float(initial_balance), leverage
        self.broker = None
        self._position = None
        self._bars_held = 0
        self.last_observation = None
        self.last_result = None
        self.peak = self.initial_balance

    def _observe(self):
        equity = self.broker.equity()
        self.peak = max(self.peak, equity)
        self.last_observation, self.atr = build_observation(
            self.frame.iloc[max(0, self.i - 2399):self.i + 1], equity=equity,
            pool_share=self.initial_balance, positions=self.broker.get_open_positions(),
            specs=self.specs, tick=self.broker.tick, drawdown=max(0, 1-equity/self.peak),
            last_result=self.last_result)
        vector = vectorize(self.last_observation)
        if vector.shape != (47,) or not np.isfinite(vector).all():
            raise ValueError('live observation contract violated')
        return vector

    def _sync_position(self):
        positions = self.broker.get_open_positions()
        self._position = min(positions, key=lambda p: (p['time'], p['ticket'])) if positions else None
        self._bars_held = max(0, (self.broker.epoch-self._position['time'])//60) if self._position else 0

    def _action_to_dict(self, action_idx):
        if action_idx == 0:
            return {'type': 'hold', 'reason': 'agent_hold'}
        if action_idx in (1, 2):
            return {'type': 'open', 'side': 'long' if action_idx == 1 else 'short',
                    'risk_fraction': .01, 'stop_distance': 1.5,
                    'reason': 'agent_long' if action_idx == 1 else 'agent_short'}
        if not self._position:
            return {'type': 'hold', 'reason': 'no_position'}
        if action_idx == 3:
            return {'type': 'close', 'position_ref': str(self._position['ticket']), 'reason': 'agent_close'}
        if action_idx == 4:
            return {'type': 'move_stop', 'position_ref': str(self._position['ticket']),
                    'to_breakeven': True, 'reason': 'agent_be'}
        raise ValueError('invalid action index')

    def _reward(self, prev_equity, curr_equity, action_idx, had_position=None):
        pnl = np.log(max(curr_equity, 1e-9)/max(prev_equity, 1e-9))
        hold_cost = -.00005*self._bars_held if self._position else 0.
        invalid = -.001 if action_idx in (3, 4) and not had_position else 0.
        return float(pnl + hold_cost + invalid)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        requested = (options or {}).get('start_bar')
        self.i = int(requested if requested is not None else self.np_random.integers(60, len(self.frame)-2))
        if not 60 <= self.i < len(self.frame)-1:
            raise ValueError('reset start must have 60 historical bars and future data')
        self.broker = SimulationBroker(self.specs, self.initial_balance, self.leverage,
                                       commission=self.specs.get('commission_per_lot', 0),
                                       slippage=self.specs.get('slippage_points', 0)*self.specs['point'])
        row = self.frame.iloc[self.i]
        spread = self.specs.get('typical_spread_pts', 1.5)*self.specs['point']
        self.broker.set_tick({'bid': float(row.get('bid_close', row['close'])),
                              'ask': float(row.get('ask_close', row['close']+spread))}, int(row['epoch'])+60)
        self._position = None
        self._bars_held = 0
        self.last_result = None
        self.peak = self.initial_balance
        self._ended = False
        return self._observe(), {'equity': self.initial_balance}

    def _rollover(self, previous, current):
        # Match CFDSimulator's fixed 22:00 UTC rollover, triple Wednesday, including gaps.
        from datetime import datetime, timezone, timedelta
        boundary = datetime.fromtimestamp(previous, timezone.utc).replace(hour=22, minute=0, second=0, microsecond=0)
        while boundary.timestamp() <= current:
            if boundary.timestamp() > previous:
                for position in self.broker.positions:
                    rate = self.specs.get('swap_long', 0) if position['type'] == 'BUY' else self.specs.get('swap_short', 0)
                    swap = rate*position['volume']*(3 if boundary.weekday() == 2 else 1)
                    self.broker.balance += swap
                    self.broker.cost_paid += max(0, -swap)
            boundary += timedelta(days=1)

    def step(self, action):
        if self._ended:
            raise RuntimeError('reset required after episode end')
        action = int(action)
        if not self.action_space.contains(action):
            raise ValueError('action out of range')
        previous = self.broker.equity()
        self._sync_position()
        had_position = self._position is not None
        adapter = ExecutionAdapter(self.broker, self.symbol, 'training',
                                   pool_equity=self.broker.equity(),
                                   pool_free_margin=max(0, self.broker.equity()-self.broker.margin()),
                                   volatility=self.atr)
        # The action was selected from the CURRENT returned observation, so fill
        # at its close tick, not at an unseen future close (a one-bar lag/leak).
        self.last_result = adapter.execute(self._action_to_dict(action), str(self.broker.epoch))
        old_epoch = self.broker.epoch
        self.i += 1
        row = self.frame.iloc[self.i]
        spread = float(row.get('ask_open', row['open']+self.specs.get('typical_spread_pts', 1.5)*self.specs['point']))-float(row.get('bid_open', row['open']))
        self._rollover(old_epoch, int(row['epoch'])+60)
        self.broker.intrabar(row, spread)
        self._sync_position()
        terminated = self.broker.equity() < self.initial_balance*.1
        truncated = self.i >= len(self.frame)-1
        if terminated or truncated:
            for p in list(self.broker.positions):
                self.broker.close_position(p['ticket'], self.symbol, comment='episode_end')
            self._sync_position()
        self._ended = bool(terminated or truncated)
        reward = self._reward(previous, self.broker.equity(), action, had_position)
        return self._observe(), reward, bool(terminated), bool(truncated), {
            'equity': self.broker.equity(), 'result': self.last_result,
            'closed_trades': len(self.broker.closed), 'cost_paid': self.broker.cost_paid}
