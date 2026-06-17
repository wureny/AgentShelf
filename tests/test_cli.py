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
    def _scan_bundle_for_diff(self, fixture: str, source: str = "store/products/demo") -> dict:
        bundle = cli._load_scan(ROOT / fixture)
        bundle["page"]["source"] = source
        return bundle

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

    def test_scan_uses_json_config_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "agentshelf.json"
            report = Path(tmpdir) / "report.sarif"
            config.write_text(
                json.dumps({"format": "sarif", "min_score": "70", "output": str(report)}),
                encoding="utf-8",
            )
            result = _run_cli("scan", "examples/weak_product_page.html", "--config", str(config))
            self.assertEqual(result.returncode, 1)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "2.1.0")
            self.assertTrue(payload["runs"][0]["results"])

    def test_scan_profile_can_be_set_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "agentshelf.json"
            report = Path(tmpdir) / "report.json"
            config.write_text(
                json.dumps({"format": "json", "profile": "shopify", "output": str(report)}),
                encoding="utf-8",
            )

            result = _run_cli("scan", "examples/weak_product_page.html", "--config", str(config))

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["commerce_signals"]["adapter_profile"]["requested"], "shopify")
            self.assertEqual(payload["commerce_signals"]["adapter_profile"]["active"], "shopify")

    def test_scan_profile_option_is_in_json_output(self) -> None:
        result = _run_cli("scan", "examples/shopify_variant_product.html", "--profile", "shopify", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["commerce_signals"]["adapter_profile"]["requested"], "shopify")
        self.assertEqual(payload["commerce_signals"]["adapter_profile"]["detected"], "shopify")

    def test_sarif_output_is_parseable(self) -> None:
        result = _run_cli("scan", "examples/weak_product_page.html", "--format", "sarif")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["version"], "2.1.0")
        self.assertEqual(payload["runs"][0]["tool"]["driver"]["name"], "AgentShelf")
        self.assertTrue(payload["runs"][0]["results"])

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

    def test_agent_tasks_jsonl(self) -> None:
        result = _run_cli("agent-tasks", "examples/weak_product_page.html")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(rows)
        self.assertIn("task", rows[0])
        self.assertIn("acceptance_check", rows[0]["task"])

    def test_compare_raw_and_rendered_snapshots_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "raw.html"
            rendered = root / "rendered.html"
            raw.write_text(
                """<html><head><title>JS Product</title></head><body>
<div id="__next"></div><script src="a.js"></script><script src="b.js"></script><script src="c.js"></script>
</body></html>""",
                encoding="utf-8",
            )
            rendered.write_text(
                """<html><head><title>JS Product</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"JS Product","offers":{"@type":"Offer","priceCurrency":"USD","price":"29.00","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"Demo Store"}}}
</script></head><body><h1>JS Product</h1><p>$29.00</p><p>In stock</p><p>Free shipping and 30-day returns.</p><p>Materials: cotton. Size: M. Color: blue.</p><section>FAQ: fits most buyers.</section></body></html>""",
                encoding="utf-8",
            )

            result = _run_cli("compare", str(raw), str(rendered), "--format", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertGreater(payload["delta"]["score"], 0)
            unlocked = {item["check_id"] for item in payload["unlocked_signals"]}
            self.assertIn("price", unlocked)
            self.assertIn("schema_product", unlocked)
            self.assertIn("Use rendered snapshots", payload["agent_recommendation"])

    def test_compare_raw_and_rendered_snapshots_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "raw.html"
            rendered = root / "rendered.html"
            raw.write_text("<html><title>Same</title><p>$10.00</p></html>", encoding="utf-8")
            rendered.write_text("<html><title>Same</title><p>$10.00</p></html>", encoding="utf-8")
            result = _run_cli("compare", str(raw), str(rendered))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# AgentShelf Snapshot Compare", result.stdout)

    def test_compare_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "raw.html"
            rendered = root / "rendered.html"
            output = root / "compare.json"
            raw.write_text("<html><title>Same</title><p>$10.00</p></html>", encoding="utf-8")
            rendered.write_text("<html><title>Same</title><p>$10.00</p></html>", encoding="utf-8")
            result = _run_cli("compare", str(raw), str(rendered), "--format", "json", "--output", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("agent_recommendation", payload)

    def test_diff_reports_improvement_and_resolved_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = root / "baseline.jsonl"
            current = root / "current.jsonl"
            weak = self._scan_bundle_for_diff("examples/weak_product_page.html")
            strong = self._scan_bundle_for_diff("examples/sample_product_page.html")
            baseline.write_text(json.dumps(weak) + "\n", encoding="utf-8")
            current.write_text(json.dumps(strong) + "\n", encoding="utf-8")

            result = _run_cli("diff", str(baseline), str(current), "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["improved_count"], 1)
            self.assertEqual(payload["summary"]["regressed_count"], 0)
            self.assertTrue(payload["improvements"][0]["resolved_blocking_issues"])

    def test_diff_reports_regression_and_new_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = root / "baseline.jsonl"
            current = root / "current.jsonl"
            strong = self._scan_bundle_for_diff("examples/sample_product_page.html")
            weak = self._scan_bundle_for_diff("examples/weak_product_page.html")
            baseline.write_text(json.dumps(strong) + "\n", encoding="utf-8")
            current.write_text(json.dumps(weak) + "\n", encoding="utf-8")

            result = _run_cli("diff", str(baseline), str(current))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# AgentShelf Audit Diff", result.stdout)
            self.assertIn("Regressions", result.stdout)
            self.assertIn("new blockers", result.stdout)

    def test_diff_accepts_json_list_and_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = root / "baseline.json"
            current = root / "current.json"
            output = root / "diff.md"
            weak = self._scan_bundle_for_diff("examples/weak_product_page.html")
            strong = self._scan_bundle_for_diff("examples/sample_product_page.html")
            baseline.write_text(json.dumps([weak]), encoding="utf-8")
            current.write_text(json.dumps([strong]), encoding="utf-8")

            result = _run_cli("diff", str(baseline), str(current), "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# AgentShelf Audit Diff", output.read_text(encoding="utf-8"))

    def test_audit_run_creates_history_and_later_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            product = root / "product.html"
            history = root / "runs"
            report = root / "audit-diff.md"
            tasks = root / "tasks.jsonl"
            product.write_text((ROOT / "examples/sample_product_page.html").read_text(encoding="utf-8"), encoding="utf-8")

            first = _run_cli(
                "audit-run",
                str(product),
                "--history-dir",
                str(history),
                "--report",
                str(report),
                "--tasks-output",
                str(tasks),
                "--format",
                "json",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            first_payload = json.loads(first.stdout)
            self.assertIsNone(first_payload["previous_results"])
            self.assertTrue((history / "current-results.jsonl").exists())
            self.assertTrue(tasks.exists())
            self.assertIn("Baseline created", report.read_text(encoding="utf-8"))

            product.write_text((ROOT / "examples/weak_product_page.html").read_text(encoding="utf-8"), encoding="utf-8")
            second = _run_cli(
                "audit-run",
                str(product),
                "--history-dir",
                str(history),
                "--report",
                str(report),
                "--format",
                "json",
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            second_payload = json.loads(second.stdout)
            self.assertEqual(second_payload["diff"]["regressed_count"], 1)
            self.assertTrue((history / "previous-results.jsonl").exists())
            self.assertGreaterEqual(len(list(history.glob("results-*.jsonl"))), 2)
            self.assertIn("Regressions", report.read_text(encoding="utf-8"))

    def test_audit_run_threshold_failure_still_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            product = root / "product.html"
            history = root / "runs"
            product.write_text((ROOT / "examples/weak_product_page.html").read_text(encoding="utf-8"), encoding="utf-8")

            result = _run_cli(
                "audit-run",
                str(product),
                "--history-dir",
                str(history),
                "--min-score",
                "70",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["threshold_failed"])
            self.assertTrue((history / "current-results.jsonl").exists())
            self.assertTrue((history / "audit-diff.md").exists())

    def test_calibrate_from_html_batch_exports_anonymized_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            page = root / "merchant-product.html"
            page.write_text(
                """<html><head><title>Merchant Product</title></head><body>
<h1>Merchant Product Bundle</h1>
<p>Contact founder@realbrand.example or visit https://realbrand.example/products/bundle.</p>
<p>Bundle price $89.00. In stock. Subscribe and save.</p>
<p>Ships to US and Canada.</p>
<p>30-day returns.</p>
<script type="application/json" id="ProductJson-template">
{"options":[{"name":"Plan"}],"variants":[{"id":1,"price":8900,"available":true,"option1":"Monthly"}],"selling_plan_groups":[{"name":"Subscribe and save"}]}
</script>
</body></html>""",
                encoding="utf-8",
            )
            fixtures = root / "fixtures"

            result = _run_cli(
                "calibrate",
                str(root),
                "--batch",
                "--format",
                "json",
                "--export-fixtures",
                str(fixtures),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract"], "agentshelf.calibration.v1")
            self.assertEqual(payload["summary"]["review_pages"], 1)
            self.assertIn("profile_rule_review", payload["summary"]["category_counts"])
            self.assertTrue(payload["fixture_export"])
            exported = next(item for item in payload["fixture_export"] if item["status"] == "exported")
            html = Path(exported["fixture"]).read_text(encoding="utf-8")
            self.assertIn("merchant@example.com", html)
            self.assertIn("https://example.com/product", html)
            self.assertNotIn("founder@realbrand.example", html)
            self.assertNotIn("realbrand.example/products", html)

    def test_calibrate_from_scan_results_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result_file = root / "results.jsonl"
            scan = _run_cli("scan", "benchmarks/fixtures/profile_rule_gap_product.html", "--format", "jsonl")
            self.assertEqual(scan.returncode, 0, scan.stderr)
            result_file.write_text(scan.stdout, encoding="utf-8")

            result = _run_cli("calibrate", str(result_file), "--from-results", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["pages"], 1)
            self.assertIn("policy_schema_review", payload["summary"]["category_counts"])
            self.assertTrue(payload["agent_next_actions"])

    def test_discover_reads_robots_sitemap_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    return

            try:
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local socket binding unavailable in this sandbox: {exc}")

            base = f"http://127.0.0.1:{server.server_port}"
            (root / "robots.txt").write_text(f"Sitemap: {base}/sitemap-index.xml\n", encoding="utf-8")
            (root / "sitemap-index.xml").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>{base}/products-sitemap.xml</loc></sitemap>
</sitemapindex>""",
                encoding="utf-8",
            )
            (root / "products-sitemap.xml").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/products/hydrated-tee</loc></url>
  <url><loc>{base}/products/hidden-sale</loc></url>
  <url><loc>{base}/blogs/story</loc></url>
</urlset>""",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                os.chdir(root)
                thread.start()
                result = _run_cli("discover", "--site", base, "--exclude", "hidden", "--format", "json")
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["count"], 1)
                self.assertEqual(payload["urls"], [f"{base}/products/hydrated-tee"])
                self.assertIn(f"{base}/sitemap-index.xml", payload["source"]["sitemaps_checked"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                os.chdir(old_cwd)

    def test_discover_from_explicit_sitemap_text_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    return

            try:
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local socket binding unavailable in this sandbox: {exc}")

            base = f"http://127.0.0.1:{server.server_port}"
            (root / "sitemap.xml").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/products/hydrated-tee</loc></url>
</urlset>""",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                os.chdir(root)
                thread.start()
                result = _run_cli("discover", "--sitemap", f"{base}/sitemap.xml")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), f"{base}/products/hydrated-tee")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                os.chdir(old_cwd)

    def test_discover_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: str, *args: object) -> None:
                    return

            try:
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local socket binding unavailable in this sandbox: {exc}")

            base = f"http://127.0.0.1:{server.server_port}"
            (root / "sitemap.xml").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{base}/products/hydrated-tee</loc></url>
</urlset>""",
                encoding="utf-8",
            )

            old_cwd = os.getcwd()
            output = root / "product-urls.txt"
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                os.chdir(root)
                thread.start()
                result = _run_cli("discover", "--sitemap", f"{base}/sitemap.xml", "--output", str(output))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(encoding="utf-8").strip(), f"{base}/products/hydrated-tee")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                os.chdir(old_cwd)

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

    def test_snapshot_url_file_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            page_one = root / "one.html"
            page_two = root / "two.html"
            page_one.write_text("<html><title>One</title></html>", encoding="utf-8")
            page_two.write_text("<html><title>Two</title></html>", encoding="utf-8")

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
                urls = root / "urls.txt"
                urls.write_text(
                    f"http://127.0.0.1:{server.server_port}/one.html\n"
                    f"http://127.0.0.1:{server.server_port}/two.html\n",
                    encoding="utf-8",
                )
                output_dir = root / "snapshots"
                manifest = root / "manifest.json"
                result = _run_cli(
                    "snapshot",
                    "--url-file",
                    str(urls),
                    "--output-dir",
                    str(output_dir),
                    "--manifest",
                    str(manifest),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(len(payload["snapshots"]), 2)
                self.assertTrue(all(Path(item["path"]).exists() for item in payload["snapshots"]))
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
