import tempfile
import unittest
from pathlib import Path
from .build_context import export


class PackagingTests(unittest.TestCase):
    def test_whitelist_includes_runtime_not_test_or_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "context"
            manifest = export(target)
            self.assertTrue((target / "examples/day15/adk_budget_router.py").is_file())
            self.assertFalse((target / "examples/day15/test_adk.py").exists())
            self.assertFalse(list(target.rglob(".env")))
            self.assertIn("examples.day15.main:app", (target / "Dockerfile").read_text())
            self.assertTrue((target / "examples/day14/memory.py").is_file())
            self.assertEqual(manifest["day15_entrypoint"], "examples.day15.main:app")
