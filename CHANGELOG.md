# Changelog

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
