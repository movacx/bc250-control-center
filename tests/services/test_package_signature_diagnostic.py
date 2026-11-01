"""Package-manager summary lines must not invent an upstream HTTP 404."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared import error_catalog

SIGNATURE_FAILURE = (
    'error: cachyos-extra-v3: signature from "CachyOS <admin@cachyos.org>" is invalid\n'
    'error: failed to synchronize all databases (unexpected error)\n'
)


class PackageSignatureDiagnostic(unittest.TestCase):
    def test_catalog_classifies_cachyos_signature_failure(self):
        self.assertEqual(error_catalog.for_marker(SIGNATURE_FAILURE).code, 'BC250-PKG-002')

    def test_terminal_reports_signature_failure_instead_of_404(self):
        import shlex
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = 'printf %s ' + shlex.quote(SIGNATURE_FAILURE) + '; exit 1'
            wrapped = workflow_wrapper(command, root / 'status', root / 'log', hold=False)
            result = subprocess.run(['bash', '-c', wrapped], input='', text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 1)
            self.assertIn('BC250-PKG-002', result.stdout)
            self.assertNotIn('BC250-UPSTREAM-404', result.stdout)
            self.assertIn('Update the distribution keyring', result.stdout)

    def test_real_404_and_busy_database_keep_their_diagnoses(self):
        for detail, expected in (
            ('error: The requested URL returned error: 404\n'
             'error: failed to synchronize all databases', 'BC250-UPSTREAM-404'),
            ('error: failed to synchronize all databases (unable to lock database)', 'BC250-PKG-001'),
        ):
            with self.subTest(detail=detail):
                self.assertEqual(error_catalog.for_marker(detail).code, expected)
                import shlex
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    wrapped = workflow_wrapper('printf %s ' + shlex.quote(detail) + '; exit 1',
                                               root / 'status', root / 'log', hold=False)
                    result = subprocess.run(['bash', '-c', wrapped], input='', text=True,
                                            capture_output=True, timeout=30)
                    self.assertIn(expected, result.stdout)
                    self.assertNotIn('BC250-PKG-002', result.stdout)

    def test_generic_sync_failure_is_not_evidence_of_404(self):
        self.assertIsNone(error_catalog.for_marker(
            'error: failed to synchronize all databases (unexpected error)'))


if __name__ == '__main__':
    unittest.main()
