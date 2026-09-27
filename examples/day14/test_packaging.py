"""建置內容檢查，不等於 Docker 已建置或 Cloud Run 已部署。"""
from pathlib import Path
import tempfile
import unittest
from .build_context import export,RUNTIME

class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'context';self.report=export(self.path)
    def test_new_entrypoint(self):
        self.assertIn('examples.day14.main:app',(self.path/'Dockerfile').read_text())
    def test_new_runtime_and_data_present(self):
        for name in RUNTIME:self.assertTrue((self.path/'examples/day14'/name).is_file())
    def test_previous_service_preserved(self):
        for name in ['examples/day08/confirmation.py','examples/day12/tasks.py','examples/day13/bridge.py']:
            self.assertTrue((self.path/name).is_file())
    def test_no_tests_or_evidence_or_live_audit(self):
        for path in self.path.rglob('*'):
            if path.is_file():
                self.assertFalse(path.name.startswith('test_'))
                self.assertNotIn(path.name,['live_check.py','.env','ANTIGRAVITY_PROMPT.md'])
    def test_reject_existing_target(self):
        with self.assertRaises(Exception):export(self.path)
