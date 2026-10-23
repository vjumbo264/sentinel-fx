"""Local regressions, not substitutes for real Actions checkpoint acceptance."""
import json
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from tools.validation import evaluate_validation
from tools.train_agent import synthetic_bars, create_model
from tools.train_env import SentinelScalpEnv

ROOT=Path(__file__).resolve().parents[1]

class SafeValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs=json.loads((ROOT/'data/symbols.json').read_text())['symbols']['EURUSD']
        cls.frame=synthetic_bars(60000)
        # Real SB3 object, but deliberately untrained; no broker/profitability claim.
        cls.model=create_model(SentinelScalpEnv(cls.frame.iloc[:1000],cls.specs),smoke=True)

    def test_insufficient_never_borrows_holdout(self):
        result=evaluate_validation(self.model,self.frame.iloc[:3000],self.specs,'EURUSD')
        self.assertEqual(result['verdict'],'insufficient_data')
        self.assertFalse(result['eligible'])

    def test_invalid_windows_skipped_not_fatal(self):
        bad=self.frame.copy()
        bad.loc[int(len(bad)*.70):int(len(bad)*.85),'bid_high']=np.nan
        result=evaluate_validation(self.model,bad,self.specs,'EURUSD')
        self.assertFalse(result['eligible'])
        self.assertEqual(result['verdict'],'invalid_data')
        self.assertEqual(len(result['skipped_windows']),3)
        self.assertTrue(all(w['status']=='skipped' for w in result['windows']))

if __name__=='__main__':unittest.main()
