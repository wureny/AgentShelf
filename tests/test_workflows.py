from __future__ import annotations

import json
import os
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
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        check=False,
    )


class WorkflowArtifactTests(unittest.TestCase):
    def test_action_metadata_is_marketplace_ready_and_writes_step_summary(self) -> None:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")

        required_snippets = [
            "description: CI gate for product pages",
            "author: Alix",
            "branding:",
            "icon: check-circle",
            "color: green",
            "GITHUB_STEP_SUMMARY",
            "AgentShelf commerce audit",
            "agent-tasks",
            "exit \"$status\"",
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, action)

    def test_copyable_pr_gate_workflow_uses_pinned_action_and_artifact_upload(self) -> None:
        workflow = (ROOT / "docs/workflows/agentshelf-pr-gate.yml").read_text(encoding="utf-8")

        required_snippets = [
            "uses: wureny/AgentShelf@v0.1.0",
            "actions/setup-python@v5",
            "python-version: \"3.11\"",
            "path: \"snapshots/**/*.html\"",
            "fail-on: not_ready",
            "actions/upload-artifact@v4",
            "if: always()",
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, workflow)

    def test_artifact_workflow_exports_review_and_agent_outputs(self) -> None:
        workflow = (ROOT / ".github/workflows/agentshelf-artifacts.yml").read_text(encoding="utf-8")

        required_snippets = [
            "agentshelf scan",
            "--format sarif",
            "agentshelf-results.sarif",
            "--format jsonl",
            "agentshelf-results.jsonl",
            "agentshelf agent-tasks",
            "agentshelf-tasks.jsonl",
            "agentshelf calibrate",
            "calibration-report.json",
            "agentshelf dashboard",
            "calibration-dashboard.html",
            "agentshelf draft-labels",
            "draft-calibration-labels.json",
            "github/codeql-action/upload-sarif",
            "actions/upload-artifact",
            "render-fixtures",
            "import-tasks.jsonl",
            "render-fixtures-manifest.json",
            "render-fixtures-summary.json",
            "AGENTSHELF_SCAN_PATH",
            "Enforce AgentShelf score gate",
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, workflow)

    def test_artifact_workflow_defers_gate_until_after_uploads(self) -> None:
        workflow = (ROOT / ".github/workflows/agentshelf-artifacts.yml").read_text(encoding="utf-8")

        scan_index = workflow.index("Scan pages for SARIF gate")
        upload_index = workflow.index("Upload AgentShelf review artifacts")
        gate_index = workflow.index("Enforce AgentShelf score gate")

        self.assertLess(scan_index, upload_index)
        self.assertLess(upload_index, gate_index)
        self.assertIn("scan_status=$scan_status", workflow)
        self.assertIn("import_status=$import_status", workflow)
        self.assertIn("if: always()", workflow)

    def test_artifact_workflow_supports_catalog_import_tasks(self) -> None:
        workflow = (ROOT / ".github/workflows/agentshelf-artifacts.yml").read_text(encoding="utf-8")

        self.assertIn("catalog:", workflow)
        self.assertIn("input_format:", workflow)
        self.assertIn("fixture_platform:", workflow)
        self.assertIn("fail_on_import_warnings:", workflow)
        self.assertIn("--tasks-output \"$AGENTSHELF_ARTIFACT_DIR/import-tasks.jsonl\"", workflow)
        self.assertIn("generated-snapshots", workflow)
        self.assertIn("AgentShelf import validation gate failed", workflow)

    def test_repo_local_geo_skill_documents_agent_workflow(self) -> None:
        skill = (ROOT / "skills/agentshelf-geo/SKILL.md").read_text(encoding="utf-8")
        contract = (ROOT / "skills/agentshelf-geo/references/task-contract.md").read_text(encoding="utf-8")
        metadata = (ROOT / "skills/agentshelf-geo/agents/openai.yaml").read_text(encoding="utf-8")

        required_skill_snippets = [
            "name: agentshelf-geo",
            "agentshelf geo-audit",
            "agentshelf geo-tasks",
            "agentshelf geo-run",
            "agentshelf scan",
            "Do not fabricate reviews",
            "audit and remediation loop",
        ]
        for snippet in required_skill_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, skill)

        self.assertIn("agentshelf.geo_task.v0", contract)
        self.assertIn("files_or_page_area", contract)
        self.assertIn("acceptance_check", contract)
        self.assertIn("$agentshelf-geo", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_packaged_geo_skill_matches_repo_local_skill(self) -> None:
        package_root = ROOT / "src/agentshelf/skills/agentshelf-geo"
        for relative in ("SKILL.md", "agents/openai.yaml", "references/task-contract.md"):
            with self.subTest(relative=relative):
                self.assertEqual(
                    (ROOT / "skills/agentshelf-geo" / relative).read_text(encoding="utf-8"),
                    (package_root / relative).read_text(encoding="utf-8"),
                )

    def test_skill_info_reports_packaged_agent_workflow(self) -> None:
        result = _run_cli("skill-info", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract"], "agentshelf.skill_info.v0")
        self.assertEqual(payload["skill"], "agentshelf-geo")
        self.assertTrue(payload["valid"])
        self.assertIn("SKILL.md", payload["bundled_files"])
        self.assertIn("agentshelf geo-run", payload["primary_workflow_command"])

    def test_export_skill_writes_codex_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli("export-skill", "--output-dir", tmpdir, "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract"], "agentshelf.skill_export.v0")
            self.assertTrue(payload["valid"])
            destination = Path(payload["destination"])
            self.assertEqual(destination, Path(tmpdir) / "agentshelf-geo")
            self.assertTrue((destination / "SKILL.md").exists())
            self.assertTrue((destination / "agents/openai.yaml").exists())
            self.assertTrue((destination / "references/task-contract.md").exists())

    def test_geo_contract_schemas_are_published(self) -> None:
        audit_schema = json.loads((ROOT / "schemas/agentshelf.geo_audit.v0.schema.json").read_text(encoding="utf-8"))
        task_schema = json.loads((ROOT / "schemas/agentshelf.geo_task.v0.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(audit_schema["properties"]["rawMetadata"]["properties"]["contract"]["const"], "agentshelf.geo_audit.v0")
        self.assertIn("categoryScores", audit_schema["required"])
        self.assertEqual(task_schema["properties"]["contract"]["const"], "agentshelf.geo_task.v0")
        self.assertIn("acceptance_check", task_schema["properties"]["task"]["required"])
