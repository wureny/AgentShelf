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

    def test_issue_and_pr_templates_capture_oss_support_boundaries(self) -> None:
        bug = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(encoding="utf-8")
        adoption = (ROOT / ".github/ISSUE_TEMPLATE/merchant_adoption.yml").read_text(encoding="utf-8")
        feature = (ROOT / ".github/ISSUE_TEMPLATE/feature_request.yml").read_text(encoding="utf-8")
        config = (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
        pr_template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")

        required = {
            "bug": ("AgentShelf version or commit", "Command or workflow step", "Minimal fixture or sanitized excerpt", "I removed secrets"),
            "adoption": ("Merchant adoption help", "adoption-check", "not a hosted crawler", "I will not use AgentShelf tasks to fabricate"),
            "feature": ("Feature request", "coding-agent workflow", "unverified claims", "merchant-confirmed facts"),
            "config": ("blank_issues_enabled: false", "Security vulnerability", "Release checklist"),
            "pr": ("Verification", "AgentShelf boundaries", "I did not fabricate", "docs/releases/"),
        }
        texts = {"bug": bug, "adoption": adoption, "feature": feature, "config": config, "pr": pr_template}
        for name, snippets in required.items():
            for snippet in snippets:
                with self.subTest(template=name, snippet=snippet):
                    self.assertIn(snippet, texts[name])

    def test_copyable_pr_gate_workflow_uses_pinned_action_and_artifact_upload(self) -> None:
        workflow = (ROOT / "docs/workflows/agentshelf-pr-gate.yml").read_text(encoding="utf-8")

        required_snippets = [
            "uses: wureny/AgentShelf@v0.36.0",
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
            "agentshelf dogfood",
            "agentshelf scan",
            "Do not fabricate reviews",
            "audit and remediation loop",
            "docs/AGENT_IMPLEMENTATION_LOOP.md",
            "references/agent-loop-example.md",
        ]
        for snippet in required_skill_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, skill)

        self.assertIn("agentshelf.geo_task.v0", contract)
        self.assertIn("files_or_page_area", contract)
        self.assertIn("acceptance_check", contract)
        self.assertIn("$agentshelf-geo", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_agent_implementation_loop_docs_are_executable(self) -> None:
        docs = (ROOT / "docs/AGENT_IMPLEMENTATION_LOOP.md").read_text(encoding="utf-8")
        reference = (ROOT / "skills/agentshelf-geo/references/agent-loop-example.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        required_snippets = [
            "agentshelf geo-run examples/artist_store_product.html",
            "agentshelf geo-run examples/codex_agent_loop_after.html",
            "agentshelf scan examples/codex_agent_loop_after.html --format markdown --min-score 90",
            "agentshelf export-skill --output-dir .codex/skills",
            "Do not fabricate reviews",
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, docs)
                self.assertIn(snippet, reference)
        self.assertIn("docs/AGENT_IMPLEMENTATION_LOOP.md", readme)
        self.assertIn("examples/codex_agent_loop_after.html", readme)

    def test_real_page_dogfood_docs_define_no_raw_html_policy(self) -> None:
        docs = (ROOT / "docs/DOGFOODING.md").read_text(encoding="utf-8")

        required_snippets = [
            "agentshelf dogfood",
            "raw_html_persisted: false",
            "Do not commit",
            "synthetic fixture",
            "raw third-party HTML",
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, docs)

    def test_packaged_geo_skill_matches_repo_local_skill(self) -> None:
        package_root = ROOT / "src/agentshelf/skills/agentshelf-geo"
        for relative in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/task-contract.md",
            "references/agent-loop-example.md",
        ):
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
        self.assertIn("agentshelf dogfood", payload["safe_url_workflow_command"])

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
            self.assertTrue((destination / "references/agent-loop-example.md").exists())

    def test_init_merchant_repo_writes_workflow_snapshot_and_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
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
            root = Path(tmpdir)
            workflow = (root / ".github/workflows/agentshelf-geo.yml").read_text(encoding="utf-8")
            onboarding = (root / "docs/agentshelf-onboarding.md").read_text(encoding="utf-8")
            snapshot = root / "snapshots/agentshelf-demo-product.html"

            self.assertEqual(payload["contract"], "agentshelf.merchant_repo_init.v0")
            self.assertTrue(payload["valid"])
            self.assertTrue((root / ".agentshelf.json").exists())
            self.assertTrue(snapshot.exists())
            self.assertTrue((root / ".codex/skills/agentshelf-geo/SKILL.md").exists())
            self.assertTrue((root / ".codex/skills/agentshelf-geo/references/agent-loop-example.md").exists())
            self.assertEqual(payload["install_ref"], "main")
            self.assertIn("github.event.inputs.product_page", workflow)
            self.assertIn("agentshelf geo-run", workflow)
            self.assertIn("agentshelf agent-tasks", workflow)
            self.assertIn("\\$agentshelf-geo", workflow)
            self.assertIn("AgentShelf.git@main", workflow)
            self.assertIn("AgentShelf.git@main", onboarding)
            self.assertIn("Moon Kiln Studio", onboarding)
            self.assertIn("agentshelf adoption-check .", onboarding)

            scan = _run_cli("scan", str(snapshot), "--format", "json", "--min-score", "70")
            self.assertEqual(scan.returncode, 0, scan.stderr)
            scan_payload = json.loads(scan.stdout)
            self.assertGreaterEqual(scan_payload["score"], 70)

    def test_init_merchant_repo_can_pin_release_install_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
                "--install-ref",
                "v0.36.0",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            root = Path(tmpdir)
            workflow = (root / ".github/workflows/agentshelf-geo.yml").read_text(encoding="utf-8")
            onboarding = (root / "docs/agentshelf-onboarding.md").read_text(encoding="utf-8")

            self.assertEqual(payload["install_ref"], "v0.36.0")
            self.assertIn("AgentShelf.git@v0.36.0", workflow)
            self.assertIn("AgentShelf.git@v0.36.0", onboarding)
            self.assertNotIn("AgentShelf.git@main", workflow)

    def test_init_merchant_repo_rejects_unsafe_install_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
                "--install-ref",
                "main;curl bad",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("--install-ref", result.stderr)

    def test_adoption_check_validates_initialized_merchant_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
                "--brand",
                "Moon Kiln Studio",
                "--category",
                "custom handmade teacups",
                "--vertical",
                "artist_store",
                "--format",
                "json",
            )
            self.assertEqual(init.returncode, 0, init.stderr)

            result = _run_cli(
                "adoption-check",
                tmpdir,
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
            self.assertEqual(payload["contract"], "agentshelf.adoption_check.v0")
            self.assertTrue(payload["valid"])
            self.assertTrue(payload["surfaces"]["config"]["exists"])
            self.assertTrue(payload["surfaces"]["workflow"]["exists"])
            self.assertTrue(payload["surfaces"]["skill"]["exists"])
            self.assertGreaterEqual(payload["scan"]["score"], 70)
            self.assertIn(payload["scan"]["band"], {"workable", "strong"})
            self.assertGreaterEqual(payload["geo"]["task_count"], 0)

    def test_shopify_rendered_snapshot_can_pass_merchant_adoption_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
                "--brand",
                "North Ridge Supply",
                "--category",
                "outdoor bottles",
                "--vertical",
                "commerce",
                "--format",
                "json",
            )
            self.assertEqual(init.returncode, 0, init.stderr)

            render = _run_cli(
                "render-fixtures",
                "examples/shopify-products.json",
                "--input-format",
                "shopify",
                "--platform",
                "shopify",
                "--output-dir",
                str(root / "snapshots/shopify"),
                "--manifest",
                str(root / "snapshots/shopify/manifest.json"),
                "--format",
                "json",
            )
            self.assertEqual(render.returncode, 0, render.stderr)

            result = _run_cli(
                "adoption-check",
                tmpdir,
                "--snapshot",
                "snapshots/shopify/trailbottle-pro-24oz.shopify.html",
                "--brand",
                "North Ridge Supply",
                "--category",
                "outdoor bottles",
                "--vertical",
                "commerce",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(
                Path(payload["scan"]["path"]).resolve(),
                (root / "snapshots/shopify/trailbottle-pro-24oz.shopify.html").resolve(),
            )
            self.assertGreaterEqual(payload["scan"]["score"], 85)
            self.assertGreaterEqual(payload["geo"]["task_count"], 0)

    def test_headless_rendered_snapshot_can_pass_merchant_adoption_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            init = _run_cli(
                "init-merchant-repo",
                "--output-dir",
                tmpdir,
                "--brand",
                "North Ridge Supply",
                "--category",
                "outdoor bottles",
                "--vertical",
                "commerce",
                "--format",
                "json",
            )
            self.assertEqual(init.returncode, 0, init.stderr)

            render = _run_cli(
                "render-fixtures",
                "examples/headless-catalog.json",
                "--input-format",
                "headless",
                "--platform",
                "headless",
                "--output-dir",
                str(root / "snapshots/headless"),
                "--manifest",
                str(root / "snapshots/headless/manifest.json"),
                "--format",
                "json",
            )
            self.assertEqual(render.returncode, 0, render.stderr)

            result = _run_cli(
                "adoption-check",
                tmpdir,
                "--snapshot",
                "snapshots/headless/trailbottle-pro-24oz.headless.html",
                "--brand",
                "North Ridge Supply",
                "--category",
                "outdoor bottles",
                "--vertical",
                "commerce",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual(
                Path(payload["scan"]["path"]).resolve(),
                (root / "snapshots/headless/trailbottle-pro-24oz.headless.html").resolve(),
            )
            self.assertGreaterEqual(payload["scan"]["score"], 85)
            self.assertGreaterEqual(payload["geo"]["task_count"], 0)

    def test_adoption_check_requires_codex_skill_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init = _run_cli("init-merchant-repo", "--output-dir", tmpdir, "--no-skill", "--format", "json")
            self.assertEqual(init.returncode, 0, init.stderr)

            result = _run_cli("adoption-check", tmpdir, "--format", "json")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(any(".codex/skills/agentshelf-geo/SKILL.md" in issue for issue in payload["issues"]))

    def test_init_merchant_repo_detects_conflicts_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".agentshelf.json").write_text('{"custom": true}\n', encoding="utf-8")
            result = _run_cli("init-merchant-repo", "--output-dir", tmpdir, "--format", "json")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(any(path.endswith(".agentshelf.json") for path in payload["conflicts"]))
            self.assertEqual((root / ".agentshelf.json").read_text(encoding="utf-8"), '{"custom": true}\n')

    def test_public_audit_validates_public_release_hygiene(self) -> None:
        result = _run_cli("public-audit", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract"], "agentshelf.public_audit.v0")
        self.assertTrue(payload["valid"])
        self.assertIn("README.md", payload["checked_files"])
        self.assertIn("docs/PUBLIC_RELEASE_AUDIT.md", payload["checked_files"])
        self.assertIn("skills/agentshelf-geo/SKILL.md", payload["checked_files"])
        self.assertEqual(payload["summary"]["issues"], 0)
        self.assertEqual(payload["summary"]["warnings"], 0)
        self.assertFalse(any(warning["id"] == "temporary_main_install" for warning in payload["warnings"]))
        self.assertFalse(any(warning["id"] == "generated_file_present" for warning in payload["warnings"]))

    def test_public_audit_fails_on_private_context_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for relative in (
                "README.md",
                "LICENSE",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "CODE_OF_CONDUCT.md",
                "CHANGELOG.md",
                "STATUS.md",
                "pyproject.toml",
                "action.yml",
                ".github/pull_request_template.md",
                ".github/ISSUE_TEMPLATE/bug_report.yml",
                ".github/ISSUE_TEMPLATE/merchant_adoption.yml",
                ".github/ISSUE_TEMPLATE/feature_request.yml",
                ".github/ISSUE_TEMPLATE/config.yml",
                ".github/workflows/ci.yml",
                ".github/workflows/agentshelf-artifacts.yml",
                "docs/ARCHITECTURE.md",
                "docs/RELEASING.md",
                "docs/PUBLIC_RELEASE_AUDIT.md",
                "docs/releases/v0.36.0.md",
                "docs/MERCHANT_ADOPTION.md",
                "docs/PLATFORM_ADOPTION.md",
                "docs/AGENT_IMPLEMENTATION_LOOP.md",
                "docs/DOGFOODING.md",
                "docs/geo-skill.md",
                "docs/store-level-audit.md",
                "docs/dogfood-artist-store.md",
                "docs/workflows/agentshelf-pr-gate.yml",
                "skills/agentshelf-geo/SKILL.md",
                "skills/agentshelf-geo/agents/openai.yaml",
                "skills/agentshelf-geo/references/task-contract.md",
                "skills/agentshelf-geo/references/agent-loop-example.md",
                "schemas/agentshelf.geo_audit.v0.schema.json",
                "schemas/agentshelf.geo_task.v0.schema.json",
                "schemas/agentshelf.store_geo_audit.v0.schema.json",
                "src/agentshelf/templates/merchant-repo/docs/agentshelf-onboarding.md",
                "src/agentshelf/templates/merchant-repo/workflows/agentshelf-geo.yml",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("placeholder\n", encoding="utf-8")
            (root / "README.md").write_text(
                "Production Posture\nWho It Helps\nagentshelf geo-run\nagentshelf export-skill\n"
                "agentshelf init-merchant-repo\nagentshelf adoption-check\nagentshelf public-audit\n"
                "does not claim live visibility lift\nDo not fabricate\n/Users/alix/private\n",
                encoding="utf-8",
            )
            result = _run_cli("public-audit", tmpdir, "--format", "json")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(any(issue["id"] == "private_user_path" for issue in payload["issues"]))

    def test_release_check_validates_release_surfaces(self) -> None:
        result = _run_cli("release-check", "--expected-version", "0.36.0", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract"], "agentshelf.release_check.v0")
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["version"], "0.36.0")
        self.assertIn("README.md", payload["checked_files"])
        self.assertIn("docs/MERCHANT_ADOPTION.md", payload["checked_files"])
        self.assertIn("docs/PLATFORM_ADOPTION.md", payload["checked_files"])
        self.assertIn("docs/PUBLIC_RELEASE_AUDIT.md", payload["checked_files"])
        self.assertIn("docs/releases/v0.36.0.md", payload["checked_files"])
        self.assertIn("src/agentshelf/templates/merchant-repo/workflows/agentshelf-geo.yml", payload["checked_files"])

    def test_release_check_fails_on_wrong_expected_version(self) -> None:
        result = _run_cli("release-check", "--expected-version", "9.99.0", "--format", "json")

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(any("Expected version 9.99.0" in issue for issue in payload["issues"]))

    def test_release_check_fails_when_committed_release_draft_drifts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            for relative in (
                "pyproject.toml",
                "src/agentshelf/__init__.py",
                "src/agentshelf/cli.py",
                "CHANGELOG.md",
                "README.md",
                "action.yml",
                "docs/workflows/agentshelf-pr-gate.yml",
                "docs/PUBLIC_RELEASE_AUDIT.md",
                "docs/releases/v0.36.0.md",
                "docs/MERCHANT_ADOPTION.md",
                "docs/PLATFORM_ADOPTION.md",
                "docs/geo-skill.md",
                "docs/store-level-audit.md",
                "docs/dogfood-artist-store.md",
                "skills/agentshelf-geo/SKILL.md",
                "skills/agentshelf-geo/references/agent-loop-example.md",
                "src/agentshelf/templates/merchant-repo/workflows/agentshelf-geo.yml",
            ):
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")
            (source / "docs/releases/v0.36.0.md").write_text("# Drifted release notes\n", encoding="utf-8")

            result = _run_cli("release-check", "--root", tmpdir, "--expected-version", "0.36.0", "--format", "json")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["valid"])
            self.assertTrue(any("docs/releases/v0.36.0.md does not match generated release notes" in issue for issue in payload["issues"]))

    def test_release_notes_generates_reviewable_markdown(self) -> None:
        result = _run_cli("release-notes", "--version", "0.36.0")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# AgentShelf v0.36.0", result.stdout)
        self.assertIn("## What changed", result.stdout)
        self.assertIn("public-audit", result.stdout)
        self.assertIn("docs/releases/v0.36.0.md", result.stdout)
        self.assertIn("agentshelf init-merchant-repo", result.stdout)
        self.assertIn("agentshelf adoption-check", result.stdout)
        self.assertIn("agentshelf public-audit .", result.stdout)
        self.assertIn("agentshelf release-check --expected-version 0.36.0", result.stdout)
        self.assertIn("Production posture", result.stdout)
        self.assertIn("Not a hosted crawler", result.stdout)
        self.assertIn("Before publishing", result.stdout)

    def test_release_notes_json_contract_is_stable(self) -> None:
        result = _run_cli("release-notes", "--version", "0.36.0", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract"], "agentshelf.release_notes.v0")
        self.assertEqual(payload["version"], "0.36.0")
        self.assertEqual(payload["title"], "AgentShelf v0.36.0")
        self.assertTrue(payload["valid"])
        self.assertTrue(any("public-audit" in item for item in payload["changelog_items"]))
        self.assertIn("wureny/AgentShelf@v0.36.0", payload["markdown"])

    def test_release_notes_fails_on_wrong_version(self) -> None:
        result = _run_cli("release-notes", "--version", "9.99.0", "--format", "json")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Requested version 9.99.0", result.stderr)

    def test_geo_contract_schemas_are_published(self) -> None:
        audit_schema = json.loads((ROOT / "schemas/agentshelf.geo_audit.v0.schema.json").read_text(encoding="utf-8"))
        task_schema = json.loads((ROOT / "schemas/agentshelf.geo_task.v0.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(audit_schema["properties"]["rawMetadata"]["properties"]["contract"]["const"], "agentshelf.geo_audit.v0")
        self.assertIn("categoryScores", audit_schema["required"])
        self.assertEqual(task_schema["properties"]["contract"]["const"], "agentshelf.geo_task.v0")
        self.assertIn("acceptance_check", task_schema["properties"]["task"]["required"])
