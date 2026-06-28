# Merchant Adoption

This guide shows how a merchant repository should adopt AgentShelf when the goal is a practical Codex-style remediation loop, not a one-off audit demo.

## 1. Initialize The Repo

Run this from the merchant storefront repository:

```bash
agentshelf init-merchant-repo \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store
```

This writes:

- `.agentshelf.json` for local and CI scan defaults.
- `.github/workflows/agentshelf-geo.yml` for PR and manual audit runs.
- `.codex/skills/agentshelf-geo/` so Codex can run the audit-task-edit-verify loop.
- `snapshots/agentshelf-demo-product.html` as a safe local smoke snapshot.
- `docs/agentshelf-onboarding.md` for repository-local operator instructions.

## 2. Verify Adoption Before Enforcing CI

Run the local adoption check:

```bash
agentshelf adoption-check . \
  --snapshot snapshots/agentshelf-demo-product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store
```

The command checks that the repo has the expected config, workflow, exported Codex skill, onboarding docs, and snapshot. It also runs a product-readiness scan and a deterministic GEO task generation pass.

Use JSON when a coding agent or CI job needs to parse the result:

```bash
agentshelf adoption-check . --format json --output artifacts/agentshelf/adoption-check.json
```

## 3. Replace The Demo Snapshot

The demo snapshot only proves the wiring. Before enforcing score gates, replace it with merchant-owned product-page HTML from one of these sources:

- Shopify theme or Liquid fixture output.
- Headless storefront HTML from a build step.
- Catalog exports rendered with `agentshelf render-fixtures`.
- Scheduled raw or rendered snapshots stored as CI artifacts.

Do not point AgentShelf at checkout flows, private customer pages, or raw third-party HTML that should not be committed.

For concrete Shopify/Liquid and headless/Next.js snapshot generation examples, see [Platform Adoption](PLATFORM_ADOPTION.md).

## 4. Let Codex Implement The Tasks

Ask Codex to use `$agentshelf-geo`, then follow this loop:

```bash
agentshelf geo-run snapshots/product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir artifacts/agentshelf/geo-run

agentshelf validate-contract artifacts/agentshelf/geo-run/geo-report.json
agentshelf validate-contract artifacts/agentshelf/geo-run/geo-tasks.jsonl --contract agentshelf.geo_task.v0
```

Codex should read `geo-tasks.jsonl`, edit templates, schema builders, product data mappers, or fixture content, and then rerun:

```bash
agentshelf adoption-check . --snapshot snapshots/product.html --brand "Moon Kiln Studio" --category "custom handmade teacups" --vertical artist_store
agentshelf scan snapshots/product.html --config .agentshelf.json
```

## Production Boundary

AgentShelf is useful when the merchant repository can produce stable product-page snapshots or generated storefront fixtures. It does not prove external ranking lift in ChatGPT, Google, Perplexity, Claude, Gemini, Bing, or other shopping agents. Treat it as a deterministic local audit, CI gate, and coding-agent task generator.
