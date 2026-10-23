"""Pure recovery decision regressions; NOT live H8/V8/V11 evidence.
The independent watcher remains staged until atomic Worker claim routes exist.
"""
import unittest
from datetime import datetime, timezone
from tools.recovery_watchdog import classify, next_failure

class RecoveryDecisions(unittest.TestCase):
    def test_login_failure_is_code_even_when_run_was_scheduled(self):
        kind,reason=classify('failure','AssertionError: demo login failed')
        self.assertEqual(kind,'code');self.assertIn('demo login failed',reason)

    def test_missing_runner_and_connection_reset_are_platform_failures(self):
        for text in ('hosted runner failed to initialize','ConnectionResetError: connection reset','HTTP Error 503: Service Unavailable'):
            self.assertEqual(classify('failure',text)[0],'platform')

    def test_cancelled_run_without_code_exception_can_recover(self):
        self.assertEqual(classify('cancelled','The operation was canceled.')[0],'platform')

    def test_three_code_failures_halt_with_original_error(self):
        previous={};now=datetime(2026,10,23,tzinfo=timezone.utc)
        for identifier in range(1,4):
            previous=next_failure(previous,{'id':identifier},'code','ValueError: actual code error',now)
        self.assertEqual(previous['status'],'code_failure_halted')
        self.assertEqual(previous['error'],'ValueError: actual code error')
        self.assertEqual(previous['consecutive_failures'],3)

    def test_platform_cooldowns_continue_instead_of_permanent_halt(self):
        previous={};now=datetime(2026,10,23,tzinfo=timezone.utc)
        for identifier,expected in enumerate((1800,7200,21600,21600,21600),1):
            previous=next_failure(previous,{'id':identifier},'platform','GitHub unavailable',now)
            self.assertEqual(previous['delay_seconds'],expected)
            self.assertEqual(previous['status'],'recovering')

    def test_same_run_is_idempotent_and_success_resets_streak(self):
        first=next_failure({}, {'id':1}, 'code', 'error')
        self.assertEqual(next_failure(first,{'id':1},'code','error'),first)
        recovered=dict(first,status='recovered')
        self.assertEqual(next_failure(recovered,{'id':2},'code','error')['consecutive_failures'],1)

if __name__=='__main__':unittest.main(verbosity=2)
