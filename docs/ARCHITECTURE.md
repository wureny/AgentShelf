# Architecture

## Overview
The MVP is a standard-library Python CLI with a three-step flow:

1. Read an HTML/text product-page snapshot from disk, or fetch raw HTML with `snapshot`.
2. Run weighted deterministic checks for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema signals.
3. Parse Product JSON-LD when present to extract stronger evidence for offers and availability.
4. Compute dimension scores for discoverability, offer clarity, policy clarity, and agent actionability.
5. Render human reports or an agent-native JSON contract with prioritized tasks.

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
- Standard library only, so the demo stays runnable without installs.
- Local-file input first, so the product can run without network access or storefront credentials.
- Weighted pass/fail checks keep the first version explainable and easy to extend.
- GitHub Action wraps the CLI instead of duplicating scanning logic.
- `agent-audit` uses stable task-oriented JSON so coding agents can act on results directly.
- Raw snapshot mode does not execute JavaScript; dynamic pages are flagged instead of silently trusted.

## Extension Path
- Add deeper schema validation for variants, offers, return policy, and merchant policy metadata.
- Add optional Playwright-backed rendered snapshots behind an extra dependency.
- Add empirical benchmark runs against real agent answer quality before claiming ranking or conversion lift.
