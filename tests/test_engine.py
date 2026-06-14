from __future__ import annotations

import unittest

from agentshelf.engine import parse_input, render_markdown, scan_readiness


SAMPLE_HTML = """<!doctype html>
<html>
  <head>
    <title>TrailBottle Pro 24oz</title>
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Product","name":"TrailBottle Pro 24oz"}
    </script>
  </head>
  <body>
    <h1>TrailBottle Pro 24oz</h1>
    <p>$39.00</p>
    <p>In stock</p>
    <p>Free shipping in the US</p>
    <p>30-day returns</p>
    <section><h2>Specifications</h2><p>Materials: stainless steel</p></section>
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


if __name__ == "__main__":
    unittest.main()
