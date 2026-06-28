from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html as html_lib
import json
import re
import shlex
from urllib.parse import urlparse


GEO_CATEGORIES = (
    "crawlability",
    "indexability",
    "structured_data",
    "content_extractability",
    "entity_consistency",
    "commerce_attributes",
    "trust",
    "ai_intent_coverage",
    "external_authority",
    "gtm",
)
VERTICALS = ("commerce", "creator_commerce", "artist_store", "local_service", "generic")
PROMPT_BUCKETS = (
    "brand",
    "category",
    "gift",
    "comparison",
    "alternative",
    "customization",
    "trust",
    "shipping",
    "price_value",
    "material_craft",
    "buyer_persona",
    "gtm",
)
SEVERITY_PENALTY = {"critical": 28, "high": 18, "medium": 10, "low": 5, "info": 0}


@dataclass
class GeoSkillConfig:
    targetUrl: str
    brandName: str | None = None
    storeName: str | None = None
    category: str | None = None
    market: list[str] = field(default_factory=list)
    language: str = "en"
    competitors: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    useCases: list[str] = field(default_factory=list)
    keyProducts: list[str] = field(default_factory=list)
    maxPages: int = 1
    includePromptPanel: bool = True
    includePatchSuggestions: bool = True
    vertical: str = "commerce"
    outputFormat: str = "markdown"


@dataclass
class StoreProfile:
    brandName: str
    domain: str
    category: str
    vertical: str
    targetMarkets: list[str]
    targetLanguages: list[str]
    keyProducts: list[str]
    buyerPersonas: list[str]
    useCases: list[str]
    competitors: list[str]
    positioning: str
    uniqueClaims: list[str]


@dataclass
class GeoPage:
    url: str
    pageType: str
    title: str
    metaDescription: str | None
    h1: str | None
    headings: list[str]
    canonical: str | None
    textContent: str
    wordCount: int
    links: list[dict]
    images: list[dict]
    schemaTypes: list[str]
    productData: dict
    faqData: list[dict]
    extractedClaims: list[str]
    lastModified: str | None
    crawlStatus: dict


@dataclass
class GeoIssue:
    id: str
    severity: str
    category: str
    title: str
    description: str
    whyItMatters: str
    recommendation: str
    confidence: float
    pageUrl: str | None = None


@dataclass
class GeoOpportunity:
    id: str
    category: str
    title: str
    description: str
    expectedImpact: str
    effort: str
    recommendedAssetType: str
    relatedPrompts: list[str] = field(default_factory=list)


@dataclass
class GeoPrompt:
    id: str
    prompt: str
    language: str
    intentBucket: str
    commercialIntent: str
    priority: int
    targetAnswerRole: str


@dataclass
class GeoPatchSuggestion:
    id: str
    patchType: str
    title: str
    rationale: str
    suggestedCopy: str
    implementationNotes: str
    priority: str
    pageUrl: str | None = None
    suggestedSchema: dict | None = None


@dataclass
class GeoAuditResult:
    targetUrl: str
    generatedAt: str
    storeProfile: StoreProfile
    pages: list[GeoPage]
    overallScore: int
    categoryScores: dict[str, int]
    issues: list[GeoIssue]
    opportunities: list[GeoOpportunity]
    promptPanel: list[GeoPrompt]
    patchSuggestions: list[GeoPatchSuggestion]
    reportMarkdown: str
    rawMetadata: dict


def build_geo_audit(
    config: GeoSkillConfig,
    html: str,
    *,
    robots_text: str | None = None,
    robots_status: str = "not_checked",
    sitemap_status: str = "not_checked",
    llms_status: str = "not_checked",
    raw_metadata: dict | None = None,
) -> GeoAuditResult:
    config = _normalize_config(config)
    store = _build_store_profile(config, html)
    page = _extract_page(config.targetUrl, html, robots_status=robots_status, sitemap_status=sitemap_status)
    issues = _audit_page(config, store, page, robots_text, sitemap_status, llms_status)
    prompts = generate_prompt_panel(store, config) if config.includePromptPanel else []
    opportunities = _build_opportunities(config, store, page, issues, prompts)
    patches = generate_patch_suggestions(config, store, page, issues, opportunities) if config.includePatchSuggestions else []
    category_scores = _category_scores(issues)
    overall = round(sum(category_scores.values()) / len(category_scores))
    result = GeoAuditResult(
        targetUrl=config.targetUrl,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        storeProfile=store,
        pages=[page],
        overallScore=overall,
        categoryScores=category_scores,
        issues=issues,
        opportunities=opportunities,
        promptPanel=prompts,
        patchSuggestions=patches,
        reportMarkdown="",
        rawMetadata={
            "contract": "agentshelf.geo_audit.v0",
            "robots_status": robots_status,
            "sitemap_status": sitemap_status,
            "llms_status": llms_status,
            "input": asdict(config),
            **(raw_metadata or {}),
        },
    )
    result.reportMarkdown = render_geo_markdown(result)
    return result


def render_geo_json(result: GeoAuditResult) -> str:
    return json.dumps(geo_result_to_dict(result), indent=2) + "\n"


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


def generate_prompt_panel(store: StoreProfile, config: GeoSkillConfig) -> list[GeoPrompt]:
    category = store.category or "products"
    brand = store.brandName or "this brand"
    competitors = store.competitors or ["Etsy", "Amazon Handmade", "local boutiques"]
    personas = store.buyerPersonas or _default_personas(store.vertical)
    use_cases = store.useCases or _default_use_cases(store.vertical)
    products = store.keyProducts or [category, "signature product", "custom order"]
    language = config.language or "en"
    prompts: list[GeoPrompt] = []

    templates = {
        "brand": [
            "What is {brand}?",
            "Is {brand} a good place to buy {category}?",
            "What makes {brand} different from other {category} stores?",
            "Who is behind {brand}?",
            "Can I trust {brand} for online orders?",
            "What should I know before buying from {brand}?",
            "Does {brand} make custom or personalized products?",
            "Where does {brand} ship?",
            "What are {brand}'s most distinctive products?",
            "Is {brand} independent or marketplace-based?",
        ],
        "category": [
            "What is the best {category} for {use_case}?",
            "Where can I buy {category} online?",
            "What should I check before buying {category}?",
            "Which {category} brands are good for {persona}?",
            "What materials matter when buying {category}?",
            "How do I compare handmade {category} options?",
            "What is a fair price for {category}?",
            "Which {category} are suitable for international shipping?",
            "What makes a {category} feel premium?",
            "What are common mistakes when ordering {category} online?",
        ],
        "gift": [
            "What is a unique handmade gift for {persona}?",
            "What is a meaningful gift for {use_case}?",
            "Where can I buy personalized {category} as a gift?",
            "What are good one-of-one gifts from independent makers?",
            "What is a good gift for someone who has everything?",
            "What are thoughtful anniversary gifts from artist stores?",
            "What are good wedding gifts that are not mass-produced?",
            "What handmade gifts can be customized with names or initials?",
            "What are good gifts for someone who loves Chinese culture?",
            "What should I buy for a tea lover who values craft?",
        ],
        "comparison": [
            "{brand} vs {competitor} for {category}",
            "Handmade {category} vs mass-produced alternatives",
            "Custom {category} vs ready-to-ship {category}",
            "Artist-made gifts vs printed personalized gifts",
            "Independent artist store vs marketplace for {category}",
            "Which is better for {persona}: {brand} or {competitor}?",
            "Compare {product} with similar {category}",
            "What are the tradeoffs of custom vs standard {category}?",
            "Is one-of-one {category} worth it compared with cheaper options?",
            "Which {category} option feels most personal?",
        ],
        "alternative": [
            "What are alternatives to {competitor} for {category}?",
            "Which independent brands sell {category}?",
            "Where can I buy {category} outside major marketplaces?",
            "What are alternatives to printed personalized mugs?",
            "What are alternatives to generic gift boxes?",
            "Who makes one-of-one {category}?",
            "What small brands make {category} for {persona}?",
            "Where can I find artist-made {category}?",
            "What are niche DTC options for {category}?",
            "What brands should I shortlist for {category}?",
        ],
        "customization": [
            "How do custom {category} orders work?",
            "Can I personalize {category} before buying?",
            "What details do I need to provide for a custom order?",
            "How long does custom {category} take?",
            "Can I request Chinese calligraphy on a handmade gift?",
            "What are the limits of custom artist-made objects?",
            "Can I preview a custom {category} before it ships?",
            "What happens if a custom order is delayed?",
            "Are custom {category} orders refundable?",
            "What should I ask before commissioning {category}?",
        ],
        "trust": [
            "Is {brand} legitimate?",
            "Does {brand} have reviews or testimonials?",
            "Who makes the products at {brand}?",
            "Does {brand} show its making process?",
            "Are {brand}'s products actually handmade?",
            "What proof should I look for before buying {category}?",
            "Does {brand} have a clear contact method?",
            "Does {brand} have external profiles or press mentions?",
            "How can I verify artist-made {category}?",
            "What makes {brand} trustworthy for international buyers?",
        ],
        "shipping": [
            "Where does {brand} ship?",
            "How long does {brand} take to ship {category}?",
            "Does {brand} ship internationally?",
            "Can {category} arrive before a birthday or wedding?",
            "How is fragile {category} packaged?",
            "What shipping details should I check before buying {category}?",
            "Does {brand} provide tracking?",
            "What countries can buy from {brand}?",
            "How long do custom orders take before shipping?",
            "What happens if {category} arrives damaged?",
        ],
        "price_value": [
            "How much should handmade {category} cost?",
            "Is {brand} good value for {category}?",
            "Why are artist-made {category} more expensive?",
            "What affects the price of custom {category}?",
            "Is one-of-one {category} worth the price?",
            "What should I compare when evaluating {category} price?",
            "Are there affordable alternatives to {brand}?",
            "Does customization change the price of {category}?",
            "What is included in the price of {product}?",
            "How do I know if {category} pricing is fair?",
        ],
        "material_craft": [
            "What materials are used in {category}?",
            "How is {category} made?",
            "What craft process does {brand} use?",
            "How should I care for {category}?",
            "Are artist-made cups safe for daily use?",
            "Is {category} decorative or functional?",
            "What does handmade mean for {category}?",
            "What makes the craft quality of {category} visible?",
            "How does calligraphy change a personalized gift?",
            "What should product photos show for handmade {category}?",
        ],
        "buyer_persona": [
            "Is {category} a good fit for {persona}?",
            "What should {persona} consider before buying {category}?",
            "Which {category} works best for {persona}?",
            "What gift would {persona} actually use?",
            "Is {brand} suitable for {persona}?",
            "What custom details matter for {persona}?",
            "What does {persona} need to know about shipping?",
            "What {category} is best for {use_case}?",
            "What are good premium gifts for {persona}?",
            "What are safe choices for first-time buyers of {category}?",
        ],
        "gtm": [
            "Best {category} brands to cite in a gift guide",
            "Independent {category} stores for AI shopping shortlists",
            "What facts should an AI answer include about {brand}?",
            "Which pages should {brand} create for AI search?",
            "What schema should {brand} add for {category}?",
            "What collection pages should {brand} build?",
            "What comparison content should {brand} publish?",
            "What external profiles should cite {brand}?",
            "What questions should {brand}'s FAQ answer?",
            "What facts make {brand} recommendable by AI shopping agents?",
        ],
    }

    for bucket in PROMPT_BUCKETS:
        for template in templates[bucket]:
            prompt = template.format(
                brand=brand,
                category=category,
                competitor=_pick(competitors, len(prompts)),
                persona=_pick(personas, len(prompts)),
                use_case=_pick(use_cases, len(prompts)),
                product=_pick(products, len(prompts)),
            )
            prompt = _clean_prompt(prompt)
            prompts.append(
                GeoPrompt(
                    id=f"{bucket}_{len(prompts) + 1:03d}",
                    prompt=prompt,
                    language=language,
                    intentBucket=bucket,
                    commercialIntent=_commercial_intent(bucket),
                    priority=_prompt_priority(bucket),
                    targetAnswerRole=_target_answer_role(bucket),
                )
            )
    return prompts[:150]


def generate_patch_suggestions(
    config: GeoSkillConfig,
    store: StoreProfile,
    page: GeoPage,
    issues: list[GeoIssue],
    opportunities: list[GeoOpportunity],
) -> list[GeoPatchSuggestion]:
    issue_ids = {issue.id for issue in issues}
    patches = [
        GeoPatchSuggestion(
            id="opening_answer_block",
            pageUrl=page.url,
            patchType="opening_answer_block",
            title="Add an AI-readable opening answer block",
            rationale="Generative search systems need a concise factual answer before narrative or merchandising copy.",
            suggestedCopy=_opening_answer_copy(store, page),
            implementationNotes="Place this near the top of the page in visible HTML, ideally before image-heavy sections.",
            priority="high" if "thin_opening_answer" in issue_ids else "medium",
        ),
        GeoPatchSuggestion(
            id="faq_block",
            pageUrl=page.url,
            patchType="faq_block",
            title="Add a commerce-focused FAQ block",
            rationale="FAQ copy helps AI answer delivery, fit, customization, care, and refund questions without guessing.",
            suggestedCopy=_faq_copy(store, page),
            implementationNotes="Use visible FAQ markup and optionally add FAQPage JSON-LD using the same factual answers.",
            priority="high" if "missing_faq" in issue_ids else "medium",
        ),
    ]
    if "missing_product_schema" in issue_ids or page.pageType == "product":
        patches.append(
            GeoPatchSuggestion(
                id="product_schema_skeleton",
                pageUrl=page.url,
                patchType="product_schema",
                title="Add Product JSON-LD skeleton",
                rationale="Product schema gives AI crawlers a stable extraction path for offer and product facts.",
                suggestedCopy="Add Product JSON-LD with only merchant-verified fields. Do not invent ratings or reviews.",
                implementationNotes="Confirm price, currency, availability, image, material, dimensions, shipping, and return fields before publishing.",
                priority="high",
                suggestedSchema=_product_schema_skeleton(store, page),
            )
        )
    if "missing_organization_schema" in issue_ids:
        patches.append(
            GeoPatchSuggestion(
                id="organization_schema_skeleton",
                pageUrl=page.url,
                patchType="organization_schema",
                title="Add Organization or WebSite schema",
                rationale="Entity-level schema helps AI systems connect the store, brand, artist, domain, and social profiles.",
                suggestedCopy="Publish Organization/WebSite JSON-LD with brand name, canonical URL, sameAs links, and contact URL.",
                implementationNotes="Only include sameAs profiles the merchant actually controls.",
                priority="medium",
                suggestedSchema=_organization_schema_skeleton(store),
            )
        )
    if any(not image.get("alt") for image in page.images):
        patches.append(
            GeoPatchSuggestion(
                id="image_alt_text",
                pageUrl=page.url,
                patchType="image_alt_text",
                title="Add conservative image alt text",
                rationale="If product facts live only in images, AI systems may miss material, motif, customization, or gift context.",
                suggestedCopy=_image_alt_copy(store, page),
                implementationNotes="Base alt text on the actual image, filename, product title, and nearby text. Do not describe unseen details.",
                priority="medium",
            )
        )
    for opportunity in opportunities:
        if opportunity.recommendedAssetType in {"collection_page", "gift_guide", "commission_process_page", "artist_entity_page"}:
            patches.append(_patch_from_opportunity(store, opportunity))
    return _dedupe_patches(patches)[:12]


def _normalize_config(config: GeoSkillConfig) -> GeoSkillConfig:
    vertical = (config.vertical or "commerce").strip().lower()
    if vertical not in VERTICALS:
        vertical = "commerce"
    return GeoSkillConfig(
        targetUrl=config.targetUrl,
        brandName=_clean_optional(config.brandName),
        storeName=_clean_optional(config.storeName),
        category=_clean_optional(config.category) or "commerce products",
        market=[item for item in config.market if item],
        language=(config.language or "en").strip() or "en",
        competitors=[item for item in config.competitors if item],
        personas=[item for item in config.personas if item],
        useCases=[item for item in config.useCases if item],
        keyProducts=[item for item in config.keyProducts if item],
        maxPages=max(1, int(config.maxPages or 1)),
        includePromptPanel=bool(config.includePromptPanel),
        includePatchSuggestions=bool(config.includePatchSuggestions),
        vertical=vertical,
        outputFormat=config.outputFormat or "markdown",
    )


def _build_store_profile(config: GeoSkillConfig, html: str) -> StoreProfile:
    domain = urlparse(config.targetUrl).netloc or "local snapshot"
    text = _visible_text(html)
    brand = config.brandName or config.storeName or _infer_brand_from_html(html, domain)
    return StoreProfile(
        brandName=brand,
        domain=domain,
        category=config.category or "commerce products",
        vertical=config.vertical,
        targetMarkets=config.market or ["US", "international"],
        targetLanguages=[config.language or "en"],
        keyProducts=config.keyProducts or _infer_key_products(text, config.category or "commerce products"),
        buyerPersonas=config.personas or _default_personas(config.vertical),
        useCases=config.useCases or _default_use_cases(config.vertical),
        competitors=config.competitors,
        positioning=_infer_positioning(text, config.vertical, config.category or "commerce products"),
        uniqueClaims=_extract_claims(text),
    )


def _extract_page(url: str, html: str, *, robots_status: str, sitemap_status: str) -> GeoPage:
    text = _visible_text(html)
    jsonld_items, jsonld_warnings = _jsonld_items(html)
    schema_types = sorted(_item_types(jsonld_items))
    title = _extract_title(html)
    headings = _extract_headings(html)
    h1 = headings[0] if headings else None
    product_data = _extract_product_data(jsonld_items)
    return GeoPage(
        url=url,
        pageType=_detect_page_type(url, schema_types, text),
        title=title,
        metaDescription=_extract_meta(html, "description"),
        h1=h1,
        headings=headings,
        canonical=_extract_canonical(html),
        textContent=text,
        wordCount=len(text.split()),
        links=_extract_links(html),
        images=_extract_images(html),
        schemaTypes=schema_types,
        productData=product_data,
        faqData=_extract_faq(jsonld_items, text),
        extractedClaims=_extract_claims(text),
        lastModified=_extract_last_modified(html, text),
        crawlStatus={"robots": robots_status, "sitemap": sitemap_status, "jsonld_warnings": jsonld_warnings},
    )


def _audit_page(
    config: GeoSkillConfig,
    store: StoreProfile,
    page: GeoPage,
    robots_text: str | None,
    sitemap_status: str,
    llms_status: str,
) -> list[GeoIssue]:
    issues: list[GeoIssue] = []

    def add(issue_id: str, severity: str, category: str, title: str, description: str, why: str, recommendation: str, confidence: float = 0.85) -> None:
        issues.append(
            GeoIssue(
                id=issue_id,
                severity=severity,
                category=category,
                pageUrl=page.url,
                title=title,
                description=description,
                whyItMatters=why,
                recommendation=recommendation,
                confidence=confidence,
            )
        )

    if page.crawlStatus["robots"] != "found":
        add("robots_not_verified", "medium", "crawlability", "robots.txt not verified", "AgentShelf could not confirm robots.txt for this target.", "AI and search crawlers need crawl permissions to discover commerce pages.", "Publish and monitor robots.txt; confirm Googlebot, Bingbot, OAI-SearchBot, GPTBot, and ChatGPT-User are not unintentionally blocked.", 0.7)
    if sitemap_status not in {"found", "present"}:
        add("sitemap_not_verified", "medium", "crawlability", "Sitemap not verified", "AgentShelf could not confirm a sitemap for this target.", "Sitemaps help search and AI crawlers discover product, collection, FAQ, policy, and entity pages.", "Expose a sitemap with product, collection, about, FAQ, policy, and guide URLs.", 0.75)
    for crawler in _blocked_crawlers(robots_text or ""):
        add(f"crawler_blocked_{crawler.lower().replace('-', '_')}", "critical", "crawlability", f"{crawler} may be blocked", f"robots.txt appears to disallow {crawler}.", "Blocking AI/search crawlers can prevent pages from being indexed or cited.", f"Review robots.txt rules for {crawler}; allow commerce content unless there is a deliberate policy reason.", 0.8)
    if llms_status == "found":
        add("llms_txt_present", "info", "gtm", "llms.txt detected", "A llms.txt file was detected.", "llms.txt can document preferred AI-facing references, but it is not a Google ranking factor.", "Keep llms.txt factual and treat it as supplementary documentation, not a substitute for crawlable pages.", 0.9)
    if not page.canonical:
        add("missing_canonical", "medium", "indexability", "Missing canonical URL", "The page does not expose a canonical link.", "Canonical URLs reduce ambiguity when AI systems cluster merchant pages and product variants.", "Add a self-referencing canonical URL for indexable product and collection pages.")
    if _has_noindex(page.textContent):
        add("noindex_detected", "critical", "indexability", "Noindex detected", "Visible or metadata text suggests the page may be noindexed.", "Noindex pages are unlikely to appear in generative answers or shopping shortlists.", "Remove noindex from commercially important pages.")
    if _dynamic_rendering_likely(page):
        add("dynamic_rendering_likely", "high", "content_extractability", "Main content may be JS-rendered", "The static snapshot has sparse text with script-heavy markup.", "AI and search crawlers may miss price, stock, reviews, or customization options when critical content is injected late.", "Generate server-rendered product facts or use rendered snapshots for audit coverage.", 0.8)
    if not page.title:
        add("missing_title", "high", "content_extractability", "Missing title", "The page has no title element.", "Titles anchor entity matching and search snippets.", "Add a concise title with brand, product or collection, and category.")
    if not page.metaDescription:
        add("missing_meta_description", "medium", "content_extractability", "Missing meta description", "The page has no meta description.", "Meta descriptions give AI/search systems a short factual summary.", "Add a factual meta description with category, buyer, material, shipping or customization context.")
    if not page.h1:
        add("missing_h1", "high", "content_extractability", "Missing H1", "The page has no primary heading.", "A clear H1 helps agents identify the main entity or product.", "Add one descriptive H1 that matches the product, collection, brand, or guide intent.")
    if page.wordCount < 120:
        add("thin_text_content", "high", "content_extractability", "Thin visible text", f"The page has only {page.wordCount} visible words.", "Generative engines need extractable facts, not only images or scripts.", "Add factual visible copy covering what it is, who it is for, differentiation, buying constraints, and policies.")
    if not _opening_answer_present(page):
        add("thin_opening_answer", "high", "content_extractability", "Missing opening answer block", "The first 300 words do not clearly answer what the page/product is and who it is for.", "AI answers often cite concise factual passages near the top of the page.", "Add a 150-300 word opening answer block with product/store, buyer, differentiator, key attributes, and constraints.")

    schema_set = set(page.schemaTypes)
    if page.pageType == "product" and "product" not in schema_set:
        add("missing_product_schema", "high", "structured_data", "Missing Product schema", "Product JSON-LD was not detected.", "Product schema is the most reliable extraction path for AI-readable commerce facts.", "Add Product JSON-LD with verified name, description, image, brand, offer, material, dimensions, shipping, and return fields.")
    if page.pageType == "product" and "offer" not in schema_set and not page.productData.get("price"):
        add("missing_offer_schema", "high", "structured_data", "Missing Offer data", "The page lacks structured offer data for price, currency, and availability.", "Agents need unambiguous offer facts before recommending a product.", "Add Product.offers with verified price, priceCurrency, availability, and seller.")
    if not {"organization", "website"}.intersection(schema_set):
        add("missing_organization_schema", "medium", "structured_data", "Missing Organization/WebSite schema", "No Organization or WebSite schema was detected.", "Entity schema helps AI systems connect the brand, domain, social profiles, and contact points.", "Add Organization or WebSite JSON-LD with sameAs and contact URL.")
    if "faqpage" not in schema_set and not page.faqData:
        add("missing_faq", "medium", "structured_data", "Missing FAQ/FAQPage", "No FAQ content or FAQPage schema was detected.", "FAQ content covers objections and lets agents answer buyer questions safely.", "Add visible FAQ content and optional FAQPage JSON-LD.")
    for field_name, label in _required_product_fields(page.pageType):
        if not _field_present(page, field_name):
            add(f"missing_product_{field_name}", "medium", "commerce_attributes", f"Missing product {label}", f"The product page does not clearly expose {label}.", "AI shopping recommendations depend on concrete commerce attributes, not brand storytelling alone.", f"Add verified {label} in visible copy and, when relevant, structured data.", 0.78)

    if not _mentions_any(page.textContent, ["who it is for", "best for", "ideal for", "gift for", "made for"]):
        add("missing_who_it_is_for", "medium", "content_extractability", "Buyer fit is unclear", "The page does not clearly say who the product or store is best for.", "Agents need buyer-fit language to match products to user intent.", "Add a short 'best for' or 'who it is for' section.")
    if not _mentions_any(page.textContent, ["different", "unique", "one-of-one", "handmade", "custom", "artist-made", "limited"]):
        add("missing_differentiation", "medium", "content_extractability", "Differentiation is unclear", "The page does not clearly state what makes the offer different.", "AI shortlists favor products with specific, comparable differentiators.", "Add factual differentiation: process, material, customization, edition size, provenance, or use case.")
    if _marketing_heavy(page.textContent):
        add("marketing_without_facts", "medium", "content_extractability", "Marketing-heavy copy lacks facts", "The page uses broad promotional language without enough concrete details.", "Generative answers need verifiable facts to cite, compare, and recommend.", "Replace vague claims with material, process, timeline, policy, proof, and limitations.")

    if store.brandName and not _mentions_any(page.title + " " + (page.h1 or "") + " " + page.textContent[:800], [store.brandName]):
        add("brand_name_inconsistent", "high", "entity_consistency", "Brand name is not consistently visible", "Configured brand/store name is not visible in key page areas.", "Entity consistency helps AI systems connect the domain, product, and brand.", "Use the same brand/store name in title, H1, about copy, footer, and schema.", 0.7)
    if not _has_link(page, ("about", "story", "artist", "studio", "founder")):
        add("missing_about_or_artist_page", "medium", "entity_consistency", "Missing about/artist entity link", "No about, artist, studio, or founder link was detected.", "Independent commerce needs entity proof so AI can explain who makes or sells the product.", "Add and internally link an about, artist, studio, or founder page.")
    if not _has_link(page, ("contact", "support")) and not _mentions_any(page.textContent, ["contact", "@", "email"]):
        add("missing_contact_method", "medium", "trust", "Contact path is unclear", "No clear contact link or contact method was detected.", "AI recommendations are safer when buyers can resolve shipping, custom order, or trust questions.", "Add a clear contact link, email, form, or support page.")
    if not _has_link(page, ("instagram", "youtube", "tiktok", "pinterest", "linkedin", "x.com", "twitter")):
        add("missing_external_profiles", "low", "external_authority", "External profiles not linked", "No social or external authority profiles were detected.", "External profiles help entity validation and provide proof of real work or community.", "Link controlled artist, studio, brand, portfolio, or social profiles where appropriate.")
    if store.vertical in {"artist_store", "creator_commerce"} and not _mentions_any(page.textContent, ["artist", "studio", "handmade", "made by", "process", "commission"]):
        add("missing_artist_or_process_story", "high", "trust", "Artist/process story is missing", "The page does not explain the maker, studio, or process.", "Creator commerce depends on provenance and craft proof for AI trust and buyer confidence.", "Add an artist/studio factsheet and process section with verified details.")
    if not _mentions_any(page.textContent, ["review", "testimonial", "customer", "buyer said", "rating"]):
        add("missing_social_proof", "medium", "trust", "Social proof is missing", "No reviews, testimonials, or buyer proof were detected.", "Agents use proof signals to rank comparable products and reduce buyer risk.", "Add real reviews, testimonials, portfolio examples, or buyer quotes. Do not fabricate ratings.")
    if not _mentions_any(page.textContent, ["shipping", "delivery", "ships", "tracking"]):
        add("missing_shipping_policy", "high", "trust", "Shipping policy is missing", "Shipping timing, regions, or cost are not clear.", "AI recommendations often depend on destination and deadline constraints.", "Add shipping regions, timelines, packaging notes, and tracking expectations.")
    if not _mentions_any(page.textContent, ["return", "refund", "exchange", "cancel"]):
        add("missing_return_policy", "high", "trust", "Return/cancellation policy is missing", "Return, refund, exchange, or cancellation terms are not clear.", "Agents need policy boundaries before recommending custom or fragile goods.", "Add concise return and cancellation policy copy, especially for custom orders.")
    if store.vertical in {"artist_store", "creator_commerce"} and not _mentions_any(page.textContent, ["portfolio", "gallery", "past work", "examples"]):
        add("missing_portfolio_gallery", "medium", "trust", "Portfolio/gallery proof is missing", "No portfolio, gallery, or past work signal was detected.", "Visual proof and previous work help AI and buyers validate one-of-one claims.", "Add a portfolio or gallery page and link it from product and about pages.")

    missing_assets = _missing_intent_assets(store, page)
    for asset_id, title, recommendation in missing_assets:
        add(asset_id, "medium", "ai_intent_coverage", title, "The current site/page set does not appear to cover this high-intent AI query pattern.", "GEO for commerce works when AI systems can cite intent-specific pages, not only product grids.", recommendation, 0.72)
    return issues


def _build_opportunities(
    config: GeoSkillConfig,
    store: StoreProfile,
    page: GeoPage,
    issues: list[GeoIssue],
    prompts: list[GeoPrompt],
) -> list[GeoOpportunity]:
    prompt_by_bucket = {bucket: [prompt.prompt for prompt in prompts if prompt.intentBucket == bucket][:4] for bucket in PROMPT_BUCKETS}
    opportunities = [
        GeoOpportunity(
            id="collection_page_ai_shortlist",
            category="gtm",
            title=f"Build a collection page for {store.category}",
            description="Create an intent-specific collection page with factual intro copy, product cards, filters, FAQ, and proof.",
            expectedImpact="Improves retrieval for category and shortlist queries.",
            effort="medium",
            recommendedAssetType="collection_page",
            relatedPrompts=prompt_by_bucket.get("category", []),
        ),
        GeoOpportunity(
            id="gift_guide",
            category="gtm",
            title="Publish a gift guide for high-intent buyers",
            description="Create a gift guide that maps products to buyer persona, occasion, budget, customization, shipping deadline, and proof.",
            expectedImpact="Captures gift and recommendation prompts where agents need curated options.",
            effort="medium",
            recommendedAssetType="gift_guide",
            relatedPrompts=prompt_by_bucket.get("gift", []),
        ),
        GeoOpportunity(
            id="faq_asset",
            category="ai_intent_coverage",
            title="Create an AI-answerable commerce FAQ",
            description="Answer customization, shipping, return, care, lead time, authenticity, and pricing questions in one crawlable asset.",
            expectedImpact="Reduces hallucination risk and improves answerability for commercial prompts.",
            effort="low",
            recommendedAssetType="faq",
            relatedPrompts=prompt_by_bucket.get("trust", []) + prompt_by_bucket.get("shipping", []),
        ),
    ]
    if store.vertical in {"artist_store", "creator_commerce"}:
        opportunities.extend(
            [
                GeoOpportunity(
                    id="commission_process_page",
                    category="gtm",
                    title="Create a custom order / commission process page",
                    description="Explain request intake, personalization options, timeline, approval, shipping, cancellations, and what cannot be customized.",
                    expectedImpact="Captures customization prompts and makes custom work safer to recommend.",
                    effort="medium",
                    recommendedAssetType="commission_process_page",
                    relatedPrompts=prompt_by_bucket.get("customization", []),
                ),
                GeoOpportunity(
                    id="artist_entity_page",
                    category="external_authority",
                    title="Create an artist/studio entity factsheet",
                    description="Publish verified maker, studio, medium, process, portfolio, location, social profiles, press kit, and contact facts.",
                    expectedImpact="Improves entity consistency and citation quality for independent creator commerce.",
                    effort="medium",
                    recommendedAssetType="artist_entity_page",
                    relatedPrompts=prompt_by_bucket.get("brand", []),
                ),
            ]
        )
    if any(issue.id.startswith("missing_product_") for issue in issues):
        opportunities.append(
            GeoOpportunity(
                id="schema_patch",
                category="structured_data",
                title="Patch Product and Organization schema",
                description="Add merchant-verified Product, Offer, Organization, WebSite, FAQPage, and policy fields where available.",
                expectedImpact="Improves machine extraction for AI shopping and search systems.",
                effort="low",
                recommendedAssetType="schema",
                relatedPrompts=prompt_by_bucket.get("gtm", []),
            )
        )
    return opportunities


def _category_scores(issues: list[GeoIssue]) -> dict[str, int]:
    scores = {category: 100 for category in GEO_CATEGORIES}
    for issue in issues:
        scores[issue.category] = max(0, scores.get(issue.category, 100) - SEVERITY_PENALTY[issue.severity])
    return scores


def _jsonld_blocks(html: str) -> list[str]:
    return re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html, flags=re.IGNORECASE)


def _jsonld_items(html: str) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    warnings: list[str] = []
    for block in _jsonld_blocks(html):
        try:
            parsed = json.loads(html_lib.unescape(block).strip())
        except json.JSONDecodeError as exc:
            warnings.append(f"Malformed JSON-LD ignored: {exc.msg}.")
            continue
        items.extend(_flatten_jsonld(parsed))
    return items, warnings


def _flatten_jsonld(value: object) -> list[dict]:
    if isinstance(value, dict):
        items = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            items.extend(item for item in graph if isinstance(item, dict))
        return items
    if isinstance(value, list):
        items: list[dict] = []
        for item in value:
            items.extend(_flatten_jsonld(item))
        return items
    return []


def _item_types(items: list[dict]) -> set[str]:
    types: set[str] = set()
    for item in items:
        raw = item.get("@type")
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if value:
                types.add(str(value).lower())
        if item.get("offers"):
            types.add("offer")
    return types


def _visible_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_ws(html_lib.unescape(text))


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, flags=re.IGNORECASE)
    return _normalize_ws(html_lib.unescape(match.group(1))) if match else ""


def _extract_meta(html: str, name: str) -> str | None:
    patterns = [
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _normalize_ws(html_lib.unescape(match.group(1)))
    return None


def _extract_canonical(html: str) -> str | None:
    match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    return html_lib.unescape(match.group(1)).strip() if match else None


def _extract_headings(html: str) -> list[str]:
    headings = []
    for match in re.finditer(r"<h[1-3][^>]*>([\s\S]*?)</h[1-3]>", html, flags=re.IGNORECASE):
        text = _normalize_ws(re.sub(r"<[^>]+>", " ", match.group(1)))
        if text:
            headings.append(html_lib.unescape(text))
    return headings


def _extract_links(html: str) -> list[dict]:
    links = []
    for match in re.finditer(r"<a\b([^>]*)>([\s\S]*?)</a>", html, flags=re.IGNORECASE):
        attrs = match.group(1)
        href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, flags=re.IGNORECASE)
        if not href_match:
            continue
        text = _normalize_ws(re.sub(r"<[^>]+>", " ", match.group(2)))
        links.append({"href": html_lib.unescape(href_match.group(1)), "text": html_lib.unescape(text)})
    return links[:200]


def _extract_images(html: str) -> list[dict]:
    images = []
    for match in re.finditer(r"<img\b([^>]*)>", html, flags=re.IGNORECASE):
        attrs = match.group(1)
        src = _attr(attrs, "src") or _attr(attrs, "data-src") or ""
        images.append({"src": html_lib.unescape(src), "alt": html_lib.unescape(_attr(attrs, "alt") or "")})
    return images[:200]


def _attr(attrs: str, name: str) -> str | None:
    match = re.search(rf'{name}=["\']([^"\']*)["\']', attrs, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_product_data(items: list[dict]) -> dict:
    for item in items:
        raw_type = item.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(str(type_name).lower() == "product" for type_name in types):
            continue
        offers = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        return {
            "name": item.get("name"),
            "description": item.get("description"),
            "image": item.get("image"),
            "brand": item.get("brand"),
            "sku": item.get("sku"),
            "material": item.get("material"),
            "color": item.get("color"),
            "size": item.get("size") or item.get("depth") or item.get("height") or item.get("width"),
            "price": offers.get("price") if isinstance(offers, dict) else None,
            "priceCurrency": offers.get("priceCurrency") if isinstance(offers, dict) else None,
            "availability": offers.get("availability") if isinstance(offers, dict) else None,
            "shippingDetails": offers.get("shippingDetails") if isinstance(offers, dict) else None,
            "hasMerchantReturnPolicy": offers.get("hasMerchantReturnPolicy") if isinstance(offers, dict) else None,
            "aggregateRating": item.get("aggregateRating"),
        }
    return {}


def _extract_faq(items: list[dict], text: str) -> list[dict]:
    faqs = []
    for item in items:
        raw_type = item.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(str(type_name).lower() == "faqpage" for type_name in types):
            continue
        for entity in item.get("mainEntity", []) if isinstance(item.get("mainEntity"), list) else []:
            if isinstance(entity, dict):
                answer = entity.get("acceptedAnswer") if isinstance(entity.get("acceptedAnswer"), dict) else {}
                faqs.append({"question": entity.get("name"), "answer": answer.get("text")})
    if not faqs and re.search(r"\bfaq\b|frequently asked|questions", text, flags=re.IGNORECASE):
        faqs.append({"question": "FAQ section detected", "answer": None})
    return faqs


def _detect_page_type(url: str, schema_types: list[str], text: str) -> str:
    path = urlparse(url).path.lower()
    lower = text.lower()
    product_path = "product" in path or "products" in path
    product_copy = any(token in lower for token in ("add to cart", "buy now", "sku", "price:", "made to order"))
    if "product" in schema_types or product_path or product_copy:
        return "product"
    if "collectionpage" in schema_types or "/collection" in path or "/category" in path:
        return "collection"
    if "faq" in path or "faqpage" in schema_types:
        return "faq"
    if "return" in path or "shipping" in path or "policy" in path:
        return "policy"
    if "about" in path or "artist" in path or "studio" in path:
        return "about"
    if "article" in schema_types or "/blog" in path:
        return "article"
    if path in {"", "/"}:
        return "home"
    return "unknown"


def _extract_last_modified(html: str, text: str) -> str | None:
    for pattern in (
        r'<meta[^>]+property=["\']article:modified_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
        r"(?:last updated|updated on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
    ):
        match = re.search(pattern, html + "\n" + text, flags=re.IGNORECASE)
        if match:
            return html_lib.unescape(match.group(1)).strip()
    return None


def _extract_claims(text: str) -> list[str]:
    patterns = [
        r"[^.]{0,60}\b(?:handmade|one-of-one|custom|personalized|artist-made|limited edition|made to order|sustainable|premium|authentic)\b[^.]{0,120}",
        r"[^.]{0,60}\b(?:ships?|delivery|returns?|refund|care|material|crafted|painted|calligraphy)\b[^.]{0,120}",
    ]
    claims = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            claim = _normalize_ws(match.group(0))
            if claim and claim.lower() not in seen:
                claims.append(claim)
                seen.add(claim.lower())
            if len(claims) >= 8:
                return claims
    return claims


def _infer_brand_from_html(html: str, domain: str) -> str:
    title = _extract_title(html)
    if title:
        return re.split(r"\s+[|-]\s+", title)[-1 if "|" in title else 0].strip() or title
    if domain and domain != "local snapshot":
        return domain.split(".")[-2].replace("-", " ").title() if "." in domain else domain
    return "Unknown Store"


def _infer_key_products(text: str, category: str) -> list[str]:
    candidates = []
    for token in ("teacup", "cup", "calligraphy", "gift", "print", "ceramic", "jewelry", "poster", "commission"):
        if re.search(rf"\b{token}s?\b", text, flags=re.IGNORECASE):
            candidates.append(token)
    return candidates[:5] or [category]


def _infer_positioning(text: str, vertical: str, category: str) -> str:
    if vertical == "artist_store":
        return f"Independent artist commerce for {category}"
    if "handmade" in text.lower() or "custom" in text.lower():
        return f"Creator-led commerce for {category}"
    return f"Commerce brand for {category}"


def _default_personas(vertical: str) -> list[str]:
    if vertical in {"artist_store", "creator_commerce"}:
        return ["gift buyers", "tea lovers", "collectors", "wedding gift shoppers", "buyers who value craft"]
    return ["online shoppers", "gift buyers", "first-time buyers", "repeat customers", "comparison shoppers"]


def _default_use_cases(vertical: str) -> list[str]:
    if vertical in {"artist_store", "creator_commerce"}:
        return ["personalized gifts", "wedding gifts", "meaningful cultural gifts", "custom commissions", "collector display pieces"]
    return ["buying online", "gift shopping", "comparing alternatives", "choosing a premium option", "checking shipping deadlines"]


def _required_product_fields(page_type: str) -> list[tuple[str, str]]:
    if page_type != "product":
        return []
    return [
        ("type", "product type"),
        ("material", "material"),
        ("size", "size or dimensions"),
        ("price", "price"),
        ("availability", "inventory state"),
        ("customization", "customization options"),
        ("lead_time", "production or delivery lead time"),
        ("shipping_country", "shipping countries"),
        ("packaging", "packaging details"),
        ("care", "care instructions"),
        ("return_policy", "return or cancellation policy"),
        ("gift_occasion", "gift occasions"),
    ]


def _field_present(page: GeoPage, field_name: str) -> bool:
    text = page.textContent.lower()
    product = page.productData
    checks = {
        "type": bool(product.get("name")) or _mentions_any(text, ["type", "category", "product"]),
        "material": bool(product.get("material")) or _mentions_any(text, ["material", "ceramic", "porcelain", "stoneware", "cotton", "wood", "paper"]),
        "size": bool(product.get("size")) or _mentions_any(text, ["size", "dimension", "capacity", "oz", "cm", "inch"]),
        "price": bool(product.get("price")) or bool(re.search(r"\$\s?\d|usd\s?\d|price", text, flags=re.IGNORECASE)),
        "availability": bool(product.get("availability")) or _mentions_any(text, ["in stock", "sold out", "available", "made to order"]),
        "customization": _mentions_any(text, ["custom", "personalized", "commission", "made to order", "name", "initials"]),
        "lead_time": _mentions_any(text, ["business days", "lead time", "weeks", "made in", "ships in", "production time"]),
        "shipping_country": _mentions_any(text, ["united states", "usa", "us shipping", "canada", "uk", "europe", "international", "worldwide"]),
        "packaging": _mentions_any(text, ["packaging", "gift box", "wrapped", "fragile", "protective"]),
        "care": _mentions_any(text, ["care", "wash", "dishwasher", "hand wash", "display only"]),
        "return_policy": _mentions_any(text, ["return", "refund", "exchange", "cancel"]),
        "gift_occasion": _mentions_any(text, ["gift", "wedding", "anniversary", "birthday", "holiday"]),
    }
    return checks[field_name]


def _mentions_any(text: str, tokens: list[str]) -> bool:
    lower = text.lower()
    return any(token.lower() in lower for token in tokens)


def _has_link(page: GeoPage, tokens: tuple[str, ...]) -> bool:
    for link in page.links:
        combined = f"{link.get('href', '')} {link.get('text', '')}".lower()
        if any(token in combined for token in tokens):
            return True
    return False


def _has_noindex(text: str) -> bool:
    return "noindex" in text.lower()


def _dynamic_rendering_likely(page: GeoPage) -> bool:
    return page.wordCount < 60 and len(page.images) < 2 and not page.schemaTypes


def _opening_answer_present(page: GeoPage) -> bool:
    opening = " ".join(page.textContent.split()[:300]).lower()
    return _mentions_any(opening, ["is a", "is an", "made for", "best for", "custom", "handmade", "ships", "made to order"]) and len(opening.split()) >= 50


def _marketing_heavy(text: str) -> bool:
    marketing = len(re.findall(r"\b(?:beautiful|amazing|perfect|unique|premium|authentic|best|elevate|timeless)\b", text, flags=re.IGNORECASE))
    facts = len(re.findall(r"\b(?:material|size|dimension|shipping|return|care|days|price|made by|process|sku)\b", text, flags=re.IGNORECASE))
    return marketing >= 5 and facts < 5


def _missing_intent_assets(store: StoreProfile, page: GeoPage) -> list[tuple[str, str, str]]:
    text = page.textContent.lower()
    assets = []
    if "gift" in " ".join(store.useCases).lower() and not _has_link(page, ("gift", "guide")):
        assets.append(("missing_gift_guide", "Gift guide intent is uncovered", "Create a gift guide mapped to buyer persona, occasion, shipping deadline, and customization options."))
    if not _has_link(page, ("compare", "alternative", "versus", "vs")):
        assets.append(("missing_comparison_asset", "Comparison intent is uncovered", "Create comparison content against common alternatives without making unsupported competitor claims."))
    if store.vertical in {"artist_store", "creator_commerce"} and not _has_link(page, ("commission", "custom", "process")):
        assets.append(("missing_commission_process_asset", "Commission/custom process intent is uncovered", "Create a custom order process page with timeline, inputs, revisions, shipping, and cancellation boundaries."))
    if not _mentions_any(text, ["faq", "frequently asked"]):
        assets.append(("missing_buyer_questions_asset", "Buyer question intent is uncovered", "Create or expand FAQ coverage for price, shipping, returns, care, fit, customization, and trust."))
    return assets[:5]


def _blocked_crawlers(robots_text: str) -> list[str]:
    if not robots_text.strip():
        return []
    crawlers = ["Googlebot", "Bingbot", "OAI-SearchBot", "GPTBot", "ChatGPT-User"]
    blocked = []
    groups = _robots_groups(robots_text)
    for crawler in crawlers:
        rules = []
        for agents, disallows in groups:
            if "*" in agents or crawler.lower() in agents:
                rules.extend(disallows)
        if "/" in rules:
            blocked.append(crawler)
    return blocked


def _robots_groups(robots_text: str) -> list[tuple[set[str], list[str]]]:
    groups = []
    current_agents: set[str] = set()
    current_disallows: list[str] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            if current_agents and not current_disallows:
                current_agents.add(value.lower())
                continue
            if current_agents or current_disallows:
                groups.append((current_agents, current_disallows))
            current_agents = {value.lower()}
            current_disallows = []
        elif key == "disallow":
            current_disallows.append(value)
    if current_agents or current_disallows:
        groups.append((current_agents, current_disallows))
    return groups


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _pick(values: list[str], index: int) -> str:
    return values[index % len(values)] if values else ""


def _commercial_intent(bucket: str) -> str:
    return "high" if bucket in {"gift", "comparison", "alternative", "customization", "shipping", "price_value"} else "medium"


def _clean_prompt(prompt: str) -> str:
    prompt = re.sub(r"\bcustom custom\b", "custom", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"\bhandmade handmade\b", "handmade", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt


def _prompt_priority(bucket: str) -> int:
    if bucket in {"gift", "category", "customization", "trust"}:
        return 1
    if bucket in {"comparison", "shipping", "price_value", "material_craft"}:
        return 2
    return 3


def _target_answer_role(bucket: str) -> str:
    mapping = {
        "brand": "be_cited",
        "category": "be_recommended",
        "gift": "be_recommended",
        "comparison": "be_compared",
        "alternative": "be_compared",
        "customization": "educate_category",
        "trust": "correct_fact",
        "shipping": "correct_fact",
        "price_value": "be_compared",
        "material_craft": "educate_category",
        "buyer_persona": "be_recommended",
        "gtm": "be_cited",
    }
    return mapping[bucket]


def _opening_answer_copy(store: StoreProfile, page: GeoPage) -> str:
    product = page.productData.get("name") or page.h1 or store.keyProducts[0]
    return (
        f"This page is about {product}, a {store.category} offer from {store.brandName}. "
        f"It is best for {', '.join(store.buyerPersonas[:2])}. "
        f"Key attributes should state material, size, availability, customization, shipping regions, lead time, care, and return boundaries. "
        f"The main difference from alternatives should be described with verified craft, process, provenance, or service facts. "
        "Keep this block factual and update it when product details change."
    )


def _faq_copy(store: StoreProfile, page: GeoPage) -> str:
    questions = [
        "What is this product?",
        "Who is it for?",
        "Can it be customized?",
        "How long does it take to make or ship?",
        "Where do you ship?",
        "Is each piece unique?",
        "How should it be cared for?",
        "What is the return or cancellation policy?",
    ]
    return "Add FAQ questions: " + " | ".join(questions) + f" Answer each with verified {store.brandName} policy and product facts."


def _product_schema_skeleton(store: StoreProfile, page: GeoPage) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": page.productData.get("name") or page.h1 or "CONFIRM_PRODUCT_NAME",
        "description": page.metaDescription or "CONFIRM_PRODUCT_DESCRIPTION",
        "brand": {"@type": "Brand", "name": store.brandName},
        "image": "CONFIRM_IMAGE_URL",
        "material": page.productData.get("material") or "CONFIRM_MATERIAL_IF_RELEVANT",
        "offers": {
            "@type": "Offer",
            "price": page.productData.get("price") or "CONFIRM_PRICE",
            "priceCurrency": page.productData.get("priceCurrency") or "CONFIRM_CURRENCY",
            "availability": page.productData.get("availability") or "CONFIRM_AVAILABILITY",
            "url": page.url,
        },
    }


def _organization_schema_skeleton(store: StoreProfile) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": store.brandName,
        "url": f"https://{store.domain}" if store.domain != "local snapshot" else "CONFIRM_CANONICAL_SITE_URL",
        "sameAs": ["CONFIRM_SOCIAL_OR_PORTFOLIO_URLS"],
        "contactPoint": {"@type": "ContactPoint", "contactType": "customer support", "url": "CONFIRM_CONTACT_URL"},
    }


def _image_alt_copy(store: StoreProfile, page: GeoPage) -> str:
    product = page.productData.get("name") or page.h1 or store.category
    examples = []
    for image in page.images[:5]:
        src = image.get("src") or "image"
        if image.get("alt"):
            continue
        filename = src.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
        examples.append(f"{src}: '{product} by {store.brandName}; confirm visible material, motif, and use from image {filename}.'")
    return "Suggested conservative alt text examples: " + " | ".join(examples or [f"{product} by {store.brandName}; confirm visible details before publishing."])


def _patch_from_opportunity(store: StoreProfile, opportunity: GeoOpportunity) -> GeoPatchSuggestion:
    patch_type = {
        "collection_page": "collection_page_brief",
        "gift_guide": "gift_guide_brief",
        "commission_process_page": "commission_process",
        "artist_entity_page": "artist_entity_factsheet",
    }.get(opportunity.recommendedAssetType, "collection_page_brief")
    sections = {
        "collection_page_brief": "Intro answer block, product selection rules, buyer fit, comparison criteria, FAQ, internal links, trust proof.",
        "gift_guide_brief": "Occasions, recipient personas, budget bands, shipping deadlines, personalization options, proof, FAQ.",
        "commission_process": "Inquiry, design inputs, quote, timeline, approval, making, shipping, cancellation boundaries, contact.",
        "artist_entity_factsheet": "Artist name, studio, medium, style, process, location, custom work, portfolio, social profiles, press kit, contact.",
    }
    return GeoPatchSuggestion(
        id=opportunity.id,
        patchType=patch_type,
        title=opportunity.title,
        rationale=opportunity.description,
        suggestedCopy=f"Create a {opportunity.recommendedAssetType.replace('_', ' ')} for {store.brandName}: {sections[patch_type]}",
        implementationNotes="Use visible HTML, stable internal links, and only merchant-verified facts.",
        priority="medium",
    )


def _dedupe_patches(patches: list[GeoPatchSuggestion]) -> list[GeoPatchSuggestion]:
    seen = set()
    deduped = []
    for patch in patches:
        if patch.id in seen:
            continue
        deduped.append(patch)
        seen.add(patch.id)
    return deduped


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
