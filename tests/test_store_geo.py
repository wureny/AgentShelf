from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agentshelf.cli import _public_audit_scan_private_context


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentshelf.cli", *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


class StoreGeoTests(unittest.TestCase):
    def test_store_level_geo_run_writes_report_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "artist-store"
            result = _run_cli(
                "geo-run",
                "--store-snapshot",
                "examples/fixtures/artist-store-before",
                "--store-profile",
                "examples/profiles/artist-store.example.json",
                "--vertical",
                "artist_store",
                "--output-dir",
                str(output_dir),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["contract"], "agentshelf.store_geo_run.v0")
            self.assertTrue(summary["store_report_validation"]["valid"])
            self.assertTrue(summary["geo_tasks_validation"]["valid"])
            self.assertGreater(summary["task_count"], 0)
            for filename in (
                "store-report.json",
                "store-report.md",
                "store-report.html",
                "report.json",
                "report.md",
                "report.html",
                "store-report-validation.json",
                "geo-tasks.jsonl",
                "geo-tasks-validation.json",
                "summary.json",
            ):
                self.assertTrue((output_dir / filename).exists(), filename)

            report = json.loads((output_dir / "store-report.json").read_text(encoding="utf-8"))
            report_alias = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["contract"], "agentshelf.store_geo_audit.v0")
            self.assertEqual(report_alias["contract"], "agentshelf.store_geo_audit.v0")
            self.assertEqual(summary["report"], str(output_dir / "report.json"))
            self.assertGreaterEqual(len(report["pages"]), 8)
            self.assertIn("products/custom-calligraphy-teacup.html", report["pageScores"])
            self.assertIn("crossPageIssues", report)
            self.assertTrue(any(issue["category"] == "commerce_attributes" for issue in report["issues"]))
            self.assertIn("## 1. Executive Summary", report["reportMarkdown"])
            self.assertIn("## 2. Top 10 Prioritized Actions", report["reportMarkdown"])
            self.assertIn("## 11. Limitations", report["reportMarkdown"])
            self.assertIn("does not measure live ChatGPT", "\n".join(report["limitations"]))

            first_task = json.loads((output_dir / "geo-tasks.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(first_task["contract"], "agentshelf.geo_task.v0")
            self.assertIn("acceptanceCriteria", first_task["task"])
            self.assertIn("verification_command", first_task["task"])
            self.assertIn("agentshelf geo-run --store-snapshot", first_task["task"]["verification_command"])
            self.assertNotIn("ranking lift", json.dumps(first_task).lower())

    def test_artist_store_after_improves_deterministic_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            before_dir = Path(tmpdir) / "before"
            after_dir = Path(tmpdir) / "after"
            common = (
                "--store-profile",
                "examples/profiles/artist-store.example.json",
                "--vertical",
                "artist_store",
                "--format",
                "json",
            )
            before = _run_cli("geo-run", "--store-snapshot", "examples/fixtures/artist-store-before", *common, "--output-dir", str(before_dir))
            after = _run_cli("geo-run", "--store-snapshot", "examples/fixtures/artist-store-after", *common, "--output-dir", str(after_dir))

            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertEqual(after.returncode, 0, after.stderr)
            before_payload = json.loads(before.stdout)
            after_payload = json.loads(after.stdout)
            before_report = json.loads((before_dir / "store-report.json").read_text(encoding="utf-8"))
            after_report = json.loads((after_dir / "store-report.json").read_text(encoding="utf-8"))

            self.assertGreater(after_payload["storeScore"], before_payload["storeScore"])
            self.assertGreater(len(before_report["issues"]), len(after_report["issues"]))
            self.assertIn("does not claim ranking lift", "\n".join(after_report["limitations"]))
            self.assertNotIn("aggregateRating", "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "examples/fixtures/artist-store-after").rglob("*.html")))
            self.assertNotIn("reviewRating", "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "examples/fixtures/artist-store-after").rglob("*.html")))

    def test_geo_tasks_accepts_store_level_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            tasks_path = Path(tmpdir) / "tasks.jsonl"
            run = _run_cli(
                "geo-run",
                "--store-snapshot",
                "examples/fixtures/artist-store-before",
                "--store-profile",
                "examples/profiles/artist-store.example.json",
                "--vertical",
                "artist_store",
                "--output-dir",
                str(output_dir),
                "--format",
                "json",
            )
            self.assertEqual(run.returncode, 0, run.stderr)

            tasks = _run_cli("geo-tasks", str(output_dir / "store-report.json"), "--output", str(tasks_path))

            self.assertEqual(tasks.returncode, 0, tasks.stderr)
            rows = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row["contract"] == "agentshelf.geo_task.v0" for row in rows))

    def test_dogfood_fixture_comparison_writes_agent_loop_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "fixture-dogfood"
            result = _run_cli(
                "dogfood",
                "--fixture",
                "artist-store-comparison",
                "--vertical",
                "artist_store",
                "--output-dir",
                str(output_dir),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract"], "agentshelf.fixture_dogfood_comparison.v0")
            self.assertTrue(payload["valid"])
            self.assertGreater(payload["after"]["storeScore"], payload["before"]["storeScore"])
            self.assertLess(payload["after"]["issue_count"], payload["before"]["issue_count"])
            self.assertTrue((output_dir / "comparison.json").exists())
            self.assertTrue((output_dir / "dogfood-notes.md").exists())
            for side in ("before", "after"):
                side_dir = output_dir / side
                self.assertTrue((side_dir / "report.json").exists())
                self.assertTrue((side_dir / "report.md").exists())
                self.assertTrue((side_dir / "report.html").exists())
                self.assertTrue((side_dir / "geo-tasks.jsonl").exists())
                self.assertTrue((side_dir / "dogfood-notes.md").exists())
            notes = (output_dir / "dogfood-notes.md").read_text(encoding="utf-8")
            self.assertIn("does not measure live ChatGPT", notes)
            self.assertIn("Codex remediation", notes)

    def test_public_audit_private_context_rules_are_broad_but_not_placeholder_hostile(self) -> None:
        issues: list[dict] = []
        _public_audit_scan_private_context(
            {
                "bad.md": "Developer note: /home/alix/project and User: alix\n",
                "ok.md": "Use https://example.com and API_KEY=placeholder in local examples.\n",
                "phone.md": "Support example number: 555-0101.\n",
            },
            issues,
        )

        self.assertTrue(any(issue["id"] == "private_home_path" for issue in issues))
        self.assertTrue(any(issue["id"] == "user_record_leak" for issue in issues))
        self.assertFalse(any(issue["path"] == "ok.md" for issue in issues))
        self.assertFalse(any(issue["path"] == "phone.md" for issue in issues))


if __name__ == "__main__":
    unittest.main()
