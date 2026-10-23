import json
import numpy as np
import pytest
from tools.train_agent import synthetic_bars, new_state, advance
from tools.train_env import SentinelScalpEnv
from tools.release_utils import ROOT

@pytest.fixture
def env():
    specs = json.loads((ROOT/'data/symbols.json').read_text())['symbols']['EURUSD']
    return SentinelScalpEnv(synthetic_bars(300),specs)

def test_engine_vector_and_five_actions(env):
    vector,_ = env.reset(seed=1,options={'start_bar':60})
    assert vector.dtype == np.float64 and vector.shape == (47,) and np.isfinite(vector).all()
    assert env._action_to_dict(3)['type']=='hold'
    for action in range(5):
        vector,reward,terminated,truncated,info = env.step(action)
        assert np.isfinite(vector).all() and np.isfinite(reward)

def test_invalid_penalty_uses_position_before_action(env):
    env.reset(options={'start_bar':60})
    _,reward,*_ = env.step(3)
    assert reward == pytest.approx(-.001)
    env.reset(options={'start_bar':60})
    env.step(1)
    assert env.last_result['status']=='filled'
    assert env.broker.positions
    _,reward,*_ = env.step(3)
    assert env.last_result['status']=='filled'
    assert not env.broker.positions
    # Closing a valid position must not incur the missing-position penalty.
    assert reward > -.001

def test_execution_uses_observed_tick_not_next_bar(env):
    env.reset(options={'start_bar':60})
    expected_ask = env.broker.tick['ask']
    env.step(1)
    assert env.last_result['price'] == pytest.approx(expected_ask)

def test_synthetic_does_not_count_as_real_training():
    state=json.loads((ROOT/'training_state.json').read_text())
    assert state['total_steps_done']==0
    assert state['smoke_test']['synthetic'] is True
    assert state['smoke_test']['steps']==1000

def test_next_pair_and_monthly_cycle():
    state=new_state();advance(state)
    assert state['active_pair']=='GBPUSD' and state['pairs_done']==['EURUSD']
    state['pairs_done']=state['queue'][:-1];state['active_pair']=state['queue'][-1]
    advance(state)
    assert state['retrain_cycle']==2 and state['active_version']==2
    assert len(state['pairs_pending'])==13 and state['next_retrain_after_utc']

def test_episode_end_liquidates(env):
    env.reset(options={'start_bar':len(env.frame)-2})
    obs,reward,term,trunc,info=env.step(1)
    assert trunc and not env.broker.positions
    with pytest.raises(RuntimeError):env.step(0)
