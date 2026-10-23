"""Export deterministic PPO action LOGITS and the unchanged engine v2 bundle."""
import copy
import hashlib
import json
import zipfile
from pathlib import Path
import numpy as np
import torch
from sentinel_engine.policy_schema import VERSION, OBSERVATION_DIM
from sentinel_engine.observation import vectorize
from sentinel_engine.execution_adapter import ExecutionAdapter
from sentinel_engine.sim import SimulationBroker
from sentinel_engine.check import check_bundle
from tools.train_env import ACTION_CATALOG

class LogitsPolicy(torch.nn.Module):
    """SB3 policy.forward emits sampled actions/values; live engine needs five scores."""
    def __init__(self, policy):
        super().__init__()
        self.policy = policy

    def forward(self, obs):
        features = self.policy.extract_features(obs)
        latent = self.policy.mlp_extractor.forward_actor(features)
        return self.policy.action_net(latent)


def export_bundle(model, env, pair, version, output, training_report):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    policy = LogitsPolicy(model.policy).cpu().eval()
    obs_dim = env.observation_space.shape[0]
    if obs_dim != OBSERVATION_DIM:
        raise ValueError(f'observation size mismatch: expected {OBSERVATION_DIM}, got {obs_dim}')
    onnx_path = output / f'{pair}_policy.onnx'
    torch.onnx.export(policy, torch.zeros(1, obs_dim, dtype=torch.float32), str(onnx_path),
                      input_names=['obs'], output_names=['action_logits'], opset_version=17,
                      dynamo=False, dynamic_axes={'obs': {0: 'batch'}, 'action_logits': {0: 'batch'}})
    import onnxruntime as ort
    options = ort.SessionOptions(); options.intra_op_num_threads = 1; options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(onnx_path), sess_options=options, providers=['CPUExecutionProvider'])
    vectors = []
    # Actual training input bars and shared observations, never invented expected baselines.
    old_env = env
    from tools.train_env import SentinelScalpEnv
    probe = SentinelScalpEnv(env.frame, env.specs, pair)
    for seed in (11, 23, 37):
        x, _ = probe.reset(seed=seed)
        if seed == 23:
            x, *_ = probe.step(1)
        obs = probe.last_observation.to_dict()
        with torch.no_grad():
            scores = policy(torch.as_tensor(x[None], dtype=torch.float32)).numpy()[0].astype(float)
        live_scores = session.run(None, {'obs': x[None].astype(np.float32)})[0][0]
        if not np.allclose(scores, live_scores, rtol=1e-5, atol=1e-6) or np.argmax(scores) != np.argmax(live_scores):
            raise ValueError('Torch/ONNX logits or action parity mismatch')
        actions = copy.deepcopy(ACTION_CATALOG[int(np.argmax(scores))])
        for action in actions:
            if action.get('position_ref') == 'oldest':
                if not obs['positions']:
                    action.clear(); action.update(type='hold', reason='Management intent has no owned position')
                else:
                    action['position_ref'] = max(obs['positions'], key=lambda p: p['time_open_minutes'])['position_ref']
        expected = {'schema_version': VERSION, 'actions': actions, 'reason': '; '.join(a['reason'] for a in actions),
                    'opinions': [], 'error': None, 'scores': scores.tolist()}
        vectors.append({'observation': obs, 'candles': probe.frame.iloc[max(0,probe.i-60):probe.i+1].to_dict('records'),
                        'expected': expected})
    tick = {'bid': float(env.frame.iloc[60]['close']),
            'ask': float(env.frame.iloc[60].get('ask_close', env.frame.iloc[60]['close']+env.specs['point']*15))}
    cases = []
    # Test normal fill, margin rejection, owner halt, risk rounding and hold.
    for action, free, overrides in [
        (ACTION_CATALOG[0][0], 10000, {}), (ACTION_CATALOG[1][0], 10000, {}),
        (ACTION_CATALOG[2][0], 10000, {}), (ACTION_CATALOG[1][0], 0, {}),
        (ACTION_CATALOG[1][0], 10000, {'halt': True})]:
        case = {'specs': env.specs, 'balance': 10000, 'free_margin': free, 'tick': tick,
                'epoch': int(env.frame.iloc[60]['epoch']), 'volatility': probe.atr,
                'overrides': overrides, 'action': action, 'leverage': 100}
        port = SimulationBroker(case['specs'], 10000)
        port.set_tick(tick, case['epoch'])
        case['expected'] = ExecutionAdapter(port, 'TEST', 'health', 10000, free, case['volatility'], overrides).execute(action, 'health')
        cases.append(case)
    payload = {
        'analysis_plan.json': {'nodes': [{'id': 'policy', 'type': 'policy', 'schema_version': VERSION,
                                        'model': 'models/policy.onnx', 'inputs': [], 'action_catalog': ACTION_CATALOG}]},
        'policy.json': {'schema_version': VERSION, 'observation_dim': obs_dim, 'action_catalog': ACTION_CATALOG},
        'risk_brain.json': {'mandatory_server_stop': True, 'risk_fraction': .01, 'stop_distance_atr': 1.5},
        'training_report.json': training_report,
        'tests/vectors.json': {'vectors': vectors, 'tolerance': 1e-5, 'latency_ms': 600},
        'tests/adapter.json': cases,
    }
    raw = {name: json.dumps(data, sort_keys=True, allow_nan=False).encode() for name,data in payload.items()}
    raw['models/policy.onnx'] = onnx_path.read_bytes()
    manifest = {'schema_version': 2, 'symbol': 'frx'+pair, 'mt5_symbol': pair, 'version': version,
                'entry_seconds': 60, 'policy_schema': VERSION, 'observation_dim': OBSERVATION_DIM,
                'trained_through': training_report.get('trained_through'),
                'files': {name: {'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
                          for name,data in raw.items()}}
    bundle = output / f'frx{pair}_v{version}.sfxmodel.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name,data in raw.items():
            archive.writestr(name, data)
    report = check_bundle(str(bundle))
    if not report['ok']:
        raise ValueError('bundle health check failed: ' + str(report['problems']))
    return bundle, report
