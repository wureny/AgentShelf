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
      {"@context":"https://schema.org","@type":"Product","name":"TrailBottle Pro 24oz","offers":{"@type":"Offer","priceCurrency":"USD","price":"39.00","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"TrailCo"},"hasMerchantReturnPolicy":{"@type":"MerchantReturnPolicy","merchantReturnDays":30}}}
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

    def test_shopify_variant_json_counts_as_commerce_evidence(self) -> None:
        html = """<!doctype html>
<html>
  <head><title>Subscription Roast</title></head>
  <body>
    <h1>Subscription Roast</h1>
    <script type="application/json" id="ProductJson-template">
      {
        "title": "Subscription Roast",
        "options": [{"name": "Size"}, {"name": "Grind"}],
        "variants": [
          {"id": 1, "title": "12oz / Whole Bean", "price": 1800, "available": true, "option1": "12oz", "option2": "Whole Bean"},
          {"id": 2, "title": "2lb / Ground", "price": 4200, "available": false, "option1": "2lb", "option2": "Ground"}
        ],
        "selling_plan_groups": [{"name": "Subscribe and save"}],
        "metafields": {"custom.tasting_notes": "cocoa and citrus", "custom.origin": "Colombia"}
      }
    </script>
    <p>Ships every Monday with free shipping over $40.</p>
    <p>Returns accepted for unopened bags within 30 days.</p>
    <p>Rating 4.8/5 from 210 reviews.</p>
    <section><h2>FAQ</h2><p>Choose whole bean or ground.</p></section>
  </body>
</html>"""
        bundle = scan_readiness(parse_input(html))
        checks = {check["id"]: check for check in bundle["checks"]}

        self.assertTrue(checks["price"]["passed"])
        self.assertIn("variant price", checks["price"]["evidence"])
        self.assertTrue(checks["availability"]["passed"])
        self.assertTrue(checks["variant_readiness"]["passed"])
        self.assertTrue(checks["merchant_feed_hints"]["passed"])
        self.assertEqual(bundle["commerce_signals"]["variant_count"], 2)
        self.assertEqual(bundle["commerce_signals"]["selling_plan_group_count"], 1)
        self.assertIn("custom.tasting_notes", bundle["commerce_signals"]["metafield_keys"])
        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["detected"], "shopify")

    def test_incomplete_variant_json_does_not_pass_variant_readiness(self) -> None:
        html = """<html><head><title>Half Wired Variant</title></head><body>
<h1>Half Wired Variant</h1>
<script type="application/json">
{"options":[{"name":"Size"}],"variants":[{"id":1,"title":"Small"},{"id":2,"title":"Large"}]}
</script>
<p>Shipping in 3 days. 30-day returns.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))
        variant_check = next(check for check in bundle["checks"] if check["id"] == "variant_readiness")

        self.assertFalse(variant_check["passed"])
        self.assertIn("incomplete", variant_check["evidence"])
        self.assertEqual(bundle["commerce_signals"]["variant_count"], 2)
        self.assertEqual(bundle["commerce_signals"]["variants_with_price"], 0)

    def test_shopify_assignment_json_is_parsed_with_nested_objects(self) -> None:
        html = """<html><head><title>Analytics Product</title></head><body>
<h1>Analytics Product</h1>
<script>
window.ShopifyAnalytics = window.ShopifyAnalytics || {};
window.ShopifyAnalytics.meta = {
  "product": {
    "options": [{"name": "Color"}],
    "variants": [{"id": 1, "price": 2900, "available": true, "option1": "Blue"}]
  }
};
</script>
<p>Delivery in 2 days. Returns within 30 days. FAQ: color may vary.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))

        self.assertEqual(bundle["commerce_signals"]["variant_count"], 1)
        self.assertEqual(bundle["commerce_signals"]["variants_with_price"], 1)
        self.assertTrue(next(check for check in bundle["checks"] if check["id"] == "variant_readiness")["passed"])

    def test_woocommerce_variation_profile_extracts_variation_data(self) -> None:
        html = """<html><head><title>Woo Hoodie</title></head><body class="single-product woocommerce">
<h1>Woo Hoodie</h1>
<form class="variations_form" data-product_variations='[
  {"variation_id":11,"display_price":49.99,"is_in_stock":true,"attributes":{"attribute_pa_size":"M","attribute_pa_color":"Blue"}},
  {"variation_id":12,"display_price":54.99,"is_in_stock":false,"attributes":{"attribute_pa_size":"L","attribute_pa_color":"Black"}}
]'></form>
<p>Delivery in 4 days. Returns within 30 days. Rating 4.6/5 from 80 reviews. FAQ: washable.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))

        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["detected"], "woocommerce")
        self.assertEqual(bundle["commerce_signals"]["variant_count"], 2)
        self.assertEqual(bundle["commerce_signals"]["variants_with_price"], 2)
        self.assertEqual(bundle["commerce_signals"]["variants_with_availability"], 2)
        self.assertIn("pa_size", bundle["commerce_signals"]["option_names"])
        self.assertTrue(next(check for check in bundle["checks"] if check["id"] == "variant_readiness")["passed"])

    def test_headless_profile_detects_next_data_variants(self) -> None:
        html = """<html><head><title>Headless Pack</title></head><body>
<h1>Headless Pack</h1>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"product":{"options":[{"name":"Pack"}],"variants":[{"id":"v1","price":"19.00","available":true,"option1":"Single"}]}}}}
</script>
<p>Ships tomorrow. Refunds accepted within 14 days. FAQ: compatible with most kits.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))

        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["detected"], "headless")
        self.assertEqual(bundle["commerce_signals"]["variant_count"], 1)
        self.assertTrue(next(check for check in bundle["checks"] if check["id"] == "price")["passed"])

    def test_forced_adapter_profile_overrides_detection(self) -> None:
        bundle = scan_readiness(parse_input("<html><title>Plain</title><h1>Plain</h1></html>"), adapter_profile="shopify")

        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["requested"], "shopify")
        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["detected"], "generic")
        self.assertEqual(bundle["commerce_signals"]["adapter_profile"]["active"], "shopify")

    def test_return_policy_schema_is_detected_inside_offer(self) -> None:
        html = """<html><head><title>Schema Returns</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Schema Returns","offers":{"@type":"Offer","priceCurrency":"USD","price":"29.00","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"Demo"},"hasMerchantReturnPolicy":{"@type":"MerchantReturnPolicy","merchantReturnDays":30}}}
</script></head><body><h1>Schema Returns</h1><p>$29.00. In stock. Free shipping in the US. 30-day returns.</p><p>Specifications: cotton, blue.</p><p>FAQ: washable. Reviews 4.7/5.</p></body></html>"""
        bundle = scan_readiness(parse_input(html))
        check = next(item for item in bundle["checks"] if item["id"] == "return_policy_schema")

        self.assertTrue(check["applicable"])
        self.assertTrue(check["passed"])
        self.assertTrue(bundle["commerce_signals"]["has_return_policy_schema"])

    def test_profile_specific_rule_pack_surfaces_agent_tasks(self) -> None:
        html = """<html><head><title>Subscribe Kit</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Subscribe Kit","offers":{"@type":"Offer","priceCurrency":"USD","price":"89.00","availability":"https://schema.org/InStock","seller":{"@type":"Organization","name":"Demo"}}}
</script></head><body>
<h1>Subscribe Kit Bundle</h1>
<script type="application/json" id="ProductJson-template">
{"options":[{"name":"Plan"}],"variants":[{"id":1,"price":8900,"available":true,"option1":"Monthly"}],"selling_plan_groups":[{"name":"Subscribe and save"}]}
</script>
<p>Bundle price $89.00. In stock. Subscribe and save.</p>
<p>Ships to US and Canada.</p>
<p>30-day returns.</p>
<p>Specifications: starter kit for daily use.</p>
<p>FAQ: works for beginners. Rating 4.8/5 from 50 reviews.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))
        contract = build_agent_contract(bundle)
        task_ids = {task["id"] for task in contract["agent_tasks"]}

        self.assertIn("complete_subscription_terms", task_ids)
        self.assertIn("clarify_bundle_components", task_ids)
        self.assertIn("add_regional_shipping_matrix", task_ids)
        self.assertIn("add_return_policy_schema", task_ids)
        self.assertTrue(next(item for item in bundle["checks"] if item["id"] == "subscription_terms")["applicable"])
        self.assertTrue(next(item for item in bundle["checks"] if item["id"] == "bundle_components")["applicable"])
        self.assertTrue(next(item for item in bundle["checks"] if item["id"] == "regional_shipping_promises")["applicable"])

    def test_profile_specific_rules_are_not_applicable_without_intent(self) -> None:
        bundle = scan_readiness(parse_input("<html><title>Bottle</title><h1>Bottle</h1></html>"))
        checks = {item["id"]: item for item in bundle["checks"]}
        contract = build_agent_contract(bundle)
        blocking_ids = {item["id"] for item in contract["blocking_issues"]}

        self.assertFalse(checks["subscription_terms"]["applicable"])
        self.assertFalse(checks["bundle_components"]["applicable"])
        self.assertFalse(checks["regional_shipping_promises"]["applicable"])
        self.assertNotIn("subscription_terms", blocking_ids)
        self.assertNotIn("bundle_components", blocking_ids)
        self.assertNotIn("regional_shipping_promises", blocking_ids)

    def test_newsletter_subscribe_copy_does_not_trigger_subscription_terms(self) -> None:
        html = """<html><head><title>Studio Mug</title></head><body>
<h1>Studio Mug</h1>
<p>$42.00 USD. In stock. Ships in 3 business days. Returns accepted within 14 days.</p>
<p>Material: stoneware. Capacity: 10 oz.</p>
<p>FAQ: Is it dishwasher safe? Yes.</p>
<p>Subscribe to our newsletter for studio updates and restock alerts.</p>
</body></html>"""
        bundle = scan_readiness(parse_input(html))
        checks = {item["id"]: item for item in bundle["checks"]}
        contract = build_agent_contract(bundle)
        blocking_ids = {item["id"] for item in contract["blocking_issues"]}
        task_ids = {item["id"] for item in contract["agent_tasks"]}

        self.assertFalse(checks["subscription_terms"]["applicable"])
        self.assertNotIn("subscription_terms", blocking_ids)
        self.assertNotIn("complete_subscription_terms", task_ids)


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
            if "profile" in expected:
                profile = bundle["commerce_signals"]["adapter_profile"]
                for key, value in expected["profile"].items():
                    self.assertEqual(profile[key], value, fixture.name)
            if "commerce_signals" in expected:
                for key, value in expected["commerce_signals"].items():
                    self.assertEqual(bundle["commerce_signals"][key], value, fixture.name)


if __name__ == "__main__":
    unittest.main()
