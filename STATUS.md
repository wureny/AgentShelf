# Status

- Date: 2026-06-17
- Phase: maintain_or_extend
- Project path: `/Users/wurenyu/Documents/Codex/2026-06-06/intent-to-prompt-users-wurenyu-codex/projects/agentic-commerce-readiness-scanner`
- Canonical requested root: `/Users/wurenyu/workspace`
- Current blocker: none

## Current Milestone
Make stable pre-merge storefront snapshot generation available for real merchant CI workflows.

## Completed This Run
- Rebranded the public project to `AgentShelf`.
- Packaged it as an installable Python project with CLI command `agentshelf`.
- Added batch scanning, JSONL output, score thresholds, fail bands, top fixes, evidence, and JSON-LD Product parsing.
- Added GitHub Action metadata, CI workflow, MIT license, contribution docs, security notes, changelog, and git ignore rules.
- Added `agent-audit` with a stable JSON contract for coding agents.
- Added raw HTML `snapshot` command for URL capture without browser dependencies.
- Added dimension scoring, agent-specific checks, contradiction detection, confidence levels, and benchmark fixtures.
- Added optional Playwright-backed rendered snapshots behind `agentshelf[render]`.
- Updated docs and package metadata for `agentshelf snapshot <url> --rendered`.
- Added `.agentshelf.json` config support for repeatable local and CI gates.
- Added SARIF output for GitHub code scanning and production-quality CI annotations.
- Added `agent-tasks` JSONL output so coding agents can remediate batches.
- Added `snapshot --url-file --output-dir --manifest` for merchant URL list capture workflows.
- Extended the GitHub Action inputs for config files, SARIF output, and fail-band gates.
- Added `compare` for raw-vs-rendered snapshot analysis with score deltas, unlocked signals, regressions, and agent recommendations.
- Added `discover` for robots.txt sitemap hints and explicit sitemap ingestion with include/exclude filters and limits.
- Added `diff` for comparing JSON/JSONL scan artifacts across scheduled audit runs, including regressions, improvements, blocker changes, catalog changes, and agent next actions.
- Added `audit-run` for local scheduled audits with safe previous/current result rotation, timestamped archives, generated diff reports, and optional agent task output.
- Added embedded commerce signal extraction for Shopify/theme-style product JSON, variants, selling plan groups, metafield-like keys, and policy snippets.
- Upgraded price, inventory, variant readiness, offer completeness, specs, policy, agent answerability, and merchant-feed checks to use storefront commerce evidence.
- Added storefront adapter profiles (`auto`, `generic`, `shopify`, `woocommerce`, `headless`) with CLI, config, GitHub Action, JSON, and Markdown support.
- Added profile-specific benchmark fixtures and expected outputs for Shopify, WooCommerce, and headless storefront exports.
- Added `docs/PROFILE_BENCHMARKS.md` to document the adapter benchmark contract.
- Added applicable profile-specific rule packs for return policy schema, subscription terms, bundle component clarity, and regional shipping promises.
- Added profile-rule agent tasks: `add_return_policy_schema`, `complete_subscription_terms`, `clarify_bundle_components`, and `add_regional_shipping_matrix`.
- Added a production-style benchmark fixture for subscription bundle gaps and updated benchmark expectations for stricter agent-readiness scoring.
- Improved JSON-LD schema extraction so nested Offer return policy metadata is detected.
- Added `agentshelf calibrate` to summarize real-page calibration hotspots from HTML snapshots or scan JSON/JSONL artifacts.
- Added calibration categories for rendered capture, contradictions, profile rules, policy schema, offer extraction, content gaps, and low-confidence snapshots.
- Added anonymized fixture export for local HTML candidates plus metadata sidecars.
- Added `agentshelf evaluate` to compare scan results against human calibration labels for checks, blocking issues, agent tasks, categories, and warnings.
- Added `examples/calibration-labels.json` as a true-positive and false-positive label contract example.
- Added `agentshelf draft-labels` to convert calibration JSON reports into editable draft label contracts.
- Added support for `needs_review` draft labels; `evaluate` skips them until they are confirmed.
- Added `examples/draft-calibration-labels.json`.
- Added `agentshelf dashboard` to render calibration JSON as standalone HTML or Markdown review dashboards.
- Dashboard output summarizes page priority, score, band, confidence, adapter profile, review categories, blockers, tasks, and next actions.
- Added `.github/workflows/agentshelf-artifacts.yml` to produce SARIF, JSONL scan results, agent task queues, calibration reports, dashboards, draft labels, and evaluation notes in one CI run.
- Added workflow regression tests so the GitHub Actions artifact example keeps covering code scanning, review artifacts, and delayed score-gate enforcement.
- Added `agentshelf render-fixtures` to turn product JSON exports into deterministic Shopify, WooCommerce, and headless HTML snapshots.
- Added `examples/storefront-products.json` as a realistic catalog export shape for merchants and coding agents.
- Added tests proving generated platform snapshots are scannable with matching adapter profiles and pass an `85` score gate.

## Verification
- `PYTHONPATH=src python3 -m unittest discover -s tests`
- `python3 -m unittest discover -s tests`
- `python3 -m pip install -e .`
- `agentshelf scan examples/sample_product_page.html --format markdown --output outputs/sample_report.md`
- `agentshelf scan examples/weak_product_page.html --min-score 70`
- `agentshelf scan examples --batch --format jsonl`
- `agentshelf agent-audit examples/weak_product_page.html --contract v1`
- `agentshelf scan benchmarks/fixtures --batch --format jsonl`
- `python3 -m unittest tests.test_cli.CliTests.test_rendered_snapshot_uses_playwright_when_available`
- `agentshelf scan examples/weak_product_page.html --format sarif`
- `agentshelf agent-tasks examples --batch`
- `agentshelf scan examples/weak_product_page.html --config examples/agentshelf.config.json`
- `python3 -m unittest tests.test_cli.CliTests.test_snapshot_url_file_writes_manifest tests.test_cli.CliTests.test_snapshot_writes_html_from_local_server`
- `agentshelf compare examples/js_product_raw.html examples/js_product_rendered.html --format json`
- `agentshelf discover --sitemap <local test server>/sitemap.xml`
- `agentshelf diff previous-results.jsonl current-results.jsonl --output audit-diff.md`
- `agentshelf audit-run "snapshots/*.html" --batch --history-dir .agentshelf/runs --tasks-output agentshelf-tasks.jsonl`
- `agentshelf scan examples/sample_product_page.html --format markdown`
- `agentshelf scan examples/shopify_variant_product.html --profile shopify --format json`
- `python3 -m unittest tests.test_engine.BenchmarkTests`
- `.venv/bin/python -m unittest tests.test_engine`
- `.venv/bin/python -m unittest tests.test_cli.CliTests.test_calibrate_from_html_batch_exports_anonymized_fixtures tests.test_cli.CliTests.test_calibrate_from_scan_results_jsonl`
- `.venv/bin/python -m unittest tests.test_cli.CliTests.test_evaluate_calibration_labels_passes_expected_findings tests.test_cli.CliTests.test_evaluate_calibration_labels_fails_false_positive_regression`
- `.venv/bin/python -m unittest tests.test_cli.CliTests.test_draft_labels_from_calibration_report tests.test_cli.CliTests.test_evaluate_skips_draft_labels`
- `.venv/bin/python -m unittest tests.test_cli.CliTests.test_dashboard_renders_html_from_calibration_report tests.test_cli.CliTests.test_dashboard_renders_markdown_from_calibration_report`
- `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/agentshelf-artifacts.yml"); puts "workflow-yaml-ok"'`
- `.venv/bin/python -m unittest tests.test_workflows`
- `.venv/bin/agentshelf scan "benchmarks/fixtures/*.html" --batch --format sarif --output /tmp/agentshelf-artifacts/agentshelf-results.sarif`
- `.venv/bin/agentshelf scan "benchmarks/fixtures/*.html" --batch --format jsonl --output /tmp/agentshelf-artifacts/agentshelf-results.jsonl`
- `.venv/bin/agentshelf agent-tasks "benchmarks/fixtures/*.html" --batch --output /tmp/agentshelf-artifacts/agentshelf-tasks.jsonl`
- `.venv/bin/agentshelf calibrate /tmp/agentshelf-artifacts/agentshelf-results.jsonl --from-results --format json --output /tmp/agentshelf-artifacts/calibration-report.json`
- `.venv/bin/agentshelf dashboard /tmp/agentshelf-artifacts/calibration-report.json --format html --output /tmp/agentshelf-artifacts/calibration-dashboard.html`
- `.venv/bin/agentshelf draft-labels /tmp/agentshelf-artifacts/calibration-report.json --include-tasks --output /tmp/agentshelf-artifacts/draft-calibration-labels.json`
- `.venv/bin/python -m unittest tests.test_cli.CliTests.test_render_fixtures_writes_platform_snapshots_and_manifest tests.test_cli.CliTests.test_render_fixtures_outputs_are_scannable_by_profile tests.test_cli.CliTests.test_render_fixtures_rejects_missing_title`
- `.venv/bin/agentshelf render-fixtures examples/storefront-products.json --platform all --output-dir /tmp/agentshelf-generated-snapshots --manifest /tmp/agentshelf-generated-snapshots/manifest.json --format json`
- `.venv/bin/agentshelf scan /tmp/agentshelf-generated-snapshots --batch --format jsonl --min-score 85`

## Next Best Task
Add native import adapters for common merchant exports: Shopify product JSON, WooCommerce product CSV, and generic headless catalog API JSON.

## Risks
- Rendered snapshot mode requires users to install Playwright and Chromium; the base CLI remains dependency-free.
- Raw URL snapshot mode still does not execute JavaScript unless `--rendered` is explicitly used.
- Benchmark fixtures are curated examples, not empirical evidence of improved ChatGPT, Google, Perplexity, or Claude shopping-agent ranking.
