from __future__ import annotations

import json
import shlex


def render_geo_tasks_jsonl(report: dict) -> str:
    return "".join(json.dumps(row) + "\n" for row in geo_tasks_from_report(report))


def render_geo_tasks_json(report: dict) -> str:
    tasks = geo_tasks_from_report(report)
    return json.dumps(
        {
            "contract": "agentshelf.geo_tasks.v0",
            "source": report.get("targetUrl"),
            "task_count": len(tasks),
            "tasks": tasks,
        },
        indent=2,
    ) + "\n"


def geo_tasks_from_report(report: dict) -> list[dict]:
    source = report.get("targetUrl") or "unknown"
    pages = report.get("pages") or []
    default_page = pages[0].get("url") if pages and isinstance(pages[0], dict) else source
    tasks: list[dict] = []

    for patch in report.get("patchSuggestions") or []:
        patch_type = patch.get("patchType") or "page_patch"
        task_id = patch.get("id") or patch_type
        tasks.append(
            {
                "contract": "agentshelf.geo_task.v0",
                "source": source,
                "page_url": patch.get("pageUrl") or default_page,
                "task": {
                    "id": task_id,
                    "title": patch.get("title") or task_id.replace("_", " ").title(),
                    "priority": patch.get("priority") or "medium",
                    "type": "patch",
                    "patch_type": patch_type,
                    "reason": patch.get("rationale") or "Improve AI-readable commerce evidence.",
                    "files_or_page_area": _geo_task_area(patch_type),
                    "suggested_copy": patch.get("suggestedCopy"),
                    "suggested_schema": patch.get("suggestedSchema"),
                    "implementation_notes": patch.get("implementationNotes"),
                    "acceptance_check": _geo_acceptance_check(patch_type),
                    "verification_command": _geo_verification_command(source),
                },
            }
        )

    covered = {row["task"]["id"] for row in tasks}
    for issue in report.get("issues") or []:
        if issue.get("severity") not in {"critical", "high"}:
            continue
        issue_id = issue.get("id") or "geo_issue"
        if issue_id in covered:
            continue
        tasks.append(
            {
                "contract": "agentshelf.geo_task.v0",
                "source": source,
                "page_url": issue.get("pageUrl") or default_page,
                "task": {
                    "id": issue_id,
                    "title": issue.get("title") or issue_id.replace("_", " ").title(),
                    "priority": "high" if issue.get("severity") == "high" else "critical",
                    "type": "issue",
                    "category": issue.get("category"),
                    "reason": issue.get("whyItMatters") or issue.get("description"),
                    "files_or_page_area": _geo_issue_area(issue_id, issue.get("category")),
                    "suggested_copy": None,
                    "suggested_schema": None,
                    "implementation_notes": issue.get("recommendation"),
                    "acceptance_check": _geo_issue_acceptance_check(issue_id, issue.get("category")),
                    "verification_command": _geo_verification_command(source),
                },
            }
        )
    return tasks


def _geo_task_area(patch_type: str) -> str:
    areas = {
        "opening_answer_block": "top of product, collection, home, artist, or landing page template",
        "faq_block": "FAQ section, product detail accordion, or shared commerce FAQ component",
        "product_schema": "Product JSON-LD builder, product template, or schema component",
        "organization_schema": "sitewide layout head, SEO component, or Organization/WebSite schema builder",
        "image_alt_text": "product image data, CMS image fields, or image rendering component",
        "collection_page_brief": "collection page route/template and internal links",
        "gift_guide_brief": "guide/article route, CMS page, or content collection",
        "commission_process": "custom order, commission, or personalization process page",
        "artist_entity_factsheet": "about, artist, studio, press, or entity factsheet page",
    }
    return areas.get(patch_type, "commerce page template or CMS content")


def _geo_issue_area(issue_id: str, category: str | None) -> str:
    if "schema" in issue_id:
        return "JSON-LD schema component or page head"
    if "shipping" in issue_id or "return" in issue_id:
        return "policy copy near purchase controls and policy pages"
    if "crawler" in issue_id or category in {"crawlability", "indexability"}:
        return "robots.txt, sitemap, canonical tags, or page metadata"
    if "artist" in issue_id or "entity" in issue_id:
        return "about, artist, studio, footer, schema, and sameAs links"
    return "page template, CMS content, or storefront data mapper"


def _geo_acceptance_check(patch_type: str) -> str:
    checks = {
        "opening_answer_block": "Re-run `agentshelf geo-audit ... --format json` and confirm `thin_opening_answer` is absent or downgraded.",
        "faq_block": "Re-run `agentshelf geo-audit ... --format json` and confirm FAQ content is detected; add FAQPage schema only from visible answers.",
        "product_schema": "Re-run `agentshelf geo-audit ... --format json` and confirm Product and Offer schema issues are resolved without fake ratings or reviews.",
        "organization_schema": "Re-run `agentshelf geo-audit ... --format json` and confirm Organization or WebSite schema is detected with verified sameAs/contact fields.",
        "image_alt_text": "Re-run `agentshelf geo-audit ... --format json` and confirm fewer product images have empty alt text.",
        "collection_page_brief": "Add the collection page or brief, link it internally, then re-run `agentshelf geo-audit` and review AI intent coverage.",
        "gift_guide_brief": "Add the gift guide, link it internally, then re-run `agentshelf geo-audit` and confirm gift intent coverage improves.",
        "commission_process": "Add a custom order process page with timeline, inputs, revisions, shipping, and cancellation boundaries.",
        "artist_entity_factsheet": "Add or improve artist/studio facts, portfolio, social profiles, press/contact data, and internal links.",
    }
    return checks.get(patch_type, "Re-run `agentshelf geo-audit ... --format json` and confirm the related issue is resolved.")


def _geo_issue_acceptance_check(issue_id: str, category: str | None) -> str:
    if "crawler" in issue_id or category == "crawlability":
        return "Re-run `agentshelf geo-audit ... --format json` and confirm the crawler or robots blocker is absent."
    if category == "indexability":
        return "Re-run `agentshelf geo-audit ... --format json` and confirm noindex, canonical, and sitemap blockers are resolved."
    if "schema" in issue_id or category == "structured_data":
        return "Re-run `agentshelf geo-audit ... --format json` and confirm the structured-data issue is absent using only merchant-verified facts."
    if category == "commerce_attributes":
        return "Re-run `agentshelf geo-audit ... --format json` and confirm purchase-decision fields are visible or present in structured data."
    if category == "trust":
        return "Re-run `agentshelf geo-audit ... --format json` and confirm trust evidence is visible without fabricated reviews, ratings, or press."
    return "Re-run `agentshelf geo-audit ... --format json` and confirm this high-severity issue is absent or downgraded."


def _geo_verification_command(source: str) -> str:
    return f"agentshelf geo-audit {shlex.quote(source)} --format json"
