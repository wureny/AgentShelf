# Agent Loop Example

Use this reference when you need a concrete Codex-style implementation loop.

Install this skill into a merchant repository with:

```bash
agentshelf export-skill --output-dir .codex/skills
```

## Before

```bash
agentshelf geo-run examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir /tmp/agentshelf-before \
  --format json
```

The before page should produce a weak product-readiness scan and high-priority tasks such as `missing_product_schema` and `missing_offer_schema`.

## Implementation Pattern

Read `geo-tasks.jsonl`, then edit the storefront, fixture, template, schema builder, or product data mapper. Prioritize:

1. Product and Offer JSON-LD using merchant-verified price, currency, availability, seller, shipping, and return data.
2. Visible opening answer copy near the H1.
3. FAQ copy and optional FAQPage JSON-LD from visible answers.
4. Conservative image alt text.
5. Internal links to collection, gift guide, custom-order, about/artist, contact, and proof pages when those pages exist.

Do not fabricate reviews, ratings, stock, shipping promises, return promises, press, external authority, or social profiles.

## After

In the AgentShelf repository, `examples/codex_agent_loop_after.html` is the implemented after page.

```bash
agentshelf geo-run examples/codex_agent_loop_after.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir /tmp/agentshelf-after \
  --format json

agentshelf scan examples/codex_agent_loop_after.html --format markdown --min-score 90
```

Expected after behavior:

- `high_impact_issue_count` is `0`.
- Product-readiness scan is `strong`.
- Product/Offer schema blocker tasks are absent.
- `price_contradiction` is absent when visible and structured prices are equivalent.
- A review/social-proof top fix may remain if the merchant has no verified reviews. Do not invent reviews or ratings.

In a merchant repository, replace the example file paths with generated storefront snapshots, theme fixtures, or local product-page HTML.
