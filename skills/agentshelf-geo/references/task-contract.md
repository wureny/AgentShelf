# AgentShelf GEO Task Contract

`agentshelf geo-tasks <geo-report.json>` emits JSONL. Each line is one task:

```json
{
  "contract": "agentshelf.geo_task.v0",
  "source": "examples/artist_store_product.html",
  "page_url": "examples/artist_store_product.html",
  "task": {
    "id": "product_schema_skeleton",
    "title": "Add Product JSON-LD skeleton",
    "priority": "high",
    "impact": "high",
    "effort": "medium",
    "type": "patch",
    "patch_type": "product_schema",
    "pageUrl": "examples/artist_store_product.html",
    "pageArea": "Product JSON-LD builder, product template, or schema component",
    "issueIds": [],
    "opportunityIds": [],
    "reason": "Product schema gives AI crawlers a stable extraction path for offer and product facts.",
    "files_or_page_area": "Product JSON-LD builder, product template, or schema component",
    "filesOrPageArea": ["Product JSON-LD builder, product template, or schema component"],
    "instructions": [
      "Confirm price, currency, availability, image, material, dimensions, shipping, and return fields before publishing.",
      "Use only merchant-confirmed facts already present in source data or approved by the merchant.",
      "Do not add aggregateRating, review, award, press, or popularity fields unless real source data exists."
    ],
    "suggested_copy": "Add Product JSON-LD with only merchant-verified fields. Do not invent ratings or reviews.",
    "suggested_schema": {},
    "implementation_notes": "Confirm price, currency, availability, image, material, dimensions, shipping, and return fields before publishing.",
    "acceptance_check": "Re-run `agentshelf geo-audit ... --format json` and confirm Product and Offer schema issues are resolved without fake ratings or reviews.",
    "acceptanceCriteria": [
      "Re-run `agentshelf geo-audit ... --format json` and confirm Product and Offer schema issues are resolved without fake ratings or reviews.",
      "No fake aggregateRating, review, testimonial, award, press, or popularity fields are added.",
      "The same task does not reappear as a high-priority blocker after rerunning AgentShelf."
    ],
    "verification_command": "agentshelf geo-audit examples/artist_store_product.html --format json",
    "verificationCommand": "agentshelf geo-audit examples/artist_store_product.html --format json",
    "expectedReportDelta": "Product/Offer structured-data issues should be absent or downgraded without fake reviews or ratings.",
    "riskNotes": [
      "This task improves deterministic AI-readability evidence; it does not prove live AI provider visibility or ranking lift.",
      "Do not add claims that cannot be verified from merchant-owned source data.",
      "Schema must mirror visible or merchant-confirmed facts; avoid fake ratings, reviews, and offers."
    ]
  }
}
```

## Field Use

- `task.id`: stable identifier for grouping repeat work.
- `priority`: handle `critical` and `high` before `medium` and `low`.
- `impact` and `effort`: help coding agents sequence high-value, feasible work.
- `patch_type`: tells the implementation shape, such as `opening_answer_block`, `faq_block`, `product_schema`, `organization_schema`, `image_alt_text`, `collection_page_brief`, `gift_guide_brief`, `commission_process`, or `artist_entity_factsheet`.
- `files_or_page_area`: first place to inspect in the target repo.
- `instructions`: implementation steps that can be followed without parsing the prose report.
- `suggested_copy`: draft copy or brief; revise to fit the merchant voice but keep factual claims.
- `suggested_schema`: schema scaffold; remove placeholders or mark them as merchant-confirmed before production.
- `acceptance_check`: condition that should become true after edits.
- `acceptanceCriteria`: expanded checklist for coding agents and reviewers.
- `verification_command`: baseline command; add the same brand/category/vertical flags used in the original audit when rerunning manually.
- `expectedReportDelta`: expected change in the next AgentShelf report.
- `riskNotes`: safety boundaries; these are part of the task, not optional marketing copy.

## Safety Rules

- Do not fabricate reviews, aggregate ratings, press mentions, certifications, inventory, discounts, delivery promises, or return policies.
- Do not state a product is handmade, one-of-one, safe for food use, microwave safe, dishwasher safe, or internationally shippable unless the source data supports it.
- For artist/creator commerce, preserve boundaries around custom work: timeline, revision process, cancellation, returns, packaging, and damage handling must be explicit.
