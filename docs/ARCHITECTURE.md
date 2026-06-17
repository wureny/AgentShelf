# Architecture

## Overview
AgentShelf is a lightweight Python CLI with a composable audit workflow:

1. Discover product-like URLs from robots.txt sitemap hints or an explicit sitemap URL.
2. Read an HTML/text product-page snapshot from disk, fetch raw HTML with `snapshot`, capture rendered HTML with the optional `agentshelf[render]` extra, or generate stable storefront-shaped snapshots from normalized product JSON, Shopify JSON, WooCommerce CSV, or headless catalog JSON with `render-fixtures`.
3. Run weighted deterministic checks for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema signals.
4. Parse Product JSON-LD when present to extract stronger evidence for offers and availability.
5. Select or auto-detect a storefront adapter profile (`generic`, `shopify`, `woocommerce`, or `headless`).
6. Extract commerce signals from embedded product JSON, variant arrays, WooCommerce variation forms, selling plan groups, metafield-like keys, policy snippets, subscription terms, bundle contents, regional shipping promises, and return policy schema.
7. Compute dimension scores for discoverability, offer clarity, policy clarity, and agent actionability. Profile-specific checks can be marked not applicable so single-SKU pages are not penalized for missing subscription or bundle terms.
8. Render human reports, JSON/JSONL, SARIF, or an agent-native JSON contract with prioritized tasks.
9. Compare raw and rendered snapshots to decide whether browser capture is worth the operational cost for a page class.
10. Compare scheduled scan result files to surface product-page regressions, improvements, and catalog coverage changes.
11. Run scheduled audits with local previous/current history, timestamped archives, diff reports, and optional agent task output.
12. Calibrate rules against real merchant snapshots by grouping likely false-positive categories and exporting anonymized fixture candidates.
13. Render calibration dashboards for larger merchant page sets, draft labels from review findings, then evaluate rule changes against confirmed human labels before tightening CI gates.
14. Publish CI review artifacts together: SARIF annotations, JSONL scan output, calibration dashboards, draft labels, evaluation notes, and agent task queues.

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
- `calibrate` turns real-page scan artifacts into review categories and anonymized fixture candidates, so production false positives can become benchmark coverage instead of ad hoc rule changes.
- `dashboard` turns calibration reports into standalone HTML or Markdown review queues for merchant operators, consultants, and CI artifacts.
- `draft-labels` converts calibration reports into editable label contracts, keeping human review lightweight while preserving a deterministic CI artifact.
- `evaluate` compares scan artifacts with human calibration labels for checks, blockers, tasks, categories, and warnings, making rule changes safer to run in CI.
- `.github/workflows/agentshelf-artifacts.yml` demonstrates the production PR-review loop: generate machine artifacts first, upload them for humans and coding agents, then enforce the score gate.
- The artifact workflow can either scan existing snapshots or render fixtures from a catalog export first, then upload import remediation tasks and page remediation tasks together before enforcing gates.
- SARIF output maps failed checks into code-scanning-style findings for CI and GitHub annotations.
- `.agentshelf.json` keeps production scan gates repeatable across local, CI, and scheduled runs.
- Raw snapshot mode does not execute JavaScript; dynamic pages are flagged instead of silently trusted. `--rendered` handles single-page JS capture when the optional browser dependency is installed.
- `snapshot --url-file` supports real merchant URL lists without introducing site-wide crawling behavior.
- `render-fixtures` gives merchants and coding agents a deterministic pre-merge path when product data is available before deployment, avoiding live crawling and browser installs for every PR. Native import adapters normalize Shopify JSON, WooCommerce CSV, and generic headless catalog JSON into one fixture contract before rendering platform-shaped HTML.
- Import validation lives before rendering, so missing native-export fields become manifest warnings and optional CI failures instead of being hidden by generated fallback copy.
- Import remediation tasks convert those validation warnings into JSONL work items with source export fields, acceptance checks, and priorities for coding agents.
- `discover` consumes sitemap metadata rather than crawling arbitrary links, keeping audits predictable and polite.

## Extension Path
- Add deeper schema validation for variants, offers, return policy, merchant policy metadata, subscription selling plans, and bundle components.
- Add more storefront profile packs for preorders, backorders, subscriptions with prepaid plans, B2B pricing, and marketplace sellers.
- Add empirical benchmark runs against real agent answer quality before claiming ranking or conversion lift.
- Optional future work: add ecosystem-specific how-to guides for Shopify theme CI, WooCommerce export jobs, and headless catalog routes.
