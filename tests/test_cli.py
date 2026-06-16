from __future__ import annotations

import json
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agentshelf import cli


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentshelf.cli", *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
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

    def test_agent_audit_returns_contract_json(self) -> None:
        result = _run_cli("agent-audit", "examples/weak_product_page.html", "--contract", "v1")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract"], "v1")
        self.assertIn("blocking_issues", payload)
        self.assertTrue(payload["agent_tasks"])

    def test_agent_audit_fail_on_blockers(self) -> None:
        result = _run_cli("agent-audit", "examples/weak_product_page.html", "--fail-on-blockers")
        self.assertEqual(result.returncode, 1)

    def test_snapshot_writes_html_from_local_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            page = root / "product.html"
            page.write_text("<html><title>Local Product</title><h1>Local Product</h1></html>", encoding="utf-8")

            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    return

            try:
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local socket binding unavailable in this sandbox: {exc}")
            old_cwd = os.getcwd()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                os.chdir(root)
                thread.start()
                output = root / "snapshot.html"
                url = f"http://127.0.0.1:{server.server_port}/product.html"
                result = _run_cli("snapshot", url, "--output", str(output))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Local Product", output.read_text(encoding="utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                os.chdir(old_cwd)

    def test_rendered_snapshot_missing_extra_has_actionable_error(self) -> None:
        original_import = __import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("playwright"):
                raise ImportError("playwright unavailable")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(ValueError, "agentshelf\\[render\\]"):
                cli._fetch_rendered_url("https://example.com/product")

    def test_rendered_snapshot_uses_playwright_when_available(self) -> None:
        calls: dict[str, object] = {}

        class FakePage:
            def goto(self, url: str, wait_until: str, timeout: int) -> None:
                calls["url"] = url
                calls["wait_until"] = wait_until
                calls["timeout"] = timeout

            def content(self) -> str:
                return "<html><title>Rendered Product</title><div>$19.00</div></html>"

        class FakeBrowser:
            def new_page(self, user_agent: str) -> FakePage:
                calls["user_agent"] = user_agent
                return FakePage()

            def close(self) -> None:
                calls["closed"] = True

        class FakeChromium:
            def launch(self, headless: bool) -> FakeBrowser:
                calls["headless"] = headless
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()

            def __enter__(self) -> "FakePlaywright":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        fake_parent = types.ModuleType("playwright")
        fake_sync_api = types.ModuleType("playwright.sync_api")
        fake_sync_api.Error = RuntimeError
        fake_sync_api.sync_playwright = lambda: FakePlaywright()

        with mock.patch.dict(sys.modules, {"playwright": fake_parent, "playwright.sync_api": fake_sync_api}):
            html = cli._fetch_rendered_url(
                "https://example.com/product",
                timeout=1.5,
                wait_until="domcontentloaded",
            )

        self.assertIn("Rendered Product", html)
        self.assertEqual(calls["url"], "https://example.com/product")
        self.assertEqual(calls["wait_until"], "domcontentloaded")
        self.assertEqual(calls["timeout"], 1500)
        self.assertEqual(calls["closed"], True)

    def test_scan_benchmark_fixtures_as_jsonl(self) -> None:
        result = _run_cli("scan", "benchmarks/fixtures", "--batch", "--format", "jsonl")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertGreaterEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main()
