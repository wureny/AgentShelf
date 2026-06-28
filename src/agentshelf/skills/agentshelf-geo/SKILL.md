---
name: agentshelf-geo
description: >
  Use AgentShelf CLI as a coding-agent workflow for AI-readable commerce and
  GEO work. Trigger when auditing or improving product pages, Shopify/DTC
  storefronts, creator commerce, artist stores, custom gift pages, schema, FAQ,
  crawlability, AI shopping readiness, agent commerce GEO, or when Codex needs
  to turn AgentShelf reports into concrete code/content edits and verification.
---

# AgentShelf GEO

Use this skill to run AgentShelf as an agent-native audit and remediation loop for AI-readable commerce. The goal is not only to produce a report; the goal is to edit the target storefront, template, fixture, or content until the important GEO and commerce-readiness tasks are resolved.

## Core Loop

1. Locate the target page source.
   - Prefer local HTML snapshots, generated storefront fixtures, product templates, theme sections, or page components.
   - Use live URLs only when the user explicitly wants URL fetch behavior or no local page source exists.

2. Run the full GEO workflow when you need an artifact bundle.

```bash
agentshelf geo-run <page-or-url> \
  --brand "<brand or store>" \
  --category "<commerce category>" \
  --vertical commerce \
  --output-dir agentshelf-geo-run
```

Use the generated `agentshelf-geo-run/summary.json`, `geo-report.json`, `geo-tasks.jsonl`, and validation files as the implementation handoff.

3. If you need separate files or custom wiring, run a manual GEO audit.

```bash
agentshelf geo-audit <page-or-url> \
  --brand "<brand or store>" \
  --category "<commerce category>" \
  --vertical commerce \
  --format json \
  --output agentshelf-geo-report.json

agentshelf validate-contract agentshelf-geo-report.json
```

Use `--vertical artist_store` for handmade, creator-commerce, commission, custom gift, artist-made, or one-of-one product contexts.

4. Convert the report into agent tasks.

```bash
agentshelf geo-tasks agentshelf-geo-report.json --output agentshelf-geo-tasks.jsonl
agentshelf validate-contract agentshelf-geo-tasks.jsonl --contract agentshelf.geo_task.v0
```

5. Read `agentshelf-geo-tasks.jsonl` and implement high-priority tasks first.
   - Edit templates, components, static pages, generated fixtures, product data mappers, schema builders, CMS seed content, or docs as appropriate.
   - Do not fabricate reviews, ratings, press, social proof, shipping promises, prices, stock, or external authority.
   - Use placeholders only when the output is explicitly a draft or scaffold and clearly marks merchant-confirmed fields.

6. Verify after edits.

```bash
agentshelf geo-audit <page-or-url> --format json --output agentshelf-geo-report-after.json
agentshelf validate-contract agentshelf-geo-report-after.json
agentshelf geo-tasks agentshelf-geo-report-after.json --output agentshelf-geo-tasks-after.jsonl
agentshelf validate-contract agentshelf-geo-tasks-after.jsonl --contract agentshelf.geo_task.v0
agentshelf scan <page-or-snapshot> --format markdown --min-score 70
```

If the target has multiple generated pages, use `agentshelf scan <dir-or-glob> --batch` for the commerce-readiness gate.

## Choosing Commands

- Use `geo-audit` for broad GEO work: crawlability, entity consistency, AI intent coverage, prompt panel, GTM assets, and patch suggestions.
- Use `geo-tasks` when Codex needs a concrete work queue from the GEO report.
- Use `geo-run` when the user wants the whole artifact bundle in one command.
- Use `validate-contract` before implementation when a task depends on stable JSON or JSONL output.
- Use `scan` for product-page readiness gates: price, availability, shipping, returns, specs, reviews, Product schema, FAQ, variants, policy, and agent actionability.
- Use `agent-tasks` for product-page remediation tasks across snapshots or fixtures.
- Use `render-fixtures` when product data exists but HTML snapshots need to be generated before auditing.
- Use `snapshot` only when a live URL must be captured; use `--rendered` only when JS-rendered content is required and Playwright is installed.

## Editing Priorities

Handle tasks in this order unless the user says otherwise:

1. Critical/high crawlability or indexability blockers: `robots.txt`, noindex, canonical, sitemap.
2. Product and Offer schema gaps.
3. Opening answer block and page-level factual copy.
4. FAQ, shipping, return/cancellation, care, custom order, and limitations.
5. Entity consistency: brand, artist, studio, about/contact, sameAs links.
6. Image alt text and product media evidence.
7. Collection pages, gift guides, comparison pages, commission process pages, artist factsheets.

## Output Discipline

- Keep JSON and JSONL artifacts machine-readable.
- Put human summaries in Markdown files or final response prose, not inside JSON fields.
- Preserve existing project style and framework conventions.
- For Shopify/Liquid, prefer theme sections/snippets and JSON-LD snippets.
- For React/Next/headless storefronts, prefer typed components, metadata helpers, and schema builders.
- For static HTML fixtures, make direct HTML edits and rerun AgentShelf.

## Task Contract

When details are needed, read `references/task-contract.md`.
