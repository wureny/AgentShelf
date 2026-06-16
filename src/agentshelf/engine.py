from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


CHECKS = [
    {
        "id": "product_title",
        "label": "Clear product title",
        "weight": 10,
        "dimension": "discoverability",
        "agent_impact": "Agents need a stable product name to identify, compare, and cite the item.",
        "success": "A shopping agent can identify the item name from page chrome or main heading.",
        "failure": "Add a single unambiguous product title in the page title and primary heading.",
    },
    {
        "id": "price",
        "label": "Explicit price",
        "weight": 15,
        "dimension": "offer_clarity",
        "agent_impact": "Agents cannot make purchase recommendations when price is hidden or ambiguous.",
        "success": "Price appears directly in page text or Product offer metadata.",
        "failure": "Expose a machine-readable price near the purchase controls.",
    },
    {
        "id": "availability",
        "label": "Availability or inventory state",
        "weight": 12,
        "dimension": "offer_clarity",
        "agent_impact": "Agents need stock state to avoid recommending unavailable products.",
        "success": "Inventory state is stated in visible text or Product offer metadata.",
        "failure": "State whether the item is in stock, backordered, or unavailable.",
    },
    {
        "id": "shipping",
        "label": "Shipping details",
        "weight": 10,
        "dimension": "policy_clarity",
        "agent_impact": "Delivery timing and cost affect whether an agent can recommend the item for a user's need date.",
        "success": "The page gives shipping timing or cost clues.",
        "failure": "Add delivery timing or shipping-cost guidance near checkout intent.",
    },
    {
        "id": "returns",
        "label": "Return policy",
        "weight": 10,
        "dimension": "policy_clarity",
        "agent_impact": "Return terms affect buyer risk and agent confidence.",
        "success": "Returns or refunds are discoverable on the page.",
        "failure": "Add a concise return window and refund policy.",
    },
    {
        "id": "specs",
        "label": "Structured product specs",
        "weight": 12,
        "dimension": "agent_actionability",
        "agent_impact": "Agents need concrete attributes to match products to user constraints.",
        "success": "Agents can extract concrete item attributes.",
        "failure": "Add a compact specifications section for key product attributes.",
    },
    {
        "id": "reviews",
        "label": "Social proof or reviews",
        "weight": 8,
        "dimension": "discoverability",
        "agent_impact": "Ratings and review volume help agents rank comparable products.",
        "success": "Review or rating signals are present.",
        "failure": "Show ratings or review volume to support agent ranking decisions.",
    },
    {
        "id": "schema_product",
        "label": "Product structured data",
        "weight": 15,
        "dimension": "discoverability",
        "agent_impact": "Structured data gives agents a reliable extraction path when visible content is noisy.",
        "success": "Structured Product metadata is present.",
        "failure": "Publish Product schema or JSON-LD so agents can parse the offer reliably.",
    },
    {
        "id": "faq",
        "label": "FAQ or policy answers",
        "weight": 8,
        "dimension": "agent_actionability",
        "agent_impact": "FAQ answers reduce uncertainty for agent-generated buying guidance.",
        "success": "Common purchase objections are pre-answered.",
        "failure": "Add a small FAQ covering shipping, sizing, warranty, or setup.",
    },
    {
        "id": "variant_readiness",
        "label": "Variant readiness",
        "weight": 10,
        "dimension": "agent_actionability",
        "agent_impact": "Agents need option, price, and stock signals to recommend the right variant.",
        "success": "Variant options appear with enough context for agent comparison.",
        "failure": "Expose variant options with readable price and availability context.",
    },
    {
        "id": "offer_completeness",
        "label": "Complete offer metadata",
        "weight": 12,
        "dimension": "offer_clarity",
        "agent_impact": "Agents need price, currency, availability, and seller or policy metadata as one coherent offer.",
        "success": "Offer metadata includes core purchase-decision fields.",
        "failure": "Complete Product offers with price, currency, availability, and seller or policy metadata.",
    },
    {
        "id": "agent_answerability",
        "label": "Agent answerability",
        "weight": 10,
        "dimension": "agent_actionability",
        "agent_impact": "Agents need enough page context to answer fit, delivery, returns, and limitations questions.",
        "success": "The page can answer common agent-mediated purchase questions.",
        "failure": "Add page copy that answers fit, delivery, return, warranty, or limitation questions.",
    },
    {
        "id": "merchant_feed_hints",
        "label": "Merchant feed hints",
        "weight": 10,
        "dimension": "discoverability",
        "agent_impact": "Merchant-feed-like metadata helps agents ingest offers beyond generic SEO snippets.",
        "success": "The page includes schema hints useful for merchant feeds and agent ingestion.",
        "failure": "Add Product, Offer, rating, FAQ, shipping, or return-policy structured data hints.",
    },
]

DIMENSIONS = ("discoverability", "offer_clarity", "policy_clarity", "agent_actionability")


@dataclass
class ScanInput:
    title: str
    content: str
    source: str = "inline"


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _visible_text(html: str) -> str:
    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return _normalize_whitespace(stripped)


def _jsonld_blocks(html: str) -> list[str]:
    pattern = r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>'
    return re.findall(pattern, html, flags=re.IGNORECASE)


def _flatten_jsonld(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            items.extend(item for item in graph if isinstance(item, dict))
        return items
    if isinstance(value, list):
        items: list[dict[str, Any]] = []
        for item in value:
            items.extend(_flatten_jsonld(item))
        return items
    return []


def _parse_product_jsonld(html: str) -> tuple[list[dict[str, Any]], list[str]]:
    products: list[dict[str, Any]] = []
    warnings: list[str] = []
    for block in _jsonld_blocks(html):
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError as exc:
            warnings.append(f"Malformed JSON-LD ignored: {exc.msg}.")
            continue
        for item in _flatten_jsonld(parsed):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(type_name).lower() == "product" for type_name in types):
                products.append(item)
    return products, warnings


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _normalize_whitespace(match.group(0))
    return None


def _offer_values(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offers: list[dict[str, Any]] = []
    for product in products:
        raw_offers = product.get("offers")
        if isinstance(raw_offers, dict):
            offers.append(raw_offers)
        elif isinstance(raw_offers, list):
            offers.extend(offer for offer in raw_offers if isinstance(offer, dict))
    return offers


def _jsonld_items(html: str) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for block in _jsonld_blocks(html):
        try:
            parsed = json.loads(block.strip())
        except json.JSONDecodeError as exc:
            warnings.append(f"Malformed JSON-LD ignored: {exc.msg}.")
            continue
        items.extend(_flatten_jsonld(parsed))
    return items, warnings


def _item_types(items: list[dict[str, Any]]) -> set[str]:
    types: set[str] = set()
    for item in items:
        item_type = item.get("@type")
        raw_types = item_type if isinstance(item_type, list) else [item_type]
        types.update(str(type_name).lower() for type_name in raw_types if type_name)
    return types


def _schema_values(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for item in items:
        for key in keys:
            if key in item:
                values.append(item[key])
    return values


def parse_input(text: str, fallback_title: str = "Untitled Product Page", source: str = "inline") -> ScanInput:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    title = fallback_title
    if match:
        title = _normalize_whitespace(match.group(1)) or fallback_title
    return ScanInput(title=title, content=text, source=source)


def _score_band(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 65:
        return "workable"
    if score >= 40:
        return "weak"
    return "not_ready"


def _check_product_title(scan_input: ScanInput, plain_text: str, products: list[dict[str, Any]]) -> tuple[bool, str | None]:
    if scan_input.title and scan_input.title != "Untitled Product Page":
        return True, f"title: {scan_input.title}"
    heading = _first_match(scan_input.content, [r"<h1[^>]*>.+?</h1>"])
    if heading:
        return True, heading
    for product in products:
        name = product.get("name")
        if isinstance(name, str) and name.strip():
            return True, f"Product.name: {name.strip()}"
    return False, None


def _check_price(plain_text: str, products: list[dict[str, Any]]) -> tuple[bool, str | None]:
    for offer in _offer_values(products):
        price = offer.get("price")
        currency = offer.get("priceCurrency")
        if price:
            return True, f"Offer price: {currency or ''} {price}".strip()
    evidence = _first_match(plain_text, [r"\$\s?\d+(?:\.\d{2})?", r"usd\s?\d+(?:\.\d{2})?", r"price\s*:\s*\$?\s?\d+"])
    return (evidence is not None), evidence


def _check_availability(plain_text: str, products: list[dict[str, Any]]) -> tuple[bool, str | None]:
    for offer in _offer_values(products):
        availability = offer.get("availability")
        if availability:
            return True, f"Offer availability: {availability}"
    evidence = _first_match(plain_text, [r"in stock", r"out of stock", r"ships in [^.]+", r"availability"])
    return (evidence is not None), evidence


def _check_text(plain_text: str, patterns: list[str]) -> tuple[bool, str | None]:
    evidence = _first_match(plain_text, patterns)
    return (evidence is not None), evidence


def _check_offer_completeness(offers: list[dict[str, Any]], jsonld_items: list[dict[str, Any]]) -> tuple[bool, str | None]:
    has_policy_metadata = bool(_schema_values(jsonld_items, ("shippingDetails", "hasMerchantReturnPolicy")))
    for offer in offers:
        has_core_offer = offer.get("price") and offer.get("priceCurrency") and offer.get("availability")
        if has_core_offer and (offer.get("seller") or has_policy_metadata):
            return True, "Offer has price, currency, availability, and seller or policy metadata"
    return False, None


def _check_merchant_feed_hints(jsonld_items: list[dict[str, Any]], schema_types: set[str]) -> tuple[bool, str | None]:
    feed_types = sorted(schema_types.intersection({"product", "offer", "aggregaterating", "faqpage"}))
    policy_fields = _schema_values(jsonld_items, ("shippingDetails", "hasMerchantReturnPolicy", "aggregateRating"))
    if feed_types:
        return True, ", ".join(feed_types)
    if policy_fields:
        return True, "merchant policy fields present"
    return False, None


def _visible_price(plain_text: str) -> str | None:
    return _first_match(plain_text, [r"\$\s?\d+(?:\.\d{2})?", r"usd\s?\d+(?:\.\d{2})?"])


def _normalize_price(value: str) -> str:
    match = re.search(r"\d+(?:\.\d{1,2})?", value.replace(",", ""))
    return match.group(0) if match else value.strip().lower()


def _detect_dynamic_rendering(content: str, plain_text: str) -> bool:
    script_count = len(re.findall(r"<script\b", content, flags=re.IGNORECASE))
    app_roots = bool(re.search(r'id=["\'](?:root|app|__next|shopify-section)', content, flags=re.IGNORECASE))
    sparse_text = len(plain_text.split()) < 30
    return script_count >= 3 and app_roots and sparse_text


def _detect_contradictions(plain_text: str, offers: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    visible = _visible_price(plain_text)
    schema_prices = [str(offer.get("price")) for offer in offers if offer.get("price")]
    if visible and schema_prices:
        visible_price = _normalize_price(visible)
        schema_price = _normalize_price(schema_prices[0])
        if visible_price != schema_price:
            issues.append(
                {
                    "id": "price_contradiction",
                    "severity": "high",
                    "message": f"Visible price {visible} conflicts with Product offer price {schema_prices[0]}.",
                }
            )
    visible_out = "out of stock" in plain_text
    visible_in = "in stock" in plain_text and not visible_out
    schema_availability = " ".join(str(offer.get("availability", "")).lower() for offer in offers)
    if visible_out and "instock" in schema_availability:
        issues.append(
            {
                "id": "availability_contradiction",
                "severity": "high",
                "message": "Visible copy says out of stock while Product offer metadata says InStock.",
            }
        )
    if visible_in and "outofstock" in schema_availability:
        issues.append(
            {
                "id": "availability_contradiction",
                "severity": "high",
                "message": "Visible copy says in stock while Product offer metadata says OutOfStock.",
            }
        )
    return issues


def scan_readiness(scan_input: ScanInput) -> dict[str, Any]:
    plain_text = _visible_text(scan_input.content).lower()
    jsonld_items, warnings = _jsonld_items(scan_input.content)
    products = [
        item
        for item in jsonld_items
        if any(str(type_name).lower() == "product" for type_name in ([item.get("@type")] if not isinstance(item.get("@type"), list) else item.get("@type")))
    ]
    offers = _offer_values(products)
    schema_types = _item_types(jsonld_items)
    dynamic_rendering_likely = _detect_dynamic_rendering(scan_input.content, plain_text)
    if dynamic_rendering_likely:
        warnings.append("dynamic_rendering_likely: static HTML may miss JS-rendered price, inventory, reviews, or variants.")
    contradiction_issues = _detect_contradictions(plain_text, offers)

    evaluators = {
        "product_title": lambda: _check_product_title(scan_input, plain_text, products),
        "price": lambda: _check_price(plain_text, products),
        "availability": lambda: _check_availability(plain_text, products),
        "shipping": lambda: _check_text(plain_text, [r"shipping", r"delivery", r"arrives", r"dispatch", r"ships in [^.]+"]),
        "returns": lambda: _check_text(plain_text, [r"return", r"refund", r"exchange", r"30-day"]),
        "specs": lambda: _check_text(plain_text, [r"specifications", r"dimensions", r"materials", r"features", r"capacity"]),
        "reviews": lambda: _check_text(plain_text, [r"review", r"rating", r"\d(\.\d)?/5", r"stars?"]),
        "schema_product": lambda: (bool(products), f"{len(products)} Product JSON-LD object(s)" if products else None),
        "faq": lambda: _check_text(plain_text, [r"faq", r"frequently asked", r"questions"]),
        "variant_readiness": lambda: _check_text(
            plain_text,
            [r"variant", r"size", r"color", r"option", r"choose your", r"select (?:a )?(?:size|color)"],
        ),
        "offer_completeness": lambda: _check_offer_completeness(offers, jsonld_items),
        "agent_answerability": lambda: _check_text(
            plain_text,
            [r"fits", r"compatible", r"warranty", r"care", r"materials", r"shipping", r"returns?", r"faq"],
        ),
        "merchant_feed_hints": lambda: _check_merchant_feed_hints(jsonld_items, schema_types),
    }

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []
    passed_weight = 0
    total_weight = sum(check["weight"] for check in CHECKS)
    dimension_totals = {dimension: 0 for dimension in DIMENSIONS}
    dimension_passed = {dimension: 0 for dimension in DIMENSIONS}

    for check in CHECKS:
        passed, evidence = evaluators[check["id"]]()
        if passed:
            passed_weight += check["weight"]
            dimension_passed[check["dimension"]] += check["weight"]
        else:
            failed_checks.append(check)
        dimension_totals[check["dimension"]] += check["weight"]
        checks.append(
            {
                "id": check["id"],
                "label": check["label"],
                "dimension": check["dimension"],
                "weight": check["weight"],
                "passed": passed,
                "evidence": evidence,
                "agent_impact": check["agent_impact"],
                "recommendation": None if passed else check["failure"],
                "notes": check["success"] if passed else check["failure"],
            }
        )

    top_fixes = [
        {"check_id": check["id"], "weight": check["weight"], "recommendation": check["failure"]}
        for check in sorted(failed_checks, key=lambda item: item["weight"], reverse=True)[:5]
    ]
    score = max(0, round((passed_weight / total_weight) * 100) - (10 * len(contradiction_issues)))
    dimensions = {
        dimension: round((dimension_passed[dimension] / dimension_totals[dimension]) * 100)
        if dimension_totals[dimension]
        else 0
        for dimension in DIMENSIONS
    }
    confidence = _confidence_level(warnings, checks)

    return {
        "page": {"title": scan_input.title, "source": scan_input.source},
        "product_page_title": scan_input.title,
        "score": score,
        "band": _score_band(score),
        "dimensions": dimensions,
        "summary": {
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "total_checks": len(checks),
        },
        "checks": checks,
        "top_fixes": top_fixes,
        "warnings": warnings,
        "contradictions": contradiction_issues,
        "confidence": confidence,
        "agent_risks": [
            "Agents may skip the item if price or inventory state is ambiguous.",
            "Missing structured data increases extraction errors and ranking instability.",
            "Thin policy details reduce confidence for autonomous checkout recommendations.",
        ],
    }


def _confidence_level(warnings: list[str], checks: list[dict[str, Any]]) -> dict[str, str]:
    if any("dynamic_rendering_likely" in warning for warning in warnings):
        return {
            "level": "low",
            "basis": "Static HTML appears sparse or JS-rendered, so key commerce signals may be missing from the snapshot.",
        }
    evidence_count = sum(1 for check in checks if check.get("evidence"))
    if evidence_count >= 8:
        return {"level": "high", "basis": "Most passing checks include direct visible or structured evidence."}
    return {"level": "medium", "basis": "Some checks rely on heuristic visible-text matching."}


TASK_MAP = {
    "price": "expose_variant_prices",
    "availability": "expose_inventory_state",
    "shipping": "add_shipping_policy_summary",
    "returns": "add_return_policy_summary",
    "schema_product": "add_product_jsonld",
    "variant_readiness": "expose_variant_options",
    "offer_completeness": "complete_offer_metadata",
    "agent_answerability": "add_agent_answerable_copy",
    "merchant_feed_hints": "add_merchant_feed_metadata",
}


def build_agent_contract(bundle: dict[str, Any], contract: str = "v1") -> dict[str, Any]:
    failed = [check for check in bundle["checks"] if not check["passed"]]
    blocking = [
        {
            "id": check["id"],
            "dimension": check["dimension"],
            "severity": "high" if check["weight"] >= 12 else "medium",
            "message": check["recommendation"],
        }
        for check in failed
        if check["weight"] >= 10
    ]
    blocking.extend(bundle["contradictions"])

    tasks = []
    for check in failed:
        task_id = TASK_MAP.get(check["id"])
        if not task_id:
            continue
        tasks.append(
            {
                "id": task_id,
                "reason": check["agent_impact"],
                "files_or_page_area": _task_area(check["id"]),
                "acceptance_check": check["recommendation"],
                "priority": "high" if check["weight"] >= 12 else "medium",
            }
        )

    return {
        "contract": contract,
        "target": bundle["page"],
        "score": {"overall": bundle["score"], "dimensions": bundle["dimensions"]},
        "band": bundle["band"],
        "blocking_issues": blocking,
        "agent_tasks": tasks[:8],
        "evidence": [
            {
                "check_id": check["id"],
                "passed": check["passed"],
                "evidence": check["evidence"],
                "agent_impact": check["agent_impact"],
            }
            for check in bundle["checks"]
        ],
        "next_actions": [fix["recommendation"] for fix in bundle["top_fixes"]],
        "confidence": bundle["confidence"],
        "warnings": bundle["warnings"],
    }


def _task_area(check_id: str) -> str:
    areas = {
        "price": "product price block, variant data, or Product Offer JSON-LD",
        "availability": "inventory copy, variant data, or Product Offer availability",
        "shipping": "shipping policy copy near purchase controls",
        "returns": "returns or refund policy copy near purchase controls",
        "schema_product": "application/ld+json Product schema",
        "variant_readiness": "variant picker and variant metadata",
        "offer_completeness": "Product Offer JSON-LD",
        "agent_answerability": "FAQ, product details, policy, or fit guidance sections",
        "merchant_feed_hints": "Product, Offer, rating, FAQ, shipping, or return-policy schema",
    }
    return areas.get(check_id, "product page")


def render_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        f"# AgentShelf Report: {bundle['page']['title']}",
        "",
        "## Summary",
        f"- Source: {bundle['page']['source']}",
        f"- Score: {bundle['score']}/100",
        f"- Readiness band: {bundle['band']}",
        f"- Passed checks: {bundle['summary']['passed_checks']}/{bundle['summary']['total_checks']}",
        f"- Dimension scores: {', '.join(f'{key}={value}' for key, value in bundle['dimensions'].items())}",
        f"- Confidence: {bundle['confidence']['level']} ({bundle['confidence']['basis']})",
        "",
        "## Checks",
    ]
    for check in bundle["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        evidence = f" Evidence: {check['evidence']}." if check["evidence"] else ""
        lines.append(f"- [{status}] {check['label']} ({check['weight']} pts): {check['notes']}{evidence} Impact: {check['agent_impact']}")

    lines.extend(["", "## Top Fixes"])
    if bundle["top_fixes"]:
        for item in bundle["top_fixes"]:
            lines.append(f"- {item['recommendation']}")
    else:
        lines.append("- No urgent fixes detected in this snapshot.")

    lines.extend(["", "## Warnings"])
    if bundle["warnings"]:
        for item in bundle["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(["", "## Contradictions"])
    if bundle["contradictions"]:
        for item in bundle["contradictions"]:
            lines.append(f"- {item['message']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Agent Risks"])
    for item in bundle["agent_risks"]:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def render_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2) + "\n"
