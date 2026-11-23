"""Failure classification and unattended reporting, without launching a GUI."""
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import launch_release as launcher


class ReleaseReportingTests(unittest.TestCase):
    def test_runtime_exit_is_not_reported_as_activation_failure(self):
        with patch.object(launcher, '_show_error_dialog') as dialog, patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(launcher.report_failure(launcher.AppSessionError('Windows app exited with code 7'), show_dialog=False), 1)
        self.assertIn('stopped unexpectedly', stderr.getvalue())
        self.assertIn('code 7', stderr.getvalue())
        self.assertNotIn('could not start', stderr.getvalue())
        dialog.assert_not_called()

    def test_startup_error_keeps_default_user_notification(self):
        with patch.object(launcher, '_show_error_dialog') as dialog, patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(launcher.report_failure(RuntimeError('activation refused')), 1)
        self.assertIn('could not start', stderr.getvalue())
        if os.name == 'nt':dialog.assert_called_once()
        else:dialog.assert_not_called()

    def test_consoleless_unattended_failure_still_returns_nonzero(self):
        with patch.object(launcher, '_show_error_dialog') as dialog, patch('sys.stderr', None):
            self.assertEqual(launcher.report_failure(RuntimeError('failure'), show_dialog=False), 1)
        dialog.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows release entrypoint')
    def test_error_dialog_flag_is_explicit_and_runtime_stage_is_preserved(self):
        error = launcher.AppSessionError('Windows app exited with code 7\nLogs: generated')
        for flags, expected in (([], True), (['--no-error-dialog'], False)):
            with self.subTest(flags=flags), patch.object(sys, 'argv', ['launch_release.py', *flags]), patch.object(launcher, 'load_settings', return_value={}), patch.object(launcher, 'launch', side_effect=error), patch.object(launcher, 'report_failure', return_value=1) as report:
                self.assertEqual(launcher.main(), 1)
                report.assert_called_once_with(error, show_dialog=expected)


if __name__ == '__main__':unittest.main()
