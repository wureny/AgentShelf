# Architecture

## Overview
The MVP is a standard-library Python CLI with a three-step flow:

1. Read an HTML or text product-page snapshot from disk.
2. Run weighted deterministic checks for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema signals.
3. Parse Product JSON-LD when present to extract stronger evidence for offers and availability.
4. Render markdown, JSON, or JSONL reports with prioritized fixes.

## Components
- `src/agentshelf/engine.py`: parser, heuristic scoring engine, JSON-LD extraction, and renderers
- `src/agentshelf/cli.py`: argument parsing, batch input resolution, threshold exits, and file I/O
- `tests/test_engine.py`: regression coverage for parsing and rendering
- `tests/test_cli.py`: CLI behavior and threshold coverage
- `examples/sample_product_page.html`: smoke-test input
- `examples/weak_product_page.html`: failing-page fixture

## Design Choices
- Standard library only, so the demo stays runnable without installs.
- Local-file input first, so the product can run without network access or storefront credentials.
- Weighted pass/fail checks keep the first version explainable and easy to extend.
- GitHub Action wraps the CLI instead of duplicating scanning logic.

## Extension Path
- Add URL fetch mode with polite crawling and explicit safe flags.
- Add batch scanning and CSV/JSON exports for catalog-level audits.
- Add deeper schema validation for variants, offers, return policy, and merchant policy metadata.
