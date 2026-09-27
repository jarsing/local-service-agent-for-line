import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from .build_context import export

class PackagingTests(unittest.TestCase):
    def test_context_contains_new_entrypoint_and_no_editorial_or_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'context'; report = export(out)
            self.assertEqual(report['day13_entrypoint'],'examples.day13.main:app')
            self.assertIn('examples.day13.main:app',(out/'Dockerfile').read_text())
            self.assertTrue((out/'examples/day13/messages.py').is_file())
            self.assertTrue((out/'examples/day12/tasks.py').is_file())
            self.assertFalse((out/'examples/day13/test_flex.py').exists())
            self.assertFalse((out/'editorial').exists())
            self.assertFalse(any(p.name=='.env' for p in out.rglob('*')))
            for rel,h in report['files'].items():
                self.assertEqual(hashlib.sha256((out/rel).read_bytes()).hexdigest(),h)

    def test_context_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): export(Path(tmp))

    def test_sample_export_has_explicit_synthetic_origin(self):
        from .export_samples import export as samples
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'samples';samples(out)
            self.assertEqual(json.loads((out/'SOURCE.json').read_text())['origin'],'synthetic_fixture')
            self.assertTrue((out/'receipt.json').is_file())
            self.assertIn('SYNTHETIC',(out/'receipt.json').read_text())

if __name__ == '__main__': unittest.main()
