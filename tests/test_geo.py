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

from agentshelf.geo import GeoSkillConfig, build_geo_audit, render_geo_json


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentshelf.cli", *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


class GeoSkillTests(unittest.TestCase):
    def test_geo_audit_contract_for_artist_store(self) -> None:
        html = (ROOT / "examples/artist_store_product.html").read_text(encoding="utf-8")
        result = build_geo_audit(
            GeoSkillConfig(
                targetUrl="https://moon-kiln.example/products/calligraphy-teacup",
                brandName="Moon Kiln Studio",
                category="custom handmade teacups",
                vertical="artist_store",
                competitors=["Etsy"],
                personas=["tea lovers"],
                useCases=["meaningful custom gifts"],
            ),
            html,
            robots_text="User-agent: *\nAllow: /\n",
            robots_status="found",
            sitemap_status="found",
            llms_status="missing_or_unavailable",
        )
        payload = json.loads(render_geo_json(result))

        self.assertEqual(payload["rawMetadata"]["contract"], "agentshelf.geo_audit.v0")
        self.assertEqual(payload["storeProfile"]["vertical"], "artist_store")
        self.assertGreaterEqual(len(payload["promptPanel"]), 100)
        self.assertIn("crawlability", payload["categoryScores"])
        self.assertTrue(payload["patchSuggestions"])
        self.assertTrue(any(item["patchType"] == "product_schema" for item in payload["patchSuggestions"]))
        self.assertTrue(any(item["intentBucket"] == "gift" for item in payload["promptPanel"]))
        self.assertIn("# AgentShelf GEO Audit Report", payload["reportMarkdown"])

    def test_geo_audit_detects_crawler_blockers(self) -> None:
        html = (ROOT / "examples/artist_store_product.html").read_text(encoding="utf-8")
        result = build_geo_audit(
            GeoSkillConfig(
                targetUrl="https://moon-kiln.example/products/calligraphy-teacup",
                brandName="Moon Kiln Studio",
                category="custom handmade teacups",
                vertical="artist_store",
            ),
            html,
            robots_text="User-agent: GPTBot\nDisallow: /\nUser-agent: OAI-SearchBot\nDisallow: /\n",
            robots_status="found",
            sitemap_status="found",
        )
        issue_ids = {issue.id for issue in result.issues}

        self.assertIn("crawler_blocked_gptbot", issue_ids)
        self.assertIn("crawler_blocked_oai_searchbot", issue_ids)
        self.assertLess(result.categoryScores["crawlability"], 100)

    def test_geo_audit_cli_json(self) -> None:
        result = _run_cli(
            "geo-audit",
            "examples/artist_store_product.html",
            "--brand",
            "Moon Kiln Studio",
            "--category",
            "custom handmade teacups",
            "--vertical",
            "artist_store",
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["storeProfile"]["brandName"], "Moon Kiln Studio")
        self.assertEqual(payload["pages"][0]["pageType"], "product")
        self.assertGreaterEqual(len(payload["promptPanel"]), 100)

    def test_geo_audit_cli_markdown_and_both_outputs(self) -> None:
        markdown = _run_cli(
            "geo-audit",
            "examples/artist_store_product.html",
            "--brand",
            "Moon Kiln Studio",
            "--category",
            "custom handmade teacups",
            "--vertical",
            "artist_store",
        )
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("## 9. Prompt Panel", markdown.stdout)
        self.assertIn("## 10. Recommended Patches", markdown.stdout)

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "moon-kiln-geo-report"
            both = _run_cli(
                "geo-audit",
                "examples/artist_store_product.html",
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "both",
                "--out",
                str(out),
            )

            self.assertEqual(both.returncode, 0, both.stderr)
            self.assertTrue(out.with_suffix(".md").exists())
            self.assertTrue(out.with_suffix(".json").exists())
            payload = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(payload["rawMetadata"]["contract"], "agentshelf.geo_audit.v0")

    def test_geo_tasks_cli_emits_agent_task_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "geo-report.json"
            tasks = Path(tmpdir) / "geo-tasks.jsonl"
            audit = _run_cli(
                "geo-audit",
                "examples/artist_store_product.html",
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "json",
                "--output",
                str(report),
            )
            self.assertEqual(audit.returncode, 0, audit.stderr)

            result = _run_cli("geo-tasks", str(report), "--output", str(tasks))

            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in tasks.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(rows)
            first = rows[0]
            self.assertEqual(first["contract"], "agentshelf.geo_task.v0")
            self.assertIn("files_or_page_area", first["task"])
            self.assertIn("acceptance_check", first["task"])
            self.assertIn("verification_command", first["task"])
            self.assertIn("agentshelf geo-audit", first["task"]["verification_command"])
            self.assertTrue(any(row["task"].get("patch_type") == "product_schema" for row in rows))

    def test_geo_tasks_cli_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "geo-report.json"
            audit = _run_cli(
                "geo-audit",
                "examples/artist_store_product.html",
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "json",
                "--output",
                str(report),
            )
            self.assertEqual(audit.returncode, 0, audit.stderr)

            result = _run_cli("geo-tasks", str(report), "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract"], "agentshelf.geo_tasks.v0")
            self.assertGreater(payload["task_count"], 0)

    def test_validate_contract_accepts_geo_audit_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "geo-report.json"
            tasks = root / "geo-tasks.jsonl"
            audit = _run_cli(
                "geo-audit",
                "examples/artist_store_product.html",
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "json",
                "--output",
                str(report),
            )
            self.assertEqual(audit.returncode, 0, audit.stderr)
            task_result = _run_cli("geo-tasks", str(report), "--output", str(tasks))
            self.assertEqual(task_result.returncode, 0, task_result.stderr)

            audit_validation = _run_cli("validate-contract", str(report), "--format", "json")
            task_validation = _run_cli("validate-contract", str(tasks), "--contract", "agentshelf.geo_task.v0")

            self.assertEqual(audit_validation.returncode, 0, audit_validation.stderr)
            audit_payload = json.loads(audit_validation.stdout)
            self.assertTrue(audit_payload["valid"])
            self.assertEqual(audit_payload["contract"], "agentshelf.geo_audit.v0")
            self.assertIn("schemas/agentshelf.geo_audit.v0.schema.json", audit_payload["schemas"])
            self.assertEqual(task_validation.returncode, 0, task_validation.stderr)
            self.assertIn("Status: valid", task_validation.stdout)

    def test_validate_contract_rejects_invalid_geo_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad-task.jsonl"
            bad.write_text(
                json.dumps(
                    {
                        "contract": "agentshelf.geo_task.v0",
                        "source": "demo.html",
                        "page_url": "demo.html",
                        "task": {
                            "id": "bad_task",
                            "title": "Bad task",
                            "priority": "urgent",
                            "type": "patch",
                            "reason": "",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = _run_cli("validate-contract", str(bad), "--format", "json")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(any("priority" in error for error in payload["errors"]))
            self.assertTrue(any("files_or_page_area" in error for error in payload["errors"]))

    def test_geo_run_writes_valid_agent_artifact_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "geo-run"
            result = _run_cli(
                "geo-run",
                "examples/artist_store_product.html",
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--output-dir",
                str(output_dir),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract"], "agentshelf.geo_run.v0")
            self.assertTrue(payload["geo_report_validation"]["valid"])
            self.assertTrue(payload["geo_tasks_validation"]["valid"])
            self.assertGreater(payload["task_count"], 0)
            self.assertIsNotNone(payload["scan"])
            for filename in (
                "geo-report.json",
                "geo-report.md",
                "geo-tasks.jsonl",
                "geo-report-validation.json",
                "geo-tasks-validation.json",
                "scan-report.md",
                "summary.json",
            ):
                self.assertTrue((output_dir / filename).exists(), filename)

            tasks = [json.loads(line) for line in (output_dir / "geo-tasks.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row["task"].get("patch_type") == "product_schema" for row in tasks))

    def test_codex_agent_loop_after_fixture_improves_audit_and_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            before_dir = Path(tmpdir) / "before"
            after_dir = Path(tmpdir) / "after"
            common_args = (
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "json",
            )
            before = _run_cli(
                "geo-run",
                "examples/artist_store_product.html",
                *common_args,
                "--output-dir",
                str(before_dir),
            )
            after = _run_cli(
                "geo-run",
                "examples/codex_agent_loop_after.html",
                *common_args,
                "--output-dir",
                str(after_dir),
            )

            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertEqual(after.returncode, 0, after.stderr)
            before_payload = json.loads(before.stdout)
            after_payload = json.loads(after.stdout)
            before_task_ids = {
                row["task"]["id"]
                for row in (json.loads(line) for line in (before_dir / "geo-tasks.jsonl").read_text(encoding="utf-8").splitlines())
            }
            after_task_ids = {
                row["task"]["id"]
                for row in (json.loads(line) for line in (after_dir / "geo-tasks.jsonl").read_text(encoding="utf-8").splitlines())
            }
            after_scan = json.loads(_run_cli("scan", "examples/codex_agent_loop_after.html", "--format", "json").stdout)

            self.assertGreater(after_payload["overallScore"], before_payload["overallScore"])
            self.assertGreater(after_payload["scan"]["score"], before_payload["scan"]["score"])
            self.assertEqual(after_payload["high_impact_issue_count"], 0)
            self.assertIn("missing_product_schema", before_task_ids)
            self.assertIn("missing_offer_schema", before_task_ids)
            self.assertNotIn("missing_product_schema", after_task_ids)
            self.assertNotIn("missing_offer_schema", after_task_ids)
            self.assertEqual(after_scan["band"], "strong")
            self.assertEqual(after_scan["contradictions"], [])


if __name__ == "__main__":
    unittest.main()
