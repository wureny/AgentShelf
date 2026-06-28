# Changelog

## 0.22.0
- Added `agentshelf geo-audit` as a deterministic GEO Skill v0 for AI-readable commerce.
- Added `agentshelf geo-tasks` to turn GEO JSON reports into a stable JSONL implementation queue for coding agents.
- Added the repo-local `skills/agentshelf-geo` Codex-style skill with task contract documentation and OpenAI agent metadata.
- Added GEO domain models, page extraction, crawlability/indexability checks, structured-data checks, content extractability checks, entity consistency checks, commerce attribute checks, trust checks, prompt panel generation, opportunity generation, and page patch suggestions.
- Added an artist-store example fixture and tests for JSON/Markdown GEO reports, crawler blocker detection, prompt panel coverage, and `--format both` output.

## 0.21.0
- Added `render-fixtures --tasks-output` to turn import validation warnings into machine-readable JSONL remediation tasks for coding agents.
- Added platform-aware task guidance for Shopify JSON, WooCommerce CSV, headless catalog JSON, and normalized AgentShelf product exports.
- Added tests for warning-to-task conversion and empty task files for clean imports.

## 0.20.0
- Added import validation to `render-fixtures` manifests so missing native-export fields are visible before generated snapshots are trusted.
- Added `render-fixtures --fail-on-warnings` for CI pipelines that should fail when exports omit price, currency, stock, variants, shipping, returns, specs, or variant option context.
- Added tests for validation manifests, warning output, and warning-gated fixture generation.

## 0.19.0
- Added native `render-fixtures --input-format` import adapters for Shopify product JSON, WooCommerce product CSV, and generic headless catalog JSON.
- Added native export examples for Shopify, WooCommerce, and headless GraphQL-style catalogs.
- Added tests proving native merchant exports can render platform snapshots and pass scan gates without manually reshaping into AgentShelf's normalized product JSON.

## 0.18.0
- Added `agentshelf render-fixtures` to generate deterministic Shopify, WooCommerce, and headless HTML snapshots from a simple product JSON export.
- Added `examples/storefront-products.json` as a merchant-readable catalog export example for local and CI fixture generation.
- Added CLI tests that render all platform snapshots, scan them with matching adapter profiles, and enforce a production-ready score threshold.

## 0.17.0
- Added a GitHub Actions artifact workflow that produces SARIF, JSONL scan results, agent task queues, calibration reports, dashboards, draft labels, and evaluation notes in one run.
- Preserved score-gate failures until after review artifacts upload, so CI users can inspect merchant-facing fixes before a job fails.
- Added workflow regression tests to keep the artifact pipeline aligned with the public CLI commands.

## 0.16.0
- Added `agentshelf dashboard` to render calibration JSON reports as operator-friendly HTML or Markdown dashboards.
- Added dashboard coverage for review queue priority, score, band, confidence, adapter profile, categories, blockers, and agent tasks.
- Documented dashboard usage for merchant calibration review artifacts.

## 0.15.0
- Added `agentshelf draft-labels` to convert calibration JSON reports into editable draft calibration label files.
- Added support for `needs_review` draft labels; `evaluate` skips draft labels until humans mark them true-positive or false-positive.
- Added `examples/draft-calibration-labels.json` to document the label authoring workflow.

## 0.14.0
- Added `agentshelf evaluate` for CI-friendly evaluation of scan results against human calibration labels.
- Added calibration label support for checks, blocking issues, agent tasks, calibration categories, and warnings.
- Added an example `examples/calibration-labels.json` contract for true-positive and false-positive expectations.

## 0.13.0
- Added `agentshelf calibrate` for real-page calibration reviews from HTML snapshots or existing scan JSON/JSONL artifacts.
- Added calibration categories for rendered capture, contradictions, profile rules, policy schema, offer extraction, content gaps, and low-confidence snapshots.
- Added anonymized fixture candidate export so teams can turn merchant-page false positives into reproducible benchmark cases.

## 0.12.0
- Added applicable profile-specific rule checks for return policy schema, subscription terms, bundle component clarity, and regional shipping promises.
- Added agent task IDs for deeper merchant remediation: `add_return_policy_schema`, `complete_subscription_terms`, `clarify_bundle_components`, and `add_regional_shipping_matrix`.
- Added a benchmark fixture that locks production-style gaps for subscription bundles and regional shipping promises.
- Improved JSON-LD schema value extraction so nested Offer return policy metadata is detected.

## 0.11.0
- Added profile-specific benchmark fixtures for Shopify, WooCommerce, and headless storefront exports.
- Extended benchmark expectations to lock adapter profile detection and core commerce signal counts.
- Added profile benchmark documentation for production CI and agent workflows.

## 0.10.0
- Added storefront adapter profiles: `auto`, `generic`, `shopify`, `woocommerce`, and `headless`.
- Added profile detection metadata to `commerce_signals` so agents can see requested, detected, and active extraction profiles.
- Added `--profile` support across scan, agent-audit, agent-tasks, compare, audit-run, config files, and the GitHub Action.

## 0.9.0
- Added embedded commerce signal extraction for Shopify/theme-style product JSON, variant arrays, selling plan groups, metafield-like keys, and policy snippets.
- Upgraded price, availability, variant readiness, offer completeness, agent answerability, specs, and merchant-feed checks to use extracted commerce evidence.
- Added `commerce_signals` to scan JSON and a Commerce Signals section to Markdown reports.

## 0.8.0
- Added `agentshelf audit-run` to scan page sets and maintain local scheduled-audit history.
- Added safe previous/current result rotation, timestamped JSONL archives, generated diff reports, and optional agent-task output.
- Preserved threshold exit behavior while still writing audit artifacts for CI review.

## 0.7.0
- Added `agentshelf diff` to compare two JSON/JSONL scan result files across scheduled audit runs.
- Added regression, improvement, new-page, removed-page, blocker, warning, and next-action reporting for merchant page sets.
- Added Markdown and JSON diff output for human review artifacts and agent-native automation.

## 0.6.0
- Added `agentshelf discover` to collect product-like URLs from robots.txt sitemap hints or explicit sitemap URLs.
- Added include/exclude regex filters, limits, text/JSON/JSONL output, and URL-list handoff to `snapshot --url-file`.

## 0.5.0
- Added `agentshelf compare raw.html rendered.html` to quantify signals unlocked by rendered capture.
- Added JSON and Markdown compare output with score deltas, dimension deltas, unlocked signals, regressions, and agent recommendations.

## 0.4.0
- Added `.agentshelf.json` configuration support for repeatable CI gates.
- Added SARIF output for GitHub code scanning and production-quality CI annotations.
- Added `agentshelf agent-tasks` to emit remediation tasks as JSONL for coding agents.
- Added `snapshot --url-file --output-dir --manifest` for batch URL capture pipelines.
- Extended the GitHub Action inputs for config, SARIF, and fail-band gates.

## 0.3.0
- Added optional Playwright-backed rendered snapshots with `agentshelf snapshot <url> --rendered`.
- Added `agentshelf[render]` extra for users who need JS-rendered storefront capture.
- Documented rendered snapshot setup and clarified that site-wide crawling remains out of scope.

## 0.2.0
- Added `agentshelf agent-audit` with a stable JSON contract for coding agents.
- Added `agentshelf snapshot` for raw HTML URL snapshots.
- Added dimension scoring for discoverability, offer clarity, policy clarity, and agent actionability.
- Added agent-specific checks for variants, offer completeness, answerability, merchant-feed hints, and visible/schema contradictions.
- Added benchmark fixtures and expected outputs for agent-specific failure modes.

## 0.1.0
- Initial open-source release.
- Added local product-page scanning for AI shopping-agent readiness.
- Added markdown, JSON, and JSONL output.
- Added batch scanning and CI-friendly score thresholds.
- Added GitHub Action wrapper.
