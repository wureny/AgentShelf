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
        "success": "A shopping agent can identify the item name from page chrome or main heading.",
        "failure": "Add a single unambiguous product title in the page title and primary heading.",
    },
    {
        "id": "price",
        "label": "Explicit price",
        "weight": 15,
        "success": "Price appears directly in page text or Product offer metadata.",
        "failure": "Expose a machine-readable price near the purchase controls.",
    },
    {
        "id": "availability",
        "label": "Availability or inventory state",
        "weight": 12,
        "success": "Inventory state is stated in visible text or Product offer metadata.",
        "failure": "State whether the item is in stock, backordered, or unavailable.",
    },
    {
        "id": "shipping",
        "label": "Shipping details",
        "weight": 10,
        "success": "The page gives shipping timing or cost clues.",
        "failure": "Add delivery timing or shipping-cost guidance near checkout intent.",
    },
    {
        "id": "returns",
        "label": "Return policy",
        "weight": 10,
        "success": "Returns or refunds are discoverable on the page.",
        "failure": "Add a concise return window and refund policy.",
    },
    {
        "id": "specs",
        "label": "Structured product specs",
        "weight": 12,
        "success": "Agents can extract concrete item attributes.",
        "failure": "Add a compact specifications section for key product attributes.",
    },
    {
        "id": "reviews",
        "label": "Social proof or reviews",
        "weight": 8,
        "success": "Review or rating signals are present.",
        "failure": "Show ratings or review volume to support agent ranking decisions.",
    },
    {
        "id": "schema_product",
        "label": "Product structured data",
        "weight": 15,
        "success": "Structured Product metadata is present.",
        "failure": "Publish Product schema or JSON-LD so agents can parse the offer reliably.",
    },
    {
        "id": "faq",
        "label": "FAQ or policy answers",
        "weight": 8,
        "success": "Common purchase objections are pre-answered.",
        "failure": "Add a small FAQ covering shipping, sizing, warranty, or setup.",
    },
]


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


def scan_readiness(scan_input: ScanInput) -> dict[str, Any]:
    plain_text = _visible_text(scan_input.content).lower()
    products, warnings = _parse_product_jsonld(scan_input.content)

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
    }

    checks: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []
    score = 0

    for check in CHECKS:
        passed, evidence = evaluators[check["id"]]()
        if passed:
            score += check["weight"]
        else:
            failed_checks.append(check)
        checks.append(
            {
                "id": check["id"],
                "label": check["label"],
                "weight": check["weight"],
                "passed": passed,
                "evidence": evidence,
                "recommendation": None if passed else check["failure"],
                "notes": check["success"] if passed else check["failure"],
            }
        )

    top_fixes = [
        {"check_id": check["id"], "weight": check["weight"], "recommendation": check["failure"]}
        for check in sorted(failed_checks, key=lambda item: item["weight"], reverse=True)[:5]
    ]

    return {
        "page": {"title": scan_input.title, "source": scan_input.source},
        "product_page_title": scan_input.title,
        "score": score,
        "band": _score_band(score),
        "summary": {
            "passed_checks": sum(1 for item in checks if item["passed"]),
            "total_checks": len(checks),
        },
        "checks": checks,
        "top_fixes": top_fixes,
        "warnings": warnings,
        "agent_risks": [
            "Agents may skip the item if price or inventory state is ambiguous.",
            "Missing structured data increases extraction errors and ranking instability.",
            "Thin policy details reduce confidence for autonomous checkout recommendations.",
        ],
    }


def render_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        f"# AgentShelf Report: {bundle['page']['title']}",
        "",
        "## Summary",
        f"- Source: {bundle['page']['source']}",
        f"- Score: {bundle['score']}/100",
        f"- Readiness band: {bundle['band']}",
        f"- Passed checks: {bundle['summary']['passed_checks']}/{bundle['summary']['total_checks']}",
        "",
        "## Checks",
    ]
    for check in bundle["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        evidence = f" Evidence: {check['evidence']}." if check["evidence"] else ""
        lines.append(f"- [{status}] {check['label']} ({check['weight']} pts): {check['notes']}{evidence}")

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

    lines.extend(["", "## Agent Risks"])
    for item in bundle["agent_risks"]:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def render_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2) + "\n"

