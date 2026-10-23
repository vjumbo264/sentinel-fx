"""Real ONNX archive/CLI checks; no mocked inference or broker claims."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
import numpy as np
import onnx
from onnx import helper, TensorProto
from sentinel_engine.bundle import verify_bundle, load_bundle
from sentinel_engine.policy_schema import OBSERVATION_DIM, VERSION
from sentinel_engine.observation import vectorize


def archive(path, width, declared=None):
    x = helper.make_tensor_value_info('obs', TensorProto.FLOAT, [1, width])
    y = helper.make_tensor_value_info('scores', TensorProto.FLOAT, [1, 1])
    weight = helper.make_tensor('weight', TensorProto.FLOAT, [width, 1], np.zeros(width, dtype=np.float32))
    graph = helper.make_graph([helper.make_node('MatMul', ['obs', 'weight'], ['scores'])], 'real-shape-test', [x], [y], [weight])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)])
    model.ir_version = 9
    files = {'models/policy.onnx': model.SerializeToString(),
             'policy.json': json.dumps({'schema_version': VERSION, 'observation_dim': width if declared is None else declared}).encode(),
             'analysis_plan.json': json.dumps({'nodes': [{'id': 'policy', 'type': 'policy', 'model': 'models/policy.onnx', 'schema_version': VERSION, 'action_catalog': [[{'type':'hold','reason':'shape-test-only'}]]}]}).encode()}
    manifest = {'schema_version':2, 'symbol':'TEST_ONLY', 'version':1,
                'files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'size':len(v)} for k,v in files.items()}}
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('manifest.json', json.dumps(manifest))
        for name, data in files.items():z.writestr(name, data)


class SchemaCompatibility(unittest.TestCase):
    def test_actual_47_dimension_model_is_rejected_by_loader_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'retired.zip';archive(path,47)
            ok,problems=verify_bundle(str(path))
            self.assertFalse(ok);self.assertIn('expected 62', ';'.join(problems))
            with self.assertRaisesRegex(ValueError,'expected 62'):load_bundle(str(path))
            result=subprocess.run(['sfx','check',str(path)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn('expected 62',result.stdout)
            print('ACTUAL sfx check 47-d: exit',result.returncode,'expected 62 mismatch reported')

    def test_forged_metadata_does_not_hide_old_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'forged.zip';archive(path,47,62)
            ok,problems=verify_bundle(str(path))
            self.assertFalse(ok);self.assertIn('model input size mismatch',';'.join(problems))

    def test_actual_current_onnx_shape_passes_static_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'current.zip';archive(path,OBSERVATION_DIM)
            self.assertEqual(verify_bundle(str(path)),(True,[]))
            self.assertEqual(load_bundle(str(path)).model('models/policy.onnx').get_inputs()[0].shape,[1,62])

    def test_shared_vector_has_current_dimension(self):
        obs={'schema_version':VERSION,'market':{},'positions':[],'news':{},'costs':{},'drawdown':0,'equity':100,'pool_share':100,
             'session':{'hour_sin':0,'hour_cos':1,'weekday':0}}
        self.assertEqual(vectorize(obs).shape,(OBSERVATION_DIM,))

if __name__=='__main__':unittest.main(verbosity=2)
