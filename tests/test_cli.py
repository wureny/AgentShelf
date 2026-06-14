from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentshelf.cli", *args],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_single_markdown_scan(self) -> None:
        result = _run_cli("scan", "examples/sample_product_page.html", "--format", "markdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# AgentShelf Report", result.stdout)

    def test_json_scan_is_parseable(self) -> None:
        result = _run_cli("scan", "examples/weak_product_page.html", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("top_fixes", payload)
        self.assertEqual(payload["band"], "not_ready")

    def test_batch_jsonl_scan(self) -> None:
        result = _run_cli("scan", "examples", "--batch", "--format", "jsonl")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertGreaterEqual(len(rows), 2)

    def test_min_score_returns_non_zero(self) -> None:
        result = _run_cli("scan", "examples/weak_product_page.html", "--min-score", "70")
        self.assertEqual(result.returncode, 1)

    def test_output_file_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "report.md"
            result = _run_cli(
                "scan",
                "examples/sample_product_page.html",
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# AgentShelf Report", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
