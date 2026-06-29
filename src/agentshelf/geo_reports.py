from __future__ import annotations

from dataclasses import asdict
import json

from agentshelf.geo_types import GeoAuditResult, GeoPrompt, PROMPT_BUCKETS


def render_geo_json(result: GeoAuditResult) -> str:
    return json.dumps(geo_result_to_dict(result), indent=2) + "\n"


def geo_result_to_dict(result: GeoAuditResult) -> dict:
    payload = asdict(result)
    payload["reportMarkdown"] = result.reportMarkdown
    return payload


def render_geo_markdown(result: GeoAuditResult) -> str:
    page = result.pages[0]
    critical = [issue for issue in result.issues if issue.severity in {"critical", "high"}]
    quick_wins = [issue for issue in result.issues if issue.severity in {"medium", "low"}][:5]
    lines = [
        "# AgentShelf GEO Audit Report",
        "",
        "## 1. Executive Summary",
        f"- Target: {result.targetUrl}",
        f"- Brand: {result.storeProfile.brandName}",
        f"- Category: {result.storeProfile.category}",
        f"- Vertical: {result.storeProfile.vertical}",
        f"- Overall score: {result.overallScore}/100",
        f"- Pages analyzed: {len(result.pages)}",
        f"- High-impact issues: {len(critical)}",
        "",
        "### Highest-impact issues",
    ]
    if critical:
        for issue in critical[:6]:
            lines.append(f"- [{issue.severity.upper()}] {issue.title}: {issue.recommendation}")
    else:
        lines.append("- No critical or high-severity GEO issues detected in this snapshot.")

    lines.extend(["", "### Quick wins"])
    if quick_wins:
        for issue in quick_wins:
            lines.append(f"- {issue.recommendation}")
    else:
        lines.append("- Keep monitoring prompt coverage and structured data completeness.")

    sections = [
        ("2. Crawlability & Indexability", ("crawlability", "indexability")),
        ("3. Structured Data", ("structured_data",)),
        ("4. Content Extractability", ("content_extractability",)),
        ("5. Entity Consistency", ("entity_consistency",)),
        ("6. Commerce Attributes", ("commerce_attributes",)),
        ("7. Trust & Proof", ("trust", "external_authority")),
        ("8. AI Intent Coverage", ("ai_intent_coverage",)),
    ]
    for heading, categories in sections:
        lines.extend(["", f"## {heading}"])
        relevant = [issue for issue in result.issues if issue.category in categories]
        if not relevant:
            lines.append("- No major issues detected.")
            continue
        for issue in relevant:
            lines.append(f"- [{issue.severity.upper()}] {issue.title}")
            lines.append(f"  - Why it matters: {issue.whyItMatters}")
            lines.append(f"  - Recommendation: {issue.recommendation}")

    lines.extend(["", "## 9. Prompt Panel"])
    if result.promptPanel:
        grouped: dict[str, list[GeoPrompt]] = {}
        for prompt in result.promptPanel:
            grouped.setdefault(prompt.intentBucket, []).append(prompt)
        for bucket in PROMPT_BUCKETS:
            prompts = grouped.get(bucket, [])
            if not prompts:
                continue
            lines.append(f"### {bucket}")
            for prompt in prompts[:8]:
                lines.append(f"- ({prompt.commercialIntent}, P{prompt.priority}) {prompt.prompt}")
    else:
        lines.append("- Prompt panel disabled for this run.")

    lines.extend(["", "## 10. Recommended Patches"])
    if result.patchSuggestions:
        for patch in result.patchSuggestions:
            lines.append(f"- [{patch.priority.upper()}] {patch.title}")
            lines.append(f"  - Page: {patch.pageUrl or page.url}")
            lines.append(f"  - Patch type: {patch.patchType}")
            lines.append(f"  - Why it matters: {patch.rationale}")
            lines.append(f"  - Suggested copy: {patch.suggestedCopy}")
            lines.append(f"  - Implementation notes: {patch.implementationNotes}")
    else:
        lines.append("- No patch suggestions generated.")

    lines.extend(["", "## 11. GTM Opportunities"])
    if result.opportunities:
        for opportunity in result.opportunities:
            lines.append(f"- {opportunity.title} ({opportunity.recommendedAssetType}, {opportunity.effort} effort)")
            lines.append(f"  - Impact: {opportunity.expectedImpact}")
            lines.append(f"  - Description: {opportunity.description}")
    else:
        lines.append("- No strategic content opportunities generated.")

    lines.extend(
        [
            "",
            "## Page Snapshot",
            f"- Page type: {page.pageType}",
            f"- Title: {page.title or 'missing'}",
            f"- H1: {page.h1 or 'missing'}",
            f"- Canonical: {page.canonical or 'missing'}",
            f"- Word count: {page.wordCount}",
            f"- Schema types: {', '.join(page.schemaTypes) or 'none'}",
            f"- Images missing alt: {sum(1 for image in page.images if not image.get('alt'))}/{len(page.images)}",
        ]
    )
    return "\n".join(lines) + "\n"
