from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import html as html_lib
import json
import re
import shlex
from pathlib import Path

from agentshelf.geo import GeoAuditResult, GeoSkillConfig, build_geo_audit


STORE_GEO_CONTRACT = "agentshelf.store_geo_audit.v0"
STORE_PAGE_GROUPS = ("home", "products", "collections", "about", "faq", "policies", "articles", "unknown")
STORE_LIMITATIONS = (
    "This report is a deterministic local audit.",
    "It does not measure live ChatGPT, Google AI, Perplexity, Claude, Gemini, or Bing visibility.",
    "It does not claim ranking lift, conversion lift, citations, impressions, mentions, referrals, or traffic.",
    "It does not use external provider search data.",
    "It identifies implementation gaps that may improve AI-readability and commerce readiness.",
)


def load_store_profile(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid store profile JSON {path}: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Store profile {path} must contain a JSON object.")
    return payload


def build_store_geo_audit(
    snapshot_root: Path,
    config: GeoSkillConfig,
    *,
    profile: dict | None = None,
    include_html: bool = True,
) -> dict:
    root = snapshot_root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Store snapshot directory not found: {snapshot_root}")
    profile = profile or {}
    config = _config_from_profile(config, profile)
    page_results = _audit_store_pages(root, config)
    if not page_results:
        raise ValueError(f"No HTML pages found under store snapshot directory: {snapshot_root}")

    store_profile = _store_profile_dict(page_results[0], config, profile)
    page_entries = [_page_entry(result, root) for result in page_results]
    page_groups = _page_groups(page_entries)
    missing_page_types = _missing_page_types(page_groups, config.vertical)
    cross_page_issues = _cross_page_issues(page_entries, store_profile, config.vertical)
    attribute_gaps = _commerce_attribute_gaps(page_entries)
    internal_linking_gaps = _internal_linking_gaps(page_entries, config.vertical)
    trust_policy_gaps = _trust_policy_gaps(page_groups, page_entries, config.vertical)
    intent_gaps = _intent_asset_gaps(page_groups, page_entries, config.vertical)
    store_issues = _store_issues(
        missing_page_types=missing_page_types,
        cross_page_issues=cross_page_issues,
        attribute_gaps=attribute_gaps,
        internal_linking_gaps=internal_linking_gaps,
        trust_policy_gaps=trust_policy_gaps,
        intent_gaps=intent_gaps,
    )
    store_score = _store_score(page_entries, store_issues)
    category_scores = _store_category_scores(page_entries, store_issues)
    actions = _top_actions(store_issues, page_entries, root, config, limit=10)
    task_rows = _store_task_rows(actions, root)

    report = {
        "contract": STORE_GEO_CONTRACT,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rootPath": str(snapshot_root),
        "sourceType": "local_snapshot",
        "storeProfile": store_profile,
        "pages": page_entries,
        "pageGroups": page_groups,
        "storeScore": store_score,
        "pageScores": {page["path"]: page["score"] for page in page_entries},
        "categoryScores": category_scores,
        "missingPageTypes": missing_page_types,
        "crossPageIssues": cross_page_issues,
        "issues": store_issues,
        "opportunities": _store_opportunities(intent_gaps, config.vertical),
        "topActions": actions,
        "taskSuggestions": [row["task"] for row in task_rows],
        "taskRows": task_rows,
        "limitations": list(STORE_LIMITATIONS),
        "rawMetadata": {
            "page_count": len(page_entries),
            "product_page_count": len(page_groups["products"]),
            "profile_input": profile,
        },
    }
    report["reportMarkdown"] = render_store_geo_markdown(report)
    if include_html:
        report["reportHtml"] = render_store_geo_html(report)
    return report


def render_store_geo_json(report: dict) -> str:
    return json.dumps(report, indent=2) + "\n"


def render_store_geo_tasks_jsonl(report: dict) -> str:
    rows = report.get("taskRows") or []
    return "".join(json.dumps(row) + "\n" for row in rows)


def render_store_geo_markdown(report: dict) -> str:
    top_risks = report.get("issues", [])[:3]
    quick_wins = [action for action in report.get("topActions", []) if action.get("effort") == "low"][:3]
    lines = [
        "# AgentShelf GEO Audit Report",
        "",
        "## 1. Executive Summary",
        f"- Store / snapshot analyzed: {report.get('rootPath')}",
        f"- Vertical: {report['storeProfile'].get('vertical')}",
        f"- Overall score: {report.get('storeScore')}/100",
        f"- Readiness level: {_readiness_level(report.get('storeScore', 0))}",
        f"- Pages analyzed: {len(report.get('pages') or [])}",
        f"- Product pages: {len(report.get('pageGroups', {}).get('products', []))}",
        "- What this report measures: deterministic AI-readability and commerce readiness gaps in local snapshots.",
        "- What this report does not measure: live AI provider visibility, rankings, citations, impressions, referrals, traffic, or conversion lift.",
        "",
        "### Top 3 risks",
    ]
    lines.extend(f"- {issue['title']}: {issue['recommendation']}" for issue in top_risks)
    if not top_risks:
        lines.append("- No high-priority store-level risks detected.")
    lines.extend(["", "### Top 3 quick wins"])
    lines.extend(f"- {action['title']} ({action['pageOrArea']})" for action in quick_wins)
    if not quick_wins:
        lines.append("- Start with the highest-priority actions below.")

    lines.extend(["", "## 2. Top 10 Prioritized Actions"])
    for action in report.get("topActions", [])[:10]:
        lines.extend(
            [
                f"### {action['priority'].upper()} - {action['title']}",
                f"- Impact: {action['impact']}",
                f"- Effort: {action['effort']}",
                f"- Page or area: {action['pageOrArea']}",
                f"- Why it matters: {action['whyItMatters']}",
                f"- Exact implementation suggestion: {action['implementationSuggestion']}",
                f"- Acceptance check: {action['acceptanceCheck']}",
                f"- Verification command: `{action['verificationCommand']}`",
            ]
        )

    lines.extend(["", "## 3. Store-Level Findings"])
    _append_list(lines, "Missing page types", report.get("missingPageTypes") or [])
    _append_issue_list(lines, "Cross-page consistency issues", report.get("crossPageIssues") or [])
    _append_issue_list(lines, "Internal linking gaps", [issue for issue in report.get("issues", []) if issue.get("category") == "internal_linking"])
    _append_issue_list(lines, "Trust and policy gaps", [issue for issue in report.get("issues", []) if issue.get("category") == "trust_policy"])

    lines.extend(["", "## 4. Page-Level Findings"])
    for page in report.get("pages") or []:
        lines.extend(
            [
                f"### {page['path']}",
                f"- Type: {page['pageType']}",
                f"- Score: {page['score']}/100",
                f"- Key issues: {', '.join(page.get('topIssueIds') or []) or 'none'}",
                f"- Suggested patches: {', '.join(page.get('topPatchIds') or []) or 'none'}",
            ]
        )

    lines.extend(["", "## 5. Structured Data"])
    schema_types = sorted({schema for page in report.get("pages") or [] for schema in page.get("schemaTypes", [])})
    lines.append(f"- Existing schema types: {', '.join(schema_types) or 'none'}")
    lines.append("- Missing schema: Product schema and FAQPage schema are page-specific; see page findings and task queue.")
    lines.append("- Suggested schema snippets: use `geo-tasks.jsonl` Product JSON-LD tasks and only merchant-confirmed fields.")
    lines.append("- Fields requiring merchant confirmation: price, currency, availability, material, dimensions, shipping, returns, ratings, reviews, and external authority.")

    lines.extend(["", "## 6. Content Extractability"])
    lines.append("- Opening answer block quality, product attributes, FAQ readiness, customization, shipping, and returns clarity are reflected in page-level scores and top actions.")

    lines.extend(["", "## 7. Entity and Trust"])
    lines.append("- Brand / artist / studio consistency is checked across titles, headings, schema, and visible copy.")
    lines.append("- About / artist page readiness, proof, gallery/process imagery, contact, FAQ, shipping, and returns are checked as store-level coverage.")

    lines.extend(["", "## 8. AI Intent Coverage"])
    for bucket in ("brand", "category", "gift", "comparison", "alternative", "customization", "trust", "shipping", "price_value", "material_craft", "buyer_persona", "gtm"):
        status = "covered" if not any(bucket in issue.get("id", "") for issue in report.get("issues", [])) else "gap detected"
        lines.append(f"- {bucket}: {status}")

    lines.extend(["", "## 9. Recommended Patches"])
    for action in report.get("topActions", [])[:10]:
        lines.append(f"- {action['title']}: {action['implementationSuggestion']}")

    lines.extend(["", "## 10. GTM Opportunities"])
    for opportunity in report.get("opportunities") or []:
        lines.append(f"- {opportunity['title']}: {opportunity['description']}")

    lines.extend(["", "## 11. Limitations"])
    lines.extend(f"- {item}" for item in report.get("limitations", STORE_LIMITATIONS))
    return "\n".join(lines) + "\n"


def render_store_geo_html(report: dict) -> str:
    actions = "".join(
        f"<li><strong>{html_lib.escape(action['priority'].upper())}: {html_lib.escape(action['title'])}</strong>"
        f"<br><span>{html_lib.escape(action['implementationSuggestion'])}</span></li>"
        for action in report.get("topActions", [])[:10]
    )
    pages = "".join(
        f"<tr><td>{html_lib.escape(page['path'])}</td><td>{html_lib.escape(page['pageType'])}</td>"
        f"<td>{page['score']}</td><td>{html_lib.escape(', '.join(page.get('topIssueIds') or []))}</td></tr>"
        for page in report.get("pages", [])
    )
    issues = "".join(
        f"<li><strong>{html_lib.escape(issue['title'])}</strong>: {html_lib.escape(issue['recommendation'])}</li>"
        for issue in report.get("issues", [])[:20]
    )
    limitations = "".join(f"<li>{html_lib.escape(item)}</li>" for item in report.get("limitations", STORE_LIMITATIONS))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentShelf Store GEO Audit</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.5; margin: 40px; color: #17202a; }}
    h1, h2 {{ color: #102a43; }}
    .score {{ font-size: 40px; font-weight: 800; }}
    .card {{ border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; margin: 20px 0; background: #f8fbff; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef4fb; }}
  </style>
</head>
<body>
  <h1>AgentShelf GEO Audit Report</h1>
  <div class="card">
    <div class="score">{report.get('storeScore')}/100</div>
    <p><strong>Vertical:</strong> {html_lib.escape(str(report['storeProfile'].get('vertical')))}</p>
    <p><strong>Snapshot:</strong> {html_lib.escape(str(report.get('rootPath')))}</p>
    <p>This is a deterministic local audit. It does not measure live AI provider visibility or ranking lift.</p>
  </div>
  <h2>Top Actions</h2>
  <ol>{actions}</ol>
  <h2>Page Scores</h2>
  <table><thead><tr><th>Page</th><th>Type</th><th>Score</th><th>Top issues</th></tr></thead><tbody>{pages}</tbody></table>
  <h2>Issues</h2>
  <ul>{issues}</ul>
  <h2>Limitations</h2>
  <ul>{limitations}</ul>
</body>
</html>
"""


def _config_from_profile(config: GeoSkillConfig, profile: dict) -> GeoSkillConfig:
    return GeoSkillConfig(
        targetUrl=config.targetUrl,
        brandName=config.brandName or profile.get("brandName"),
        storeName=config.storeName or profile.get("storeName") or profile.get("brandName"),
        category=config.category or profile.get("category"),
        market=config.market or list(profile.get("targetMarkets") or []),
        language=config.language or (profile.get("targetLanguages") or ["en"])[0],
        competitors=config.competitors or list(profile.get("competitors") or []),
        personas=config.personas or list(profile.get("buyerPersonas") or []),
        useCases=config.useCases or list(profile.get("useCases") or []),
        keyProducts=config.keyProducts or list(profile.get("keyProducts") or []),
        maxPages=config.maxPages,
        includePromptPanel=config.includePromptPanel,
        includePatchSuggestions=config.includePatchSuggestions,
        vertical=config.vertical or profile.get("vertical") or "commerce",
        outputFormat=config.outputFormat,
    )


def _audit_store_pages(root: Path, config: GeoSkillConfig) -> list[GeoAuditResult]:
    results = []
    for path in sorted(root.rglob("*.html")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        html = path.read_text(encoding="utf-8")
        page_config = GeoSkillConfig(
            **{
                **asdict(config),
                "targetUrl": relative,
                "includePromptPanel": False,
                "includePatchSuggestions": True,
            }
        )
        result = build_geo_audit(
            page_config,
            html,
            robots_text="User-agent: *\nAllow: /\n",
            robots_status="found",
            sitemap_status="found",
            llms_status="not_checked",
            raw_metadata={"source_type": "store_snapshot", "snapshot_path": relative},
        )
        result.pages[0].pageType = _classify_store_page(relative, result.pages[0].pageType, result.pages[0].textContent)
        results.append(result)
    return results


def _store_profile_dict(first_result: GeoAuditResult, config: GeoSkillConfig, profile: dict) -> dict:
    store = asdict(first_result.storeProfile)
    for key, value in profile.items():
        if key in store and value not in (None, "", []):
            store[key] = value
    store["brandName"] = config.brandName or profile.get("brandName") or store.get("brandName")
    store["vertical"] = config.vertical or profile.get("vertical") or store.get("vertical")
    store["category"] = config.category or profile.get("category") or store.get("category")
    return store


def _page_entry(result: GeoAuditResult, root: Path) -> dict:
    page = result.pages[0]
    return {
        "path": page.url,
        "pageType": page.pageType,
        "title": page.title,
        "h1": page.h1,
        "score": result.overallScore,
        "categoryScores": result.categoryScores,
        "issueCount": len(result.issues),
        "highImpactIssueCount": len([issue for issue in result.issues if issue.severity in {"critical", "high"}]),
        "topIssueIds": [issue.id for issue in result.issues if issue.severity in {"critical", "high"}][:6],
        "topPatchIds": [patch.id for patch in result.patchSuggestions[:5]],
        "schemaTypes": page.schemaTypes,
        "links": page.links,
        "imagesMissingAlt": len([image for image in page.images if not image.get("alt")]),
        "imageCount": len(page.images),
        "textContent": page.textContent,
        "productData": page.productData,
        "sourceFile": str(root / page.url),
    }


def _classify_store_page(relative: str, fallback: str, text: str) -> str:
    lower = relative.lower()
    body = text.lower()
    if lower in {"home.html", "index.html"}:
        return "home"
    if "/products/" in f"/{lower}" or lower.startswith("products/"):
        return "product"
    if "/collections/" in f"/{lower}" or lower.startswith("collections/"):
        return "collection"
    if any(token in lower for token in ("faq", "questions")):
        return "faq"
    if any(token in lower for token in ("shipping", "returns", "refund", "policy")):
        return "policy"
    if any(token in lower for token in ("about", "artist", "studio")):
        return "about"
    if any(token in lower for token in ("commission", "custom", "process")) or "commission process" in body:
        return "commission"
    return fallback


def _page_groups(pages: list[dict]) -> dict:
    groups = {name: [] for name in STORE_PAGE_GROUPS}
    for page in pages:
        page_type = page["pageType"]
        if page_type == "product":
            groups["products"].append(page["path"])
        elif page_type == "collection":
            groups["collections"].append(page["path"])
        elif page_type == "policy":
            groups["policies"].append(page["path"])
        elif page_type == "commission":
            groups["articles"].append(page["path"])
        elif page_type in groups:
            groups[page_type].append(page["path"])
        else:
            groups["unknown"].append(page["path"])
    return groups


def _missing_page_types(groups: dict, vertical: str) -> list[str]:
    missing = []
    required = {
        "home": "home",
        "product_page": "products",
        "collection_page": "collections",
        "about_page": "about",
        "faq_page": "faq",
    }
    for page_type, group in required.items():
        if not groups.get(group):
            missing.append(page_type)
    policies = " ".join(groups.get("policies", [])).lower()
    if "shipping" not in policies:
        missing.append("shipping_policy")
    if not any(token in policies for token in ("return", "refund")):
        missing.append("return_policy")
    if vertical in {"artist_store", "creator_commerce"} and not any("commission" in path or "custom" in path for path in groups.get("articles", [])):
        missing.append("commission_process_page")
    if not any("gift" in path for path in groups.get("collections", [])):
        missing.append("gift_guide")
    return missing


def _cross_page_issues(pages: list[dict], store_profile: dict, vertical: str) -> list[dict]:
    issues = []
    brand = str(store_profile.get("brandName") or "").lower()
    if brand:
        missing_brand = [
            page["path"]
            for page in pages
            if brand not in f"{page.get('title', '')} {page.get('h1', '')} {page.get('textContent', '')[:1200]}".lower()
        ]
        if missing_brand:
            issues.append(
                _store_issue(
                    "cross_page_brand_name_inconsistent",
                    "high",
                    "entity_consistency",
                    "Brand name is not consistently visible across pages",
                    f"Configured brand is missing from key text on {len(missing_brand)} page(s).",
                    "AI-readable storefronts need stable entity naming across home, product, collection, about, FAQ, and policy pages.",
                    "Use the same brand or studio name in titles, H1s, opening copy, footer, and schema across all key pages.",
                    missing_brand[:5],
                )
            )
    product_paths = [page["path"] for page in pages if page["pageType"] == "product"]
    policy_paths = [page["path"] for page in pages if page["pageType"] == "policy"]
    if product_paths and policy_paths:
        for page in pages:
            if page["pageType"] == "product" and not _links_to_any(page, ("shipping", "return", "refund", "faq")):
                issues.append(
                    _store_issue(
                        f"product_policy_links_missing_{_slug(page['path'])}",
                        "medium",
                        "internal_linking",
                        "Product page does not link to policy or FAQ pages",
                        f"{page['path']} does not expose clear links to shipping, returns, or FAQ.",
                        "Agents need policy paths before recommending fragile, custom, or international purchases.",
                        "Link product templates to FAQ, shipping, returns, and custom-order policy sections.",
                        [page["path"]],
                    )
                )
                break
    if vertical in {"artist_store", "creator_commerce"}:
        about_pages = [page for page in pages if page["pageType"] == "about"]
        if about_pages and not any(_links_to_any(page, ("commission", "custom", "product", "collection")) for page in about_pages):
            issues.append(
                _store_issue(
                    "about_page_dead_end",
                    "medium",
                    "internal_linking",
                    "About/artist page does not route buyers to products or commission flow",
                    "The artist entity page should connect trust context to a buying or inquiry path.",
                    "AI answers need a safe next step after explaining the maker or studio.",
                    "Link the about/artist page to collections, products, and commission process pages.",
                    [page["path"] for page in about_pages],
                )
            )
    return issues


def _commerce_attribute_gaps(pages: list[dict]) -> list[dict]:
    product_pages = [page for page in pages if page["pageType"] == "product"]
    fields = {
        "price": ("price", r"\$\s?\d|usd\s?\d|price"),
        "availability": ("availability", r"in stock|sold out|available|made to order"),
        "material": ("material", r"ceramic|porcelain|stoneware|paper|wood|cotton|material"),
        "dimensions": ("size or dimensions", r"size|dimension|capacity|oz|cm|inch"),
        "customization": ("customization", r"custom|personalized|commission|made to order|initials|name"),
        "lead_time": ("lead time", r"business days|lead time|weeks|ships in|production time"),
        "shipping": ("shipping", r"shipping|delivery|ships|tracking"),
        "returns": ("returns", r"return|refund|exchange|cancel"),
        "care": ("care instructions", r"care|wash|dishwasher|hand wash|display only"),
        "gift_occasion": ("gift occasions", r"gift|wedding|anniversary|birthday|holiday"),
    }
    gaps = []
    for field, (label, pattern) in fields.items():
        missing = []
        for page in product_pages:
            text = page.get("textContent", "").lower()
            product = page.get("productData") or {}
            if product.get(field) or re.search(pattern, text, flags=re.IGNORECASE):
                continue
            missing.append(page["path"])
        if missing:
            gaps.append(
                _store_issue(
                    f"product_attribute_gap_{field}",
                    "high" if field in {"price", "availability", "shipping", "returns"} else "medium",
                    "commerce_attributes",
                    f"Product pages often miss {label}",
                    f"{len(missing)} product page(s) do not clearly expose {label}.",
                    "Shopping agents need concrete purchase-decision facts, not only imagery or storytelling.",
                    f"Add merchant-confirmed {label} to visible product copy and structured data where appropriate.",
                    missing[:8],
                )
            )
    return gaps


def _internal_linking_gaps(pages: list[dict], vertical: str) -> list[dict]:
    gaps = []
    home = next((page for page in pages if page["pageType"] == "home"), None)
    if home and not _links_to_any(home, ("product", "collection", "about", "artist")):
        gaps.append(
            _store_issue(
                "home_internal_links_weak",
                "medium",
                "internal_linking",
                "Homepage does not clearly link to product, collection, or entity pages",
                "The homepage lacks obvious internal links to commercial and trust pages.",
                "AI crawlers and buyers need direct paths from the homepage into products, collections, and entity proof.",
                "Add visible links to best collections, product pages, about/artist, FAQ, shipping, and commission pages.",
                [home["path"]],
            )
        )
    collection_pages = [page for page in pages if page["pageType"] == "collection"]
    if collection_pages and not any(_links_to_any(page, ("product", "/products/")) for page in collection_pages):
        gaps.append(
            _store_issue(
                "collection_product_links_missing",
                "high",
                "internal_linking",
                "Collection pages do not link to product pages",
                "Collection pages should route category and gift intent to concrete products.",
                "Agents need collection-to-product paths to connect broad buyer intent to purchasable offers.",
                "Add product cards or contextual links from each collection to relevant product pages.",
                [page["path"] for page in collection_pages],
            )
        )
    faq_pages = [page for page in pages if page["pageType"] == "faq"]
    if faq_pages and not any(_links_to_any(page, ("product", "commission", "contact", "shipping")) for page in faq_pages):
        gaps.append(
            _store_issue(
                "faq_dead_end",
                "low",
                "internal_linking",
                "FAQ does not route buyers to next steps",
                "FAQ pages answer objections but should also connect buyers to products, commission, shipping, or contact.",
                "Agent answers can cite FAQ copy more safely when users can follow a clear next step.",
                "Add internal links from FAQ answers to relevant products, commission process, policy, and contact pages.",
                [page["path"] for page in faq_pages],
            )
        )
    return gaps


def _trust_policy_gaps(groups: dict, pages: list[dict], vertical: str) -> list[dict]:
    all_text = " ".join(page.get("textContent", "") for page in pages).lower()
    gaps = []
    checks = {
        "contact": ("contact path", r"contact|email|support|inquiry"),
        "process": ("making or commission process", r"process|commission|custom order|made to order"),
        "proof": ("trust proof", r"testimonial|portfolio|gallery|past work|process image|studio photo"),
    }
    for key, (label, pattern) in checks.items():
        if not re.search(pattern, all_text, flags=re.IGNORECASE):
            gaps.append(
                _store_issue(
                    f"trust_gap_{key}",
                    "medium",
                    "trust_policy",
                    f"Missing {label}",
                    f"The store snapshot does not clearly expose {label}.",
                    "AI-readable commerce needs proof and policy context before recommendation or comparison.",
                    f"Add merchant-confirmed {label} in visible copy and link it from product and about pages.",
                    [],
                )
            )
    if not groups.get("faq"):
        gaps.append(_coverage_issue("faq_page", "FAQ page is missing", "Add a crawlable FAQ page for customization, shipping, returns, care, deadlines, and contact."))
    if "shipping_policy" in _missing_page_types(groups, vertical):
        gaps.append(_coverage_issue("shipping_policy", "Shipping policy page is missing", "Add a clear shipping policy with regions, timing, packaging, tracking, and international boundaries."))
    if "return_policy" in _missing_page_types(groups, vertical):
        gaps.append(_coverage_issue("return_policy", "Return policy page is missing", "Add return, exchange, refund, and cancellation terms, especially for custom goods."))
    return gaps


def _intent_asset_gaps(groups: dict, pages: list[dict], vertical: str) -> list[dict]:
    all_paths = " ".join(page["path"] for page in pages).lower()
    gaps = []
    intent_assets = {
        "gift_guide": ("gift intent asset", "Create a gift guide for buyer personas, occasions, price bands, customization, and shipping deadlines."),
        "comparison_page": ("comparison intent asset", "Create comparison content against generic alternatives without unsupported competitor claims."),
        "material_care_guide": ("material and care guide", "Create a material/care guide so agents can answer durability and use questions."),
    }
    for key, (title, recommendation) in intent_assets.items():
        token = key.replace("_page", "").replace("_guide", "").split("_")[0]
        if token not in all_paths:
            gaps.append(
                _store_issue(
                    f"intent_gap_{key}",
                    "medium",
                    "ai_intent_coverage",
                    f"Missing {title}",
                    f"The snapshot does not include a dedicated {title}.",
                    "Generative engines answer high-intent prompts more safely when there are focused, crawlable assets.",
                    recommendation,
                    [],
                )
            )
    if vertical in {"artist_store", "creator_commerce"} and "commission" not in all_paths:
        gaps.append(
            _store_issue(
                "intent_gap_commission_process",
                "high",
                "ai_intent_coverage",
                "Missing commission process asset",
                "Creator-commerce buyers need customization boundaries, timeline, inputs, revisions, and cancellation terms.",
                "Agents should not infer custom-order process from product poetry or image captions.",
                "Create a commission/custom order process page and link it from products, about, and FAQ.",
                [],
            )
        )
    return gaps


def _store_issues(
    *,
    missing_page_types: list[str],
    cross_page_issues: list[dict],
    attribute_gaps: list[dict],
    internal_linking_gaps: list[dict],
    trust_policy_gaps: list[dict],
    intent_gaps: list[dict],
) -> list[dict]:
    coverage_issues = [
        _store_issue(
            f"missing_page_type_{page_type}",
            "high" if page_type in {"product_page", "shipping_policy", "return_policy", "commission_process_page"} else "medium",
            "page_type_coverage",
            f"Missing {page_type.replace('_', ' ')}",
            f"The store snapshot does not include {page_type.replace('_', ' ')}.",
            "Store-level GEO depends on answerable, linkable pages across buyer intent, trust, and policy questions.",
            f"Create or expose a crawlable {page_type.replace('_', ' ')} and link it from relevant pages.",
            [],
        )
        for page_type in missing_page_types
    ]
    return sorted(
        coverage_issues + cross_page_issues + attribute_gaps + internal_linking_gaps + trust_policy_gaps + intent_gaps,
        key=lambda issue: (_severity_rank(issue["severity"]), issue["id"]),
    )


def _store_score(pages: list[dict], issues: list[dict]) -> int:
    if not pages:
        return 0
    page_average = round(sum(page["score"] for page in pages) / len(pages))
    penalty = sum({"critical": 8, "high": 5, "medium": 3, "low": 1}.get(issue["severity"], 0) for issue in issues)
    return max(0, min(100, page_average - penalty))


def _store_category_scores(pages: list[dict], issues: list[dict]) -> dict:
    categories = {
        "page_type_coverage",
        "entity_consistency",
        "commerce_attributes",
        "internal_linking",
        "trust_policy",
        "ai_intent_coverage",
        "structured_data",
        "content_extractability",
    }
    scores = {category: 100 for category in sorted(categories)}
    for page in pages:
        for category, score in page.get("categoryScores", {}).items():
            if category in scores:
                scores[category] = min(scores[category], score)
    for issue in issues:
        category = issue.get("category")
        if category in scores:
            scores[category] = max(0, scores[category] - {"critical": 28, "high": 18, "medium": 10, "low": 5}.get(issue["severity"], 0))
    return scores


def _top_actions(issues: list[dict], pages: list[dict], root: Path, config: GeoSkillConfig, *, limit: int) -> list[dict]:
    actions = []
    command = f"agentshelf geo-run --store-snapshot {shlex.quote(str(root))} --vertical {shlex.quote(config.vertical)} --format json"
    for issue in issues[:limit]:
        actions.append(
            {
                "id": f"action_{issue['id']}",
                "issueIds": [issue["id"]],
                "priority": issue["severity"] if issue["severity"] in {"critical", "high"} else "medium",
                "impact": "high" if issue["severity"] in {"critical", "high"} else "medium",
                "effort": _effort_for_issue(issue),
                "pageOrArea": ", ".join(issue.get("pagePaths") or []) or issue["category"],
                "title": issue["title"],
                "whyItMatters": issue["whyItMatters"],
                "implementationSuggestion": issue["recommendation"],
                "acceptanceCheck": "Re-run the store-level audit and confirm this issue id is absent or downgraded without fabricating reviews, ratings, stock, policy, press, or external authority.",
                "verificationCommand": command,
            }
        )
    return actions


def _store_task_rows(actions: list[dict], root: Path) -> list[dict]:
    rows = []
    for action in actions:
        rows.append(
            {
                "contract": "agentshelf.geo_task.v0",
                "source": str(root),
                "page_url": action["pageOrArea"],
                "task": {
                    "id": action["id"].replace("action_", "store_"),
                    "title": action["title"],
                    "priority": action["priority"],
                    "type": "issue",
                    "category": "store_level_geo",
                    "reason": action["whyItMatters"],
                    "files_or_page_area": action["pageOrArea"],
                    "acceptance_check": action["acceptanceCheck"],
                    "verification_command": action["verificationCommand"],
                    "impact": action["impact"],
                    "effort": action["effort"],
                    "issue_ids": action["issueIds"],
                    "instructions": [action["implementationSuggestion"]],
                    "acceptanceCriteria": [action["acceptanceCheck"]],
                    "expectedReportDelta": "Store-level issue count decreases and no fake AI visibility or merchant fact claims are introduced.",
                    "riskNotes": "Use only merchant-confirmed facts. Do not invent reviews, ratings, stock, shipping promises, return promises, press, or AI ranking data.",
                },
            }
        )
    return rows


def _store_opportunities(intent_gaps: list[dict], vertical: str) -> list[dict]:
    opportunities = []
    for gap in intent_gaps:
        opportunities.append(
            {
                "id": gap["id"].replace("intent_gap_", "opportunity_"),
                "title": gap["title"],
                "description": gap["recommendation"],
                "expectedImpact": "Improves deterministic AI-readability for high-intent commerce questions.",
                "effort": "medium",
                "recommendedAssetType": gap["id"].replace("intent_gap_", ""),
            }
        )
    if vertical in {"artist_store", "creator_commerce"}:
        opportunities.append(
            {
                "id": "opportunity_artist_entity_factsheet",
                "title": "Build an artist or studio entity factsheet",
                "description": "Publish verified maker, studio, process, portfolio, contact, and social profile facts in one crawlable page.",
                "expectedImpact": "Improves entity consistency and trust answerability for creator commerce.",
                "effort": "medium",
                "recommendedAssetType": "artist_entity_factsheet",
            }
        )
    return opportunities[:8]


def _store_issue(
    issue_id: str,
    severity: str,
    category: str,
    title: str,
    description: str,
    why: str,
    recommendation: str,
    page_paths: list[str],
) -> dict:
    return {
        "id": issue_id,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "whyItMatters": why,
        "recommendation": recommendation,
        "pagePaths": page_paths,
        "confidence": 0.78,
    }


def _coverage_issue(issue_id: str, title: str, recommendation: str) -> dict:
    return _store_issue(
        f"trust_gap_{issue_id}",
        "high",
        "trust_policy",
        title,
        title,
        "Agents need explicit trust and policy assets before making safe commerce recommendations.",
        recommendation,
        [],
    )


def _links_to_any(page: dict, tokens: tuple[str, ...]) -> bool:
    for link in page.get("links") or []:
        combined = f"{link.get('href', '')} {link.get('text', '')}".lower()
        if any(token in combined for token in tokens):
            return True
    return False


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(severity, 5)


def _effort_for_issue(issue: dict) -> str:
    if issue["category"] in {"page_type_coverage", "ai_intent_coverage"}:
        return "medium"
    if issue["category"] == "commerce_attributes":
        return "low"
    return "medium"


def _readiness_level(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "workable"
    if score >= 45:
        return "weak"
    return "not_ready"


def _append_list(lines: list[str], title: str, items: list[str]) -> None:
    lines.append(f"### {title}")
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append("- None detected.")


def _append_issue_list(lines: list[str], title: str, issues: list[dict]) -> None:
    lines.append(f"### {title}")
    if issues:
        lines.extend(f"- {issue['title']}: {issue['recommendation']}" for issue in issues)
    else:
        lines.append("- None detected.")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:60] or "page"
