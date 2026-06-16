# Architecture

## Overview
The MVP is a lightweight Python CLI with a three-step flow:

1. Discover product-like URLs from robots.txt sitemap hints or an explicit sitemap URL.
2. Read an HTML/text product-page snapshot from disk, fetch raw HTML with `snapshot`, or capture rendered HTML with the optional `agentshelf[render]` extra.
3. Run weighted deterministic checks for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema signals.
4. Parse Product JSON-LD when present to extract stronger evidence for offers and availability.
5. Compute dimension scores for discoverability, offer clarity, policy clarity, and agent actionability.
6. Render human reports, JSON/JSONL, SARIF, or an agent-native JSON contract with prioritized tasks.
7. Compare raw and rendered snapshots to decide whether browser capture is worth the operational cost for a page class.
8. Compare scheduled scan result files to surface product-page regressions, improvements, and catalog coverage changes.

## Components
- `src/agentshelf/engine.py`: parser, heuristic scoring engine, JSON-LD extraction, and renderers
- `src/agentshelf/cli.py`: argument parsing, batch input resolution, snapshot fetches, threshold exits, and file I/O
- `tests/test_engine.py`: regression coverage for parsing and rendering
- `tests/test_cli.py`: CLI behavior and threshold coverage
- `examples/sample_product_page.html`: smoke-test input
- `examples/weak_product_page.html`: failing-page fixture
- `benchmarks/fixtures/`: curated agent-readiness benchmark inputs
- `benchmarks/expected/`: expected benchmark bands, blockers, and agent tasks

## Design Choices
- Standard-library raw snapshot mode keeps the base demo runnable without browser installs.
- Rendered snapshot mode is optional and dynamically imports Playwright only when `--rendered` is requested.
- Local-file input first, so the product can run without network access or storefront credentials.
- Weighted pass/fail checks keep the first version explainable and easy to extend.
- GitHub Action wraps the CLI instead of duplicating scanning logic.
- `agent-audit` uses stable task-oriented JSON so coding agents can act on results directly.
- `agent-tasks` emits JSONL so coding agents can remediate batches without parsing human reports.
- `compare` reports score deltas, dimension deltas, unlocked signals, regressions, and an agent recommendation for raw vs rendered snapshots.
- `diff` compares stored scan artifacts instead of rescanning pages, so scheduled jobs can produce regression reports from CI artifacts.
- SARIF output maps failed checks into code-scanning-style findings for CI and GitHub annotations.
- `.agentshelf.json` keeps production scan gates repeatable across local, CI, and scheduled runs.
- Raw snapshot mode does not execute JavaScript; dynamic pages are flagged instead of silently trusted. `--rendered` handles single-page JS capture when the optional browser dependency is installed.
- `snapshot --url-file` supports real merchant URL lists without introducing site-wide crawling behavior.
- `discover` consumes sitemap metadata rather than crawling arbitrary links, keeping audits predictable and polite.

## Extension Path
- Add deeper schema validation for variants, offers, return policy, and merchant policy metadata.
- Add run history retention helpers for teams that want AgentShelf to manage previous/current artifacts locally.
- Add empirical benchmark runs against real agent answer quality before claiming ranking or conversion lift.
