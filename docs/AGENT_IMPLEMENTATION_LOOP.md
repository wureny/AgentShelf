# Agent Implementation Loop

AgentShelf is designed to be useful to coding agents, not only human auditors. This loop shows how Codex-style agents should use the CLI and exported `agentshelf-geo` skill to turn an audit into concrete storefront edits and verification.

## 1. Run The Before Audit

```bash
agentshelf geo-run examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir /tmp/agentshelf-before \
  --format json
```

The before fixture intentionally lacks Product/Offer JSON-LD and machine-readable commerce facts. The generated bundle includes:

- `geo-report.json`: deterministic GEO report using `agentshelf.geo_audit.v0`.
- `geo-tasks.jsonl`: coding-agent work queue using `agentshelf.geo_task.v0`.
- `scan-report.md`: product-readiness evidence and top fixes.
- `summary.json`: machine-readable summary for CI or agent handoff.

Expected before state:

- `overallScore`: about `88`.
- `scan.score`: about `58`, `weak`.
- High-priority task examples: `product_schema_skeleton`, `missing_product_schema`, `missing_offer_schema`.

## 2. Implement The First Agent Tasks

A coding agent should read `geo-tasks.jsonl` and handle high-priority tasks first. For this example, the implemented fixture is:

```text
examples/codex_agent_loop_after.html
```

It demonstrates safe first-pass edits:

- Add visible opening answer copy near the H1.
- Add merchant-verified Product and Offer JSON-LD with price, currency, availability, seller, shipping, and return policy.
- Add Organization and FAQPage JSON-LD using facts already visible on the page.
- Add FAQ copy covering buyer fit, customization, shipping, care, cancellations, and returns.
- Add conservative product image alt text.
- Link supporting collection, gift-guide, custom-order, artist/about, contact, and external profile pages.

Do not fabricate reviews, ratings, press, social proof, availability, shipping promises, return promises, or external authority links. If a field is not merchant-confirmed, omit it or mark it as a draft outside production markup.

## 3. Verify The After State

```bash
agentshelf geo-run examples/codex_agent_loop_after.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir /tmp/agentshelf-after \
  --format json

agentshelf scan examples/codex_agent_loop_after.html --format markdown --min-score 90
```

Expected after state:

- `overallScore`: about `96`.
- `scan.score`: about `95`, `strong`.
- `high_impact_issue_count`: `0`.
- No `price_contradiction` when visible price `USD 128` matches structured price `128.00`.
- Product/Offer schema blocker tasks are resolved.
- A real review/social-proof gap may remain unless the merchant has verified reviews or ratings. Do not fabricate them to reach `100`.

## 4. What This Proves

This loop is intentionally local and deterministic. It does not prove live ranking lift in ChatGPT, Google, Perplexity, Claude, or other external agents. It proves a narrower but useful production workflow:

- AgentShelf can generate validated JSON/JSONL contracts.
- Codex can treat those contracts as an implementation queue.
- The storefront or fixture can be edited without guessing from prose.
- The result can be verified with the same CLI before a PR is merged.

Use this pattern in merchant repositories by exporting the skill:

```bash
agentshelf export-skill --output-dir .codex/skills
```

Then ask the coding agent to run `$agentshelf-geo` against generated product-page snapshots or storefront fixtures.
