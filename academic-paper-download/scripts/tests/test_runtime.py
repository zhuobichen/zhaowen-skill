from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[2]
RUNTIME = SKILL_ROOT / "scripts" / "runtime.py"
PYPROJECT = SKILL_ROOT / "pyproject.toml"
LOCK = SKILL_ROOT / "requirements.lock"


class RuntimeContractTests(unittest.TestCase):
    def test_project_range_and_exact_lock_are_aligned(self) -> None:
        project = PYPROJECT.read_text(encoding="utf-8")
        self.assertRegex(project, r'(?m)^requires-python = ">=3\.10"$')
        self.assertIn('"pypdf>=6.14,<7"', project)

        lock = LOCK.read_text(encoding="utf-8")
        self.assertRegex(lock, r"(?m)^pypdf==6\.14\.2 \\")
        self.assertRegex(lock, r"--hash=sha256:[0-9a-f]{64}")

    def test_offline_smoke_never_bootstraps_an_empty_cache(self) -> None:
        with (
            tempfile.TemporaryDirectory() as cache,
            tempfile.TemporaryDirectory() as cwd,
        ):
            environment = os.environ.copy()
            environment["ACADEMIC_PAPER_DOWNLOAD_CACHE_DIR"] = cache
            completed = subprocess.run(
                [sys.executable, str(RUNTIME), "smoke", "--offline", "--json"],
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 3, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "runtime_missing")
        self.assertNotIn("pip install", completed.stderr)

    def test_runtime_source_uses_skill_relative_paths(self) -> None:
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("Path(__file__).resolve()", source)
        self.assertNotRegex(source, re.compile(r"Path\([\"']requirements\.lock[\"']\)"))

    def test_entrypoint_options_are_forwarded_without_double_dash(self) -> None:
        spec = importlib.util.spec_from_file_location("academic_paper_runtime", RUNTIME)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        completed = subprocess.CompletedProcess(args=[], returncode=0)

        with (
            mock.patch.object(runtime, "_verify_environment", return_value=Path("/locked/python")),
            mock.patch.object(runtime.subprocess, "run", return_value=completed) as run,
        ):
            result = runtime.main(
                [
                    "notify-human",
                    "--title",
                    "Paper download needs your action",
                    "--message",
                    "Complete the security challenge normally.",
                    "--button",
                    "OK",
                    "--timeout",
                    "120",
                ]
            )

        self.assertEqual(result, 0)
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], "/locked/python")
        self.assertEqual(Path(argv[1]).name, "notify_human.py")
        self.assertEqual(
            argv[2:],
            [
                "--title",
                "Paper download needs your action",
                "--message",
                "Complete the security challenge normally.",
                "--button",
                "OK",
                "--timeout",
                "120",
            ],
        )


if __name__ == "__main__":
    unittest.main()
