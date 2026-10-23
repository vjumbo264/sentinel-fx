"""Fixed purged validation windows, bounded per checkpoint; never final hold-out.

Three deterministic, disjoint 1024-bar windows cover early/middle/late validation.
2400 bars are purged after training and 2400 prior bars warm up each window.
Bad windows are recorded and excluded, not silently repaired or scored as wins.
Any skipped window makes this checkpoint ineligible for best/release selection.
"""
import math
import numpy as np
from tools.train_env import SentinelScalpEnv

PURGE = 2400
WINDOW = 1024
WARMUP = 2400


def evaluate_validation(model, full_data, specs, pair):
    first, end = int(len(full_data)*.70)+PURGE, int(len(full_data)*.85)
    usable_start = first+WARMUP
    if end-usable_start < WINDOW:
        return {'verdict':'insufficient_data','eligible':False,'val_rows':0,
                'reason':'purged validation too short; never borrow training or locked hold-out'}
    starts = sorted(set(int(x) for x in np.linspace(usable_start, end-WINDOW, 3)))
    curves, closed, errors, windows = [], [], [], []
    cost, active_days, days = 0., set(), set()
    for start in starts:
        stop = start+WINDOW
        window = full_data.iloc[start-WARMUP:stop].reset_index(drop=True)
        record = {'start_epoch':int(full_data.iloc[start].epoch),
                  'end_epoch':int(full_data.iloc[stop-1].epoch),'rows':WINDOW}
        try:
            # Drop no rows: invalid prices/volatility are a bad window, not tradable data.
            cols=[c for c in ('bid_open','bid_high','bid_low','bid_close','ask_close') if c in window]
            values=window[cols].to_numpy(dtype=float)
            if not cols or not np.isfinite(values).all() or (values<=0).any():
                raise ValueError('nonfinite or nonpositive validation prices')
            env=SentinelScalpEnv(window,specs,pair)
            obs,_=env.reset(options={'start_bar':WARMUP})
            curve=[env.initial_balance]
            active=set()
            while True:
                action,_=model.predict(obs,deterministic=True)
                epoch=env.broker.epoch
                obs,_,terminated,truncated,info=env.step(int(action))
                if not math.isfinite(info['equity']):
                    raise ValueError('nonfinite validation equity')
                curve.append(info['equity'])
                days.add(epoch//86400)
                if env.broker.positions or info['result'].get('tickets'):
                    active.add(epoch//86400)
                if terminated or truncated:break
            curves.append(np.array(curve,dtype=float));closed.extend(env.broker.closed)
            cost+=env.broker.cost_paid;active_days.update(active)
            record.update(status='evaluated',final_equity=curve[-1],trades=len(env.broker.closed))
        except (ValueError, FloatingPointError, ZeroDivisionError, OverflowError) as exc:
            record.update(status='skipped',error=str(exc))
            errors.append(record.copy())
            print(f"VALIDATION WINDOW SKIPPED {pair} epoch={record['start_epoch']}: {exc}",flush=True)
        windows.append(record)
    if not curves:
        return {'verdict':'invalid_data','eligible':False,'val_rows':0,
                'skipped_windows':errors,'windows':windows,'reason':'all validation windows skipped'}
    returns=np.concatenate([np.diff(np.log(np.maximum(c,1e-9))) for c in curves])
    growth=float(np.prod([c[-1]/c[0] for c in curves])-1)
    drawdown=max(float(np.max(1-c/np.maximum.accumulate(c))) for c in curves)
    sharpe=float(returns.mean()/(returns.std()+1e-9)*np.sqrt(252*1440))
    eligible=not errors
    result={'verdict':'pass' if eligible and growth>0 and drawdown<.30 and len(closed)>=10 else 'no_edge',
            'eligible':eligible,'val_rows':sum(len(c)-1 for c in curves),'purge_bars':PURGE,
            'holdout_rows':len(full_data)-end,'holdout_accessed':False,
            'total_return_pct':round(growth*100,6),'max_drawdown_pct':round(drawdown*100,6),
            'sharpe_annualized':round(sharpe,6),'trade_count':len(closed),
            'activity_days':len(active_days),'evaluated_days':len(days),'cost_paid':cost,
            'windows':windows,'skipped_windows':errors,
            'sampling':'three fixed 1024-bar purged validation windows; not full validation coverage'}
    print('VALIDATION '+str(pair)+' '+str(result),flush=True)
    return result
