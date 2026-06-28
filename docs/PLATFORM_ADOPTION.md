# Platform Adoption

AgentShelf works best when the storefront repository can produce merchant-owned HTML snapshots before a PR is merged. This guide documents the two highest-value paths for coding-agent workflows: Shopify/Liquid and headless storefronts such as Next.js.

## Shopify Or Liquid Theme Repos

Use this path when product data can be exported from Shopify or a theme build step can produce product-page HTML.

```bash
agentshelf init-merchant-repo \
  --brand "North Ridge Supply" \
  --category "outdoor bottles" \
  --vertical commerce

agentshelf render-fixtures examples/shopify-products.json \
  --input-format shopify \
  --platform shopify \
  --output-dir snapshots/shopify \
  --manifest snapshots/shopify/manifest.json \
  --format json

agentshelf adoption-check . \
  --snapshot snapshots/shopify/trailbottle-pro-24oz.shopify.html \
  --brand "North Ridge Supply" \
  --category "outdoor bottles" \
  --vertical commerce
```

Recommended production wiring:

- Generate snapshots from a real Shopify product export or theme fixture job.
- Keep `.agentshelf.json` in the repo and start with `min_score: 70`.
- Upload `artifacts/agentshelf/` from the GitHub workflow before failing the gate.
- Ask Codex to use `$agentshelf-geo`, edit Liquid sections/snippets or schema builders, then rerun `adoption-check`.

Do not fabricate ratings, reviews, inventory, shipping promises, return promises, or external authority links to make the gate pass.

## Headless Or Next.js Storefronts

Use this path when product data flows through a catalog API, GraphQL export, static generation job, or app-state payload such as `__NEXT_DATA__`.

```bash
agentshelf init-merchant-repo \
  --brand "North Ridge Supply" \
  --category "outdoor bottles" \
  --vertical commerce

agentshelf render-fixtures examples/headless-catalog.json \
  --input-format headless \
  --platform headless \
  --output-dir snapshots/headless \
  --manifest snapshots/headless/manifest.json \
  --format json

agentshelf adoption-check . \
  --snapshot snapshots/headless/trailbottle-pro-24oz.headless.html \
  --brand "North Ridge Supply" \
  --category "outdoor bottles" \
  --vertical commerce
```

Recommended production wiring:

- Run the snapshot generation step after catalog normalization and before deploy previews.
- Prefer generated product-page snapshots over live crawling in PR gates.
- If the live page injects key data late with JavaScript, add a scheduled rendered snapshot job separately and keep those raw artifacts out of commits when they include third-party HTML.
- Keep schema and page-copy fixes in typed components, metadata helpers, JSON-LD builders, or product data mappers.

## What Good Looks Like

A mature merchant repo has:

- `.github/workflows/agentshelf-geo.yml` committed.
- `.agentshelf.json` committed.
- `.codex/skills/agentshelf-geo/` committed when Codex should perform remediation.
- A reproducible snapshot generation step.
- `agentshelf adoption-check` passing on at least one merchant-owned product snapshot.
- Uploaded scan, GEO report, and task artifacts for failed PRs.

This still does not claim external ranking lift in ChatGPT, Google, Perplexity, Claude, Gemini, or Bing. It proves that merchant-owned product facts are exposed in a deterministic format and that coding agents have a concrete task queue for remediation.
