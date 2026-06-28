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
15. Run `geo-audit` when the goal is a broader Generative Engine Optimization plan for AI-readable commerce rather than only a product-page readiness score.
16. Convert GEO reports with `geo-tasks` when a coding agent needs a JSONL implementation queue with page areas, acceptance checks, and verification commands.
17. Validate agent-facing artifacts with `validate-contract` before implementation or CI handoff.
18. Use `geo-run` to produce a complete dogfood artifact bundle for coding agents: GEO report, validated task queue, local scan evidence, and summary.
19. Export the bundled `agentshelf-geo` skill with `export-skill` when another repository should carry the same coding-agent workflow.
20. Use `dogfood` for public real-page checks where derived artifacts are useful but third-party raw HTML should not be persisted.

## Components
- `src/agentshelf/engine.py`: parser, heuristic scoring engine, JSON-LD extraction, and renderers
- `src/agentshelf/geo.py`: GEO Skill domain models, page extraction, deterministic GEO rules, prompt panel generation, opportunity generation, patch suggestions, and report renderers
- `src/agentshelf/cli.py`: argument parsing, batch input resolution, snapshot fetches, threshold exits, and file I/O
- `skills/agentshelf-geo/`: repo-local Codex-style skill, JSONL task contract reference, and OpenAI agent metadata for audit-task-edit-verify workflows
- `src/agentshelf/skills/agentshelf-geo/`: package-bundled copy of the same skill assets used by `skill-info` and `export-skill`
- `src/agentshelf/templates/merchant-repo/`: package-bundled merchant repository initializer assets used by `init-merchant-repo`
- `schemas/`: published JSON Schema files for agent-facing GEO audit and task contracts
- `tests/test_engine.py`: regression coverage for parsing and rendering
- `tests/test_cli.py`: CLI behavior and threshold coverage
- `examples/sample_product_page.html`: smoke-test input
- `examples/weak_product_page.html`: failing-page fixture
- `examples/artist_store_product.html`: artist-store GEO before fixture for creator-commerce prompts and patches
- `examples/codex_agent_loop_after.html`: implemented after fixture showing the first Codex-style remediation loop
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
- `geo-audit` is implemented as a separate module so GEO reporting can evolve without destabilizing the existing score-gated scanner. It uses deterministic rules and templates only; live platform visibility monitoring, GSC/Bing integrations, and LLM-generated analysis remain future extension points.
- `geo-tasks` turns `geo-audit` JSON into stable task rows for coding agents. This keeps the agent interface implementation-oriented instead of forcing agents to parse prose reports.
- `geo-run` is a thin orchestration layer over `geo-audit`, `geo-tasks`, `validate-contract`, and local `scan`; it should not contain separate scoring logic.
- `dogfood` is the URL-safe orchestration layer for real-page calibration. It fetches HTML in memory, writes derived GEO and scan artifacts, and records `raw_html_persisted: false` in the summary.
- `validate-contract` provides dependency-free contract checks for `agentshelf.geo_audit.v0`, `agentshelf.geo_task.v0`, and the `agentshelf.geo_tasks.v0` wrapper so agent workflows can fail fast when artifacts drift.
- The bundled `agentshelf-geo` skill documents the intended loop: audit, emit tasks, edit storefront code/content/schema, then verify with `geo-run`, `geo-audit`, `geo-tasks`, and `scan`.
- `skill-info` and `export-skill` keep skill distribution inside the package boundary, so users do not need to clone this repository or manually copy paths to install the AgentShelf workflow into a merchant repo.
- `docs/AGENT_IMPLEMENTATION_LOOP.md` locks the concrete before/after path for coding agents, so the project demonstrates an implementation loop rather than only audit output.
- `init-merchant-repo` packages the practical adoption path: workflow, config, demo snapshot, onboarding docs, and exported skill with conflict-safe writes.

## Extension Path
- Add stricter JSON Schema validation if AgentShelf later accepts an optional `jsonschema` dependency or a build-time validation extra.
- Add deeper schema validation for variants, offers, return policy, merchant policy metadata, subscription selling plans, and bundle components.
- Add more storefront profile packs for preorders, backorders, subscriptions with prepaid plans, B2B pricing, and marketplace sellers.
- Add empirical benchmark runs against real agent answer quality before claiming ranking or conversion lift.
- Optional future work: add ecosystem-specific how-to guides for Shopify theme CI, WooCommerce export jobs, and headless catalog routes.
