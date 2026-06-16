from __future__ import annotations

import unittest
import json
from pathlib import Path

from agentshelf.engine import build_agent_contract, parse_input, render_markdown, scan_readiness


SAMPLE_HTML = """<!doctype html>
<html>
  <head>
    <title>TrailBottle Pro 24oz</title>
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Product","name":"TrailBottle Pro 24oz","offers":{"@type":"Offer","priceCurrency":"USD","price":"39.00","availability":"https://schema.org/InStock"}}
    </script>
  </head>
  <body>
    <h1>TrailBottle Pro 24oz</h1>
    <p>$39.00</p>
    <p>In stock</p>
    <p>Free shipping in the US</p>
    <p>30-day returns</p>
    <section><h2>Specifications</h2><p>Materials: stainless steel. Size: 24oz. Color: black.</p></section>
    <section><h2>FAQ</h2><p>Can it hold hot drinks?</p></section>
  </body>
</html>
"""


class EngineTests(unittest.TestCase):
    def test_parse_input_uses_title(self) -> None:
        parsed = parse_input(SAMPLE_HTML)
        self.assertEqual(parsed.title, "TrailBottle Pro 24oz")

    def test_scan_readiness_scores_key_signals(self) -> None:
        bundle = scan_readiness(parse_input(SAMPLE_HTML))
        self.assertGreaterEqual(bundle["score"], 80)
        self.assertEqual(bundle["band"], "strong")
        self.assertIn("dimensions", bundle)
        self.assertEqual(set(bundle["dimensions"]), {"discoverability", "offer_clarity", "policy_clarity", "agent_actionability"})
        self.assertTrue(
            any(check["id"] == "schema_product" and check["passed"] for check in bundle["checks"])
        )
        self.assertTrue(any(check["evidence"] for check in bundle["checks"] if check["passed"]))

    def test_weak_page_surfaces_top_fixes(self) -> None:
        bundle = scan_readiness(parse_input("<html><title>Bottle</title><h1>Bottle</h1></html>"))
        self.assertLess(bundle["score"], 40)
        self.assertEqual(bundle["band"], "not_ready")
        self.assertEqual(bundle["top_fixes"][0]["check_id"], "price")

    def test_malformed_jsonld_warns_without_crashing(self) -> None:
        html = """<html><title>Bad Data</title>
<script type="application/ld+json">{"@type":"Product",</script>
<h1>Bad Data</h1></html>"""
        bundle = scan_readiness(parse_input(html))
        self.assertTrue(bundle["warnings"])
        self.assertFalse(
            any(check["id"] == "schema_product" and check["passed"] for check in bundle["checks"])
        )

    def test_render_markdown_contains_sections(self) -> None:
        output = render_markdown(scan_readiness(parse_input(SAMPLE_HTML)))
        self.assertIn("## Summary", output)
        self.assertIn("## Top Fixes", output)

    def test_agent_contract_contains_required_fields(self) -> None:
        bundle = scan_readiness(parse_input("<html><title>Bottle</title><h1>Bottle</h1></html>"))
        contract = build_agent_contract(bundle)
        self.assertEqual(
            set(contract),
            {
                "contract",
                "target",
                "score",
                "band",
                "blocking_issues",
                "agent_tasks",
                "evidence",
                "next_actions",
                "confidence",
                "warnings",
            },
        )
        self.assertTrue(contract["agent_tasks"])
        self.assertIn("acceptance_check", contract["agent_tasks"][0])

    def test_contradiction_checks_catch_visible_schema_mismatch(self) -> None:
        html = """<html><head><title>Conflict</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Conflict","offers":{"@type":"Offer","priceCurrency":"USD","price":"49.00","availability":"https://schema.org/InStock"}}
</script></head><body><h1>Conflict</h1><p>Price: $59.00. Out of stock.</p></body></html>"""
        bundle = scan_readiness(parse_input(html))
        ids = {issue["id"] for issue in bundle["contradictions"]}
        self.assertIn("price_contradiction", ids)
        self.assertIn("availability_contradiction", ids)

    def test_dynamic_placeholder_warns(self) -> None:
        html = """<html><head><title>JS Product</title></head><body>
<div id="__next"></div><script src="a.js"></script><script src="b.js"></script><script src="c.js"></script>
</body></html>"""
        bundle = scan_readiness(parse_input(html))
        self.assertTrue(any("dynamic_rendering_likely" in warning for warning in bundle["warnings"]))


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_expectations_are_stable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        fixture_dir = root / "benchmarks" / "fixtures"
        expected_dir = root / "benchmarks" / "expected"
        fixtures = sorted(fixture_dir.glob("*.html"))
        self.assertGreaterEqual(len(fixtures), 8)
        for fixture in fixtures:
            expected = json.loads((expected_dir / f"{fixture.stem}.json").read_text(encoding="utf-8"))
            bundle = scan_readiness(
                parse_input(
                    fixture.read_text(encoding="utf-8"),
                    fallback_title=fixture.stem,
                    source=str(fixture),
                )
            )
            contract = build_agent_contract(bundle)
            self.assertEqual(bundle["band"], expected["band"], fixture.name)
            issue_ids = {issue["id"] for issue in contract["blocking_issues"]}
            task_ids = {task["id"] for task in contract["agent_tasks"]}
            for issue_id in expected["blocking_issues"]:
                self.assertIn(issue_id, issue_ids, fixture.name)
            for task_id in expected["top_tasks"]:
                self.assertIn(task_id, task_ids, fixture.name)


if __name__ == "__main__":
    unittest.main()
