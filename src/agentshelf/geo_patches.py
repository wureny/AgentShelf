from __future__ import annotations

from agentshelf.geo_types import GeoIssue, GeoOpportunity, GeoPage, GeoPatchSuggestion, GeoSkillConfig, StoreProfile


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
    return "Suggested conservative alt text examples: " + " | ".join(
        examples or [f"{product} by {store.brandName}; confirm visible details before publishing."]
    )


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
