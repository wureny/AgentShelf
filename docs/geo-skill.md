# AgentShelf GEO Skill

AgentShelf GEO Skill is a deterministic audit and remediation workflow for AI-readable commerce. It helps product pages, collection pages, policy pages, creator-commerce stores, and artist stores expose facts that coding agents, shopping agents, search agents, and GTM workflows can read safely.

It is different from a traditional SEO audit because the output is not only a score. AgentShelf produces implementation-ready `geo-tasks` that Codex-style coding agents can apply to storefront templates, schema builders, product data mappers, content fixtures, or merchant-owned HTML snapshots.

## What v0 Supports

- Page-level `geo-audit` for local HTML files or explicit URLs.
- Store-level audit for a local snapshot bundle with `agentshelf geo-run --store-snapshot`.
- Deterministic prompt panels for commerce intent coverage.
- JSON and Markdown reports with limitations and merchant-safe recommendations.
- JSONL `geo-tasks` with acceptance checks and verification commands.
- Contract validation with `agentshelf validate-contract`.
- Exportable `$agentshelf-geo` skill for Codex-style remediation loops.

## What v0 Does Not Support

- No live AI visibility measurement.
- No ChatGPT, Google AI, Perplexity, Claude, Gemini, Bing, GSC, or Bing Webmaster integration.
- No claimed ranking lift, citation lift, impression lift, referral lift, traffic lift, or conversion lift.
- No fake AI citation, AI ranking, AI mention, or AI referral data.
- No browser automation, Shopify app, checkout automation, SaaS dashboard, or external provider scraping.

These are explicit product boundaries. Current value comes from making commerce pages more AI-readable and easier for agents or developers to improve, not from measuring external-provider outcomes.

## Page-Level Audit

```bash
agentshelf geo-audit examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --format both \
  --output reports/moon-kiln-geo-report
```

Use page-level audit when you are improving a product page, collection page, or specific template.

## Store-Level Audit

```bash
agentshelf geo-run \
  --store-snapshot examples/fixtures/artist-store-before \
  --store-profile examples/profiles/artist-store.example.json \
  --vertical artist_store \
  --output-dir reports/artist-store
```

Use store-level audit when the question is whether the storefront as a whole answers buyer, policy, entity, trust, comparison, gift, and customization prompts.

## Generate Geo Tasks

```bash
agentshelf geo-tasks reports/artist-store/report.json \
  --output reports/artist-store/geo-tasks.jsonl
```

Each task includes a concrete page or area, reason, implementation guidance, acceptance check, verification command, expected report delta, and risk notes. Tasks must not ask Codex or developers to fabricate reviews, ratings, stock, shipping promises, return promises, press, or external authority.

## Validate Contracts

```bash
agentshelf validate-contract reports/artist-store/report.json \
  --contract agentshelf.store_geo_audit.v0

agentshelf validate-contract reports/artist-store/geo-tasks.jsonl \
  --contract agentshelf.geo_task.v0
```

Contract validation is intended to happen before a coding agent edits a storefront and again after it writes new artifacts.

## Interpreting Scores

Scores are deterministic local readiness signals. They summarize whether local snapshots expose crawlable, structured, internally linked, policy-aware, product-specific facts. They do not prove external AI visibility, ranking, citation, traffic, or revenue outcomes.
