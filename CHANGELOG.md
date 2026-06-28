# Changelog

## 0.36.0
- Added `agentshelf public-audit` to validate public open-source release hygiene before tags, release drafts, or Marketplace-facing copy.
- Added `docs/PUBLIC_RELEASE_AUDIT.md` with maintainer checks for public adoption paths, conservative non-claims, private path leaks, tracked generated-file hygiene, release notes, and Marketplace readiness.
- Cleaned `STATUS.md` into a public-facing release posture summary instead of an internal automation log.
- Extended `release-check` so public-audit failures block release readiness.

## 0.35.0
- Added regression coverage proving `init-merchant-repo`, `render-fixtures`, and `adoption-check` work together on a headless/Next.js-style catalog export.
- Expanded platform adoption guidance for app-state payloads, typed metadata helpers, JSON-LD builders, and Codex remediation in headless storefront repositories.
- Updated release readiness docs and examples for the `v0.35.0` release target.

## 0.34.0
- Added platform adoption guidance for Shopify/Liquid and headless/Next.js storefronts that use generated snapshots instead of live crawling.
- Added regression coverage proving `init-merchant-repo`, `render-fixtures`, and `adoption-check` work together on a Shopify export inside a merchant-style repository.
- Extended release readiness checks to keep the platform adoption guide present before public tags are created.

## 0.33.0
- Added `agentshelf adoption-check` to validate initialized merchant repositories after `init-merchant-repo`.
- The adoption check verifies config, GitHub workflow, exported Codex skill, onboarding docs, snapshot scan score, and GEO task generation in one local command.
- Added merchant adoption documentation so operators and Codex-style agents can confirm the AgentShelf workflow is actually installed before enforcing CI gates.

## 0.32.0
- Added `agentshelf release-notes` to generate conservative Markdown or JSON release drafts from the matching `CHANGELOG.md` section before creating public GitHub tags.
- Extended `release-check` to require release-note generation coverage so maintainers review production posture, install guidance, and non-claims before publishing.
- Updated release documentation and pinned workflow examples for the `v0.32.0` release target.

## 0.31.0
- Added `agentshelf release-check` for source-tree release readiness validation before creating a public GitHub release tag.
- Updated copyable Action examples to use the current `v0.31.0` release tag target instead of the old placeholder tag.
- Added release checks for version consistency, changelog coverage, README production posture, Action metadata, pinned workflow examples, skill assets, and merchant onboarding templates.

## 0.30.0
- Added `agentshelf init-merchant-repo` to initialize storefront repositories with an AgentShelf GEO workflow, local scan config, demo snapshot, onboarding docs, and exported Codex skill.
- Added a packaged merchant-repository template for GitHub Actions adoption without manually copying README snippets.
- Added conflict-safe initialization behavior so existing merchant repo files are not overwritten unless `--force` is used.

## 0.29.0
- Added a Codex-style before/after implementation-loop fixture showing how an agent can turn `geo-run` tasks into a stronger, schema-backed product page.
- Documented the audit-task-edit-verify loop for coding agents in `docs/AGENT_IMPLEMENTATION_LOOP.md`.
- Normalized equivalent visible and structured prices such as `USD 128` and `128.00` so agent reports do not emit false price contradictions.
- Tightened review detection so return-policy review copy or future testimonial placeholders do not count as verified product reviews.

## 0.28.0
- Tightened return-policy schema applicability so generic footer links such as "Returns and exchanges" do not trigger `add_return_policy_schema`.
- Preserved return-policy schema tasks for explicit promises such as `30-day returns`, unused-condition requirements, refund methods, labels, or store credit.
- Added a synthetic benchmark fixture for return-policy-link-only pages to prevent noisy merchant-page remediation tasks.

## 0.27.0
- Tightened subscription-intent detection so newsletter or restock-alert copy does not trigger subscription purchase-term failures.
- Added a synthetic benchmark fixture derived from real-page dogfooding for single-SKU product pages with newsletter subscribe copy.
- Locked the expected benchmark output so `complete_subscription_terms` does not reappear unless a page has actual selling-plan or purchase-subscription intent.

## 0.26.0
- Added `agentshelf dogfood` for safe real-URL dogfooding without persisting third-party raw HTML by default.
- `dogfood` writes GEO reports, GEO tasks, contract validation, product-readiness scan reports, dogfood notes, and a machine-readable summary.
- Documented the real-page calibration workflow and no-raw-third-party-HTML policy for open-source dogfooding.

## 0.25.0
- Bundled the `agentshelf-geo` skill inside the Python package so installed AgentShelf distributions can export the same coding-agent workflow.
- Added `agentshelf skill-info` to inspect the packaged skill and primary GEO workflow.
- Added `agentshelf export-skill` to install `.codex/skills/agentshelf-geo` into another storefront or merchant repository.
- Added regression tests to keep the repo-local skill and package-bundled skill synchronized.

## 0.24.0
- Added `agentshelf geo-run` as a one-command GEO dogfood workflow for coding agents and CI artifacts.
- `geo-run` writes GEO reports, validated JSON contracts, task queues, optional local scan reports, and a machine-readable summary into one output directory.
- Updated docs and skill guidance to prefer `geo-run` when users want the full audit-task-verify artifact bundle.

## 0.23.0
- Added `agentshelf validate-contract` for validating AgentShelf GEO JSON and JSONL artifacts before coding agents act on them.
- Published JSON Schema files for `agentshelf.geo_audit.v0` and `agentshelf.geo_task.v0` under `schemas/`.
- Updated the GEO skill workflow so Codex-style agents can audit, validate contracts, emit tasks, edit, and verify without relying on prose-only reports.

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
