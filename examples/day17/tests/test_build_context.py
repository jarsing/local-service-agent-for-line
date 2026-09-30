"""建置白名單的離線檢查；測試資料只模擬被核對的目錄關係。"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .. import build_context


class BuildContextTests(unittest.TestCase):
    def fixture(self, directory: str):
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        for name in build_context.RUNTIME:
            (source / name).write_text("# 明示的合成測試檔案\n", encoding="utf-8")
        for name in ("demo.py", "verify.py", "README.md", ".env"):
            (source / name).write_text("不得進入映像的合成內容\n", encoding="utf-8")
        (source / "tests").mkdir()
        (source / "tests/test_private.py").write_text("# 合成測試\n", encoding="utf-8")
        out = root / "context"
        (out / "examples/day16").mkdir(parents=True)
        existing = b"# reviewed dependency fixture\n"
        (out / "examples/day16/main.py").write_bytes(existing)
        report = {
            "files": {"examples/day16/main.py": hashlib.sha256(existing).hexdigest()},
            "day16_entrypoint": "examples.day16.main:app",
        }
        return source, out, report

    def test_copy_only_runtime_and_preserve_existing_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, report = self.fixture(directory)
            with patch.object(build_context, "HERE", source):
                result = build_context.copy_runtime(out, report)
            copied = out / "examples/day17"
            self.assertEqual({path.name for path in copied.iterdir()}, set(build_context.RUNTIME))
            self.assertIs(result, report)
            self.assertEqual(report["day16_entrypoint"], "examples.day16.main:app")
            self.assertIn("examples/day16/main.py", report["files"])
            for name, digest in report["files"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
            for excluded in ("demo.py", "verify.py", "README.md", ".env", "tests", "build_context.py"):
                self.assertFalse((copied / excluded).exists())

    def test_missing_source_is_rejected_before_any_day17_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, report = self.fixture(directory)
            (source / "legacy_adapter.py").unlink()
            with patch.object(build_context, "HERE", source):
                with self.assertRaisesRegex(ValueError, "MISSING_OR_LINKED_SOURCE"):
                    build_context.copy_runtime(out, report)
            self.assertFalse((out / "examples/day17").exists())

    def test_symlinked_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, report = self.fixture(directory)
            (source / "outcomes.py").unlink()
            (source / "outcomes.py").symlink_to(source / "adapters.py")
            with patch.object(build_context, "HERE", source):
                with self.assertRaisesRegex(ValueError, "MISSING_OR_LINKED_SOURCE"):
                    build_context.copy_runtime(out, report)
            self.assertFalse((out / "examples/day17").exists())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, out, report = self.fixture(directory)
            (out / "examples/day17").mkdir()
            original = out / "examples/day17/outcomes.py"
            original.write_text("# 保留既有內容\n", encoding="utf-8")
            with patch.object(build_context, "HERE", source):
                with self.assertRaises(FileExistsError):
                    build_context.copy_runtime(out, report)
            self.assertEqual(original.read_text(encoding="utf-8"), "# 保留既有內容\n")

    def test_runtime_relative_imports_are_in_allowlist(self):
        allowed = {Path(name).stem for name in build_context.RUNTIME}
        for name in build_context.RUNTIME:
            with self.subTest(source=name):
                source = (build_context.HERE / name).read_text(encoding="utf-8")
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.ImportFrom) and node.level == 1:
                        modules = [node.module.split(".")[0]] if node.module else [item.name for item in node.names]
                        self.assertTrue(set(modules) <= allowed, (name, modules))


if __name__ == "__main__":
    unittest.main()
