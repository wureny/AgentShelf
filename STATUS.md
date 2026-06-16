# Status

- Date: 2026-06-16
- Phase: maintain_or_extend
- Project path: `/Users/wurenyu/Documents/Codex/2026-06-06/intent-to-prompt-users-wurenyu-codex/projects/agentic-commerce-readiness-scanner`
- Canonical requested root: `/Users/wurenyu/workspace`
- Current blocker: none

## Current Milestone
Make storefront-specific extraction configurable for production CI and agent workflows.

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

## Next Best Task
Add profile-specific benchmark fixtures and docs for WooCommerce and headless storefront exports.

## Risks
- Rendered snapshot mode requires users to install Playwright and Chromium; the base CLI remains dependency-free.
- Raw URL snapshot mode still does not execute JavaScript unless `--rendered` is explicitly used.
- Benchmark fixtures are curated examples, not empirical evidence of improved ChatGPT, Google, Perplexity, or Claude shopping-agent ranking.
