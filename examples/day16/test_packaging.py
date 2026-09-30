from pathlib import Path
import tempfile
import unittest
import hashlib
from .build_context import export
from examples.day17.build_context import RUNTIME as DAY17_RUNTIME


class PackagingTests(unittest.TestCase):
    def test_minimum_context_includes_day16_and_excludes_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "context"
            report = export(out)
            self.assertEqual(report["day16_entrypoint"], "examples.day16.main:app")
            self.assertIn("examples.day16.main:app", (out / "Dockerfile").read_text())
            self.assertIn("COPY examples/day16/*.py", (out / "Dockerfile").read_text())
            self.assertIn("COPY examples/day17/*.py", (out / "Dockerfile").read_text())
            for name in DAY17_RUNTIME:
                self.assertTrue((out / "examples/day17" / name).is_file())
            for name in ("demo.py", "verify.py", "build_context.py", "README.md", "tests"):
                self.assertFalse((out / "examples/day17" / name).exists())
            self.assertTrue((out / "examples/day16/data/untrusted_flyer.txt").is_file())
            self.assertFalse((out / "examples/day16/test_policy.py").exists())
            self.assertFalse((out / ".git").exists())
            self.assertFalse((out / "editorial").exists())
            for name, digest in report["files"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)

    def test_existing_export_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "context"
            out.mkdir()
            with self.assertRaises((FileExistsError, ValueError)):
                export(out)
