# Status

- Version: 0.36.0
- Phase: maintain_or_extend
- Current focus: public release readiness for a coding-agent-first AgentShelf workflow
- Current blocker: none

## Current Release Posture

AgentShelf is suitable for production dogfooding as a local CLI, GitHub Action, generated-snapshot audit, and Codex-style remediation workflow. It is not yet a hosted crawler, Shopify app, checkout automation system, or empirically proven external-agent ranking tool.

The intended mature loop is:

1. Generate or capture merchant-owned product-page snapshots.
2. Run `agentshelf geo-run`, `agentshelf geo-run --store-snapshot`, `agentshelf scan`, or the GitHub Action.
3. Let a coding agent consume `geo-tasks.jsonl` or `agentshelf-tasks.jsonl`.
4. Edit storefront templates, schema builders, product data mappers, or content.
5. Re-run AgentShelf until blockers and score gates are resolved.

## Public Surfaces

- `agentshelf scan`: human and CI product-page readiness gate.
- `agentshelf geo-run`: one-command GEO artifact bundle for coding agents.
- `agentshelf geo-run --store-snapshot`: store-level GEO audit bundle for local multi-page storefront snapshots.
- `agentshelf dogfood --fixture artist-store-comparison`: deterministic local before/after dogfood loop for Codex-style agents.
- `agentshelf geo-tasks`: JSONL implementation queue from a GEO report.
- `agentshelf export-skill`: exports the bundled `agentshelf-geo` skill into merchant repos.
- `agentshelf init-merchant-repo`: initializes a storefront repo with workflow, config, demo snapshot, onboarding docs, and skill.
- `agentshelf adoption-check`: verifies an initialized merchant repo before enforcing CI, or the AgentShelf source checkout before release.
- `agentshelf public-audit`: checks public release hygiene before tags or Marketplace copy.
- `agentshelf release-check`: verifies versioned release surfaces before tagging.
- `agentshelf release-notes`: generates conservative GitHub release draft copy.

## Verified Workflows

- Full unit suite.
- GEO audit-task-edit-verify example.
- Packaged skill export and drift tests.
- Merchant repo initialization and adoption checks.
- Shopify and headless generated-snapshot adoption regressions.
- Release-readiness and public-audit checks.
- Store-level artist-store before/after fixture and `dogfood --fixture artist-store-comparison` proving deterministic local readiness improvement without external AI provider claims.
- Source checkout `adoption-check .` validating public-audit, release-check, docs, skill assets, and fixture quality.
- Page-level GEO internals split into type, report, task, and patch modules while preserving the `agentshelf.geo` public import surface.

## Next Best Task

Run store-level dogfood on one merchant-owned snapshot bundle, convert any false positives into synthetic fixtures, then create a reviewed GitHub tag after the maintainer approves release notes for the current version.

## Risks

- Rendered snapshot mode requires the optional Playwright extra and Chromium install.
- Raw URL mode does not execute JavaScript unless rendered mode is explicitly used.
- Curated fixtures are useful regression evidence, not proof of external ChatGPT, Google, Perplexity, Claude, Gemini, or Bing ranking lift.
- Unusual merchant catalog exports may need a small mapping step before `render-fixtures`.
- Marketplace publication should wait until a reviewed release tag exists and CI is green on that tag.
