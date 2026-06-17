# Architecture

## Overview
AgentShelf is a lightweight Python CLI with a composable audit workflow:

1. Discover product-like URLs from robots.txt sitemap hints or an explicit sitemap URL.
2. Read an HTML/text product-page snapshot from disk, fetch raw HTML with `snapshot`, or capture rendered HTML with the optional `agentshelf[render]` extra.
3. Run weighted deterministic checks for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema signals.
4. Parse Product JSON-LD when present to extract stronger evidence for offers and availability.
5. Select or auto-detect a storefront adapter profile (`generic`, `shopify`, `woocommerce`, or `headless`).
6. Extract commerce signals from embedded product JSON, variant arrays, WooCommerce variation forms, selling plan groups, metafield-like keys, policy snippets, subscription terms, bundle contents, regional shipping promises, and return policy schema.
7. Compute dimension scores for discoverability, offer clarity, policy clarity, and agent actionability. Profile-specific checks can be marked not applicable so single-SKU pages are not penalized for missing subscription or bundle terms.
8. Render human reports, JSON/JSONL, SARIF, or an agent-native JSON contract with prioritized tasks.
9. Compare raw and rendered snapshots to decide whether browser capture is worth the operational cost for a page class.
10. Compare scheduled scan result files to surface product-page regressions, improvements, and catalog coverage changes.
11. Run scheduled audits with local previous/current history, timestamped archives, diff reports, and optional agent task output.

## Components
- `src/agentshelf/engine.py`: parser, heuristic scoring engine, JSON-LD extraction, and renderers
- `src/agentshelf/cli.py`: argument parsing, batch input resolution, snapshot fetches, threshold exits, and file I/O
- `tests/test_engine.py`: regression coverage for parsing and rendering
- `tests/test_cli.py`: CLI behavior and threshold coverage
- `examples/sample_product_page.html`: smoke-test input
- `examples/weak_product_page.html`: failing-page fixture
- `benchmarks/fixtures/`: curated agent-readiness benchmark inputs
- `benchmarks/expected/`: expected benchmark bands, blockers, and agent tasks
- `docs/PROFILE_BENCHMARKS.md`: profile-specific benchmark contract for Shopify, WooCommerce, and headless fixtures

## Design Choices
- Standard-library raw snapshot mode keeps the base demo runnable without browser installs.
- Rendered snapshot mode is optional and dynamically imports Playwright only when `--rendered` is requested.
- Local-file input first, so the product can run without network access or storefront credentials.
- Weighted pass/fail checks keep the first version explainable and easy to extend.
- Adapter profiles keep extraction deterministic while still supporting real storefront variation: `auto` detects a likely profile, and explicit profiles let CI pin Shopify, WooCommerce, headless, or generic behavior.
- Embedded commerce extraction treats storefront JSON as first-class evidence, so variant price, availability, selling plans, WooCommerce variation data, metafield-like specs, and nested return policy schema can help checks pass even when visible copy is sparse.
- Profile-specific rule packs fire only when relevant merchant intent is detected: subscriptions need cadence, price or discount, and cancellation terms; bundles need component lists plus bundle-level offer data; regional shipping needs destination plus timing or cost; visible returns should be backed by return policy schema.
- GitHub Action wraps the CLI instead of duplicating scanning logic.
- `agent-audit` uses stable task-oriented JSON so coding agents can act on results directly.
- `agent-tasks` emits JSONL so coding agents can remediate batches without parsing human reports.
- `compare` reports score deltas, dimension deltas, unlocked signals, regressions, and an agent recommendation for raw vs rendered snapshots.
- `diff` compares stored scan artifacts instead of rescanning pages, so scheduled jobs can produce regression reports from CI artifacts.
- `audit-run` wraps scan and diff for local scheduled jobs, rotating previous/current JSONL safely before writing current results.
- SARIF output maps failed checks into code-scanning-style findings for CI and GitHub annotations.
- `.agentshelf.json` keeps production scan gates repeatable across local, CI, and scheduled runs.
- Raw snapshot mode does not execute JavaScript; dynamic pages are flagged instead of silently trusted. `--rendered` handles single-page JS capture when the optional browser dependency is installed.
- `snapshot --url-file` supports real merchant URL lists without introducing site-wide crawling behavior.
- `discover` consumes sitemap metadata rather than crawling arbitrary links, keeping audits predictable and polite.

## Extension Path
- Add deeper schema validation for variants, offers, return policy, merchant policy metadata, subscription selling plans, and bundle components.
- Add more storefront profile packs for preorders, backorders, subscriptions with prepaid plans, B2B pricing, and marketplace sellers.
- Add empirical benchmark runs against real agent answer quality before claiming ranking or conversion lift.
