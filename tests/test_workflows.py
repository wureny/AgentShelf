from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowArtifactTests(unittest.TestCase):
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
