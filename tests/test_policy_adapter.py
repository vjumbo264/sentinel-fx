"""Pure logic tests, not broker/live acceptance evidence."""
import pytest
from sentinel_engine.policy_schema import validate_action
from sentinel_engine.execution_adapter import ExecutionAdapter,model_magic
from sentinel_engine.sim import SimulationBroker,block_bootstrap_growth_ci
SPECS={'point':.00001,'digits':5,'tick_size':.00001,'tick_value':1,'contract_size':100000,'volume_min':.01,'volume_max':50,'volume_step':.01,'stops_level':10,'freeze_level':0}
def setup():
 b=SimulationBroker(SPECS,1000,100);b.set_tick({'bid':1.1,'ask':1.1002},1791710000)
 return b,ExecutionAdapter(b,'UNIT','unit',1000,1000,.001)
def test_missing_stop_gets_protective_server_stop():
 b,a=setup();r=a.execute({'type':'open','side':'long','risk_fraction':.01,'reason':'unit protective stop'})
 assert r['status']=='filled' and r['clamped']['protective_stop'];assert all(p['sl']>0 for p in b.positions)
 assert r['clamped']['risk_fraction']<=.01
@pytest.mark.parametrize('risk',[0,-1,1.1,float('nan'),float('inf')])
def test_oversized_and_invalid_risk_rejected(risk):
 b,a=setup();r=a.execute({'type':'open','side':'long','risk_fraction':risk,'reason':'invalid risk'})
 assert r['status']=='rejected' and r['reason']=='invalid' and not b.positions
@pytest.mark.parametrize('kind',['open','reduce','reverse','add','move_stop','close'])
def test_invalid_action_schema(kind):
 with pytest.raises(ValueError):validate_action({'type':kind,'reason':'unit invalid'})
def test_no_two_position_cap():
 b,a=setup()
 for i in range(4):assert a.execute({'type':'open','side':'long','risk_fraction':.002,'stop_distance':1,'reason':'independent budgeted entry'},str(i))['status']=='filled'
 assert len(b.positions)==4
 assert b.margin()<1000

def test_partial_close_and_model_ownership():
 b,a=setup();r=a.execute({'type':'open','side':'long','risk_fraction':.01,'stop_distance':1,'reason':'entry'})
 p=b.positions[0];r=a.execute({'type':'reduce','position_ref':str(p['ticket']),'fraction':.5,'reason':'reduce risk'})
 assert r['status']=='partial';other=ExecutionAdapter(b,'UNIT','different',1000,1000,.001)
 assert other.execute({'type':'close','position_ref':str(p['ticket']),'reason':'not owned'})['status']=='rejected'
def test_intrabar_both_hit_uses_stop():
 b,a=setup();a.execute({'type':'open','side':'long','risk_fraction':.01,'stop_distance':1,'targets':[{'distance':1,'fraction':1}],'reason':'collision'})
 p=b.positions[0];b.intrabar({'epoch':1791710060,'open':1.1,'high':1.11,'low':1.09,'close':1.1},.0002)
 assert b.closed[0]['close_reason']=='server_stop' and b.closed[0]['net_pnl']<0

def test_bootstrap_insufficient_is_unknown():assert block_bootstrap_growth_ci([.01]) is None
