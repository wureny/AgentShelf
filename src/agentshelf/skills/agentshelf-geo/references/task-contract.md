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
    "type": "patch",
    "patch_type": "product_schema",
    "reason": "Product schema gives AI crawlers a stable extraction path for offer and product facts.",
    "files_or_page_area": "Product JSON-LD builder, product template, or schema component",
    "suggested_copy": "Add Product JSON-LD with only merchant-verified fields. Do not invent ratings or reviews.",
    "suggested_schema": {},
    "implementation_notes": "Confirm price, currency, availability, image, material, dimensions, shipping, and return fields before publishing.",
    "acceptance_check": "Re-run `agentshelf geo-audit ... --format json` and confirm Product and Offer schema issues are resolved without fake ratings or reviews.",
    "verification_command": "agentshelf geo-audit examples/artist_store_product.html --format json"
  }
}
```

## Field Use

- `task.id`: stable identifier for grouping repeat work.
- `priority`: handle `critical` and `high` before `medium` and `low`.
- `patch_type`: tells the implementation shape, such as `opening_answer_block`, `faq_block`, `product_schema`, `organization_schema`, `image_alt_text`, `collection_page_brief`, `gift_guide_brief`, `commission_process`, or `artist_entity_factsheet`.
- `files_or_page_area`: first place to inspect in the target repo.
- `suggested_copy`: draft copy or brief; revise to fit the merchant voice but keep factual claims.
- `suggested_schema`: schema scaffold; remove placeholders or mark them as merchant-confirmed before production.
- `acceptance_check`: condition that should become true after edits.
- `verification_command`: baseline command; add the same brand/category/vertical flags used in the original audit when rerunning manually.

## Safety Rules

- Do not fabricate reviews, aggregate ratings, press mentions, certifications, inventory, discounts, delivery promises, or return policies.
- Do not state a product is handmade, one-of-one, safe for food use, microwave safe, dishwasher safe, or internationally shippable unless the source data supports it.
- For artist/creator commerce, preserve boundaries around custom work: timeline, revision process, cancellation, returns, packaging, and damage handling must be explicit.
