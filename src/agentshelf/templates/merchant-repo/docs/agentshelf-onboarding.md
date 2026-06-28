# AgentShelf Merchant Onboarding

This repository has been initialized for AgentShelf GEO and product-page readiness audits.

## What Was Added

- `.github/workflows/agentshelf-geo.yml`: GitHub Actions workflow that runs `geo-run`, `scan`, and coding-agent task export.
- `.agentshelf.json`: local scan defaults for humans and CI.
- `.codex/skills/agentshelf-geo/`: Codex-style skill for audit-task-edit-verify remediation.
- `snapshots/agentshelf-demo-product.html`: safe local demo snapshot.

## Local Smoke Check

```bash
python3 -m pip install "git+https://github.com/wureny/AgentShelf.git@main"

agentshelf geo-run snapshots/agentshelf-demo-product.html \
  --brand "{{BRAND}}" \
  --category "{{CATEGORY}}" \
  --vertical {{VERTICAL}} \
  --output-dir artifacts/agentshelf/geo-run \
  --format json

agentshelf scan snapshots/agentshelf-demo-product.html --config .agentshelf.json

agentshelf adoption-check . \
  --brand "{{BRAND}}" \
  --category "{{CATEGORY}}" \
  --vertical {{VERTICAL}}
```

## Replace The Demo Snapshot

Use one of these production inputs:

- Shopify theme or Liquid fixture output.
- Headless storefront rendered HTML from a build step.
- Catalog exports rendered with `agentshelf render-fixtures`.
- Scheduled raw/rendered snapshots stored as CI artifacts.

Do not point the PR gate at a live checkout flow. AgentShelf is a local-input audit and remediation workflow, not checkout automation.

## Codex Remediation Loop

Ask Codex to use `$agentshelf-geo`, then:

1. Run `agentshelf geo-run` against a product-page snapshot.
2. Read `geo-tasks.jsonl` and `agentshelf-tasks.jsonl`.
3. Edit templates, components, schema builders, product data mappers, or fixture content.
4. Re-run `geo-run` and `scan`.
5. Commit only merchant-owned source, generated fixtures, and AgentShelf config.

Do not fabricate reviews, ratings, press, inventory, shipping promises, return promises, or external profiles.
