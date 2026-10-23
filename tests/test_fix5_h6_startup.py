"""Local startup regressions, NOT a substitute for Windows/MT5 acceptance."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.mt5_broker import MT5Broker


class TestNativeStartup(unittest.TestCase):
    def test_initialize_authenticates_first_and_uses_launched_executable(self):
        calls = []
        class API:
            def initialize(self, **kw):
                calls.append(kw)
                return True
            def login(self, **kw):
                return True
            def account_info(self):
                return SimpleNamespace(balance=10000, currency='USD', leverage=100, margin_mode=2)
        broker = MT5Broker(demo_login='123456', demo_server='Demo', password='test-fixture-only')
        broker._mt5 = API()
        with patch.dict(os.environ, {'MT5_TERMINAL_PATH': r'C:\runtime\terminal64.exe'}):
            self.assertTrue(broker.connect('demo'))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['login'], 123456)
        self.assertEqual(calls[0]['server'], 'Demo')
        self.assertEqual(calls[0]['password'], 'test-fixture-only')
        self.assertEqual(calls[0]['path'], r'C:\runtime\terminal64.exe')
        self.assertTrue(calls[0]['portable'])
        self.assertGreaterEqual(calls[0]['timeout'], 60000)

    def test_wrong_mode_is_rejected_before_initialization(self):
        with self.assertRaisesRegex(ValueError, 'Invalid mode'):
            MT5Broker().connect('unexpected')


if __name__ == '__main__':
    unittest.main()
