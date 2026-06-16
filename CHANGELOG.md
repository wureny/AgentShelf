# Changelog

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
