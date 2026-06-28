# AgentShelf

Open-source GEO and product page audits for AI-readable commerce.

AgentShelf checks whether product pages expose the signals AI shopping agents need for discovery, ranking, and purchase recommendations: product title, price, availability, shipping, returns, specs, reviews, FAQ, and Product structured data.

It also reads storefront implementation signals that matter in real Shopify/DTC pages: embedded product JSON, variant arrays, selling plan groups, metafield-like keys, policy snippets, subscription terms, bundle contents, regional shipping promises, and return policy schema.

AgentShelf now includes a deterministic GEO Skill v0 for AI-readable commerce. `agentshelf geo-audit` turns a merchant page or URL plus brand/category context into a structured GEO report with crawlability, indexability, structured data, content extractability, entity consistency, commerce attribute, trust, AI intent, prompt panel, GTM opportunity, and patch recommendations.

For Codex-style coding agents, AgentShelf ships a repo-local skill at [`skills/agentshelf-geo/SKILL.md`](skills/agentshelf-geo/SKILL.md). The intended agent workflow is: run `geo-audit`, convert the report with `geo-tasks`, edit the storefront or fixture, then verify with `geo-audit` and `scan`.

## Production Posture
AgentShelf is ready for production dogfooding in CI when you can provide one of these inputs:

- generated product-page HTML snapshots from your storefront build
- stable theme fixture HTML committed or produced during CI
- Shopify, WooCommerce, headless, or normalized catalog exports rendered with `agentshelf render-fixtures`
- raw or rendered snapshots captured by a scheduled job before the PR gate runs

It is not a fully managed crawler, hosted Shopify app, or checkout automation system. Treat the score as an explainable CI signal, not a claim that a specific external shopping agent will rank the product higher. The mature production loop is: generate or capture snapshots, run `agentshelf scan`, upload human-readable evidence, emit `agentshelf agent-tasks` for coding agents, and tighten thresholds after a few real merchant review cycles.

For GEO work, treat `geo-audit` as a local deterministic skill for review and implementation planning. It does not call ChatGPT, Google, Perplexity, Claude, Gemini, Bing, or Search Console APIs, and it does not claim live visibility lift. It creates the factual report, prompt panel, and patch queue needed before those monitoring integrations are worth adding.

## Who It Helps
- Shopify and DTC operators preparing storefronts for agentic commerce
- AI commerce consultants doing quick storefront readiness audits
- indie commerce founders validating whether product pages are machine-readable
- Codex-style coding agents that need deterministic remediation tasks instead of prose-only audit notes

## 5-Minute Quickstart
```bash
python3 -m pip install -e .
agentshelf scan examples/sample_product_page.html --format markdown
```

Scan a weak page and fail below a threshold:

```bash
agentshelf scan examples/weak_product_page.html --min-score 70
```

Batch scan page snapshots:

```bash
agentshelf scan "examples/*.html" --batch --format jsonl --output agentshelf-results.jsonl
```

Force a storefront adapter profile when you know the page type:

```bash
agentshelf scan examples/shopify_variant_product.html --profile shopify --format markdown
```

Discover product URLs from sitemap hints:

```bash
agentshelf discover --site https://example.com --output product-urls.txt
```

Run a repeatable CI gate from config:

```bash
agentshelf scan "examples/*.html" --batch --config examples/agentshelf.config.json
```

Emit a JSON contract for a coding agent:

```bash
agentshelf agent-audit examples/weak_product_page.html --contract v1
```

Emit batch remediation tasks for a coding agent:

```bash
agentshelf agent-tasks examples --batch --output agentshelf-tasks.jsonl
```

Run a GEO Skill audit for an artist-store or creator-commerce page:

```bash
agentshelf geo-audit examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --format markdown
```

Write both Markdown and JSON GEO reports:

```bash
agentshelf geo-audit examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --competitor Etsy \
  --persona "tea lovers" \
  --use-case "meaningful custom gifts" \
  --format both \
  --out reports/moon-kiln-geo-report
```

Turn a GEO report into a Codex-readable task queue:

```bash
agentshelf geo-tasks reports/moon-kiln-geo-report.json \
  --output reports/moon-kiln-geo-tasks.jsonl
```

Validate agent-facing contracts before implementation:

```bash
agentshelf validate-contract reports/moon-kiln-geo-report.json
agentshelf validate-contract reports/moon-kiln-geo-tasks.jsonl --contract agentshelf.geo_task.v0
```

Fetch a raw HTML snapshot for later audit:

```bash
agentshelf snapshot https://example.com/product --output snapshots/product.html
```

Fetch a URL list and write a manifest:

```bash
agentshelf snapshot --url-file product-urls.txt --output-dir snapshots --manifest snapshots/manifest.json
```

Fetch a rendered snapshot for JS-heavy storefronts:

```bash
python3 -m pip install -e ".[render]"
python3 -m playwright install chromium
agentshelf snapshot https://example.com/product --rendered --output snapshots/product.html
```

Generate stable pre-merge snapshots from a catalog export:

```bash
agentshelf render-fixtures examples/storefront-products.json \
  --platform all \
  --output-dir snapshots \
  --manifest snapshots/manifest.json
agentshelf scan snapshots --batch --format jsonl --output agentshelf-results.jsonl
```

Import native merchant exports without reshaping first:

```bash
agentshelf render-fixtures examples/shopify-products.json \
  --input-format shopify \
  --platform shopify \
  --output-dir snapshots/shopify
agentshelf render-fixtures examples/woocommerce-products.csv \
  --input-format woocommerce \
  --platform woocommerce \
  --output-dir snapshots/woocommerce \
  --tasks-output import-tasks.jsonl \
  --fail-on-warnings
agentshelf render-fixtures examples/headless-catalog.json \
  --input-format headless \
  --platform headless \
  --output-dir snapshots/headless
```

Compare raw vs rendered snapshots:

```bash
agentshelf compare examples/js_product_raw.html examples/js_product_rendered.html --format json
```

Compare two scheduled audit runs:

```bash
agentshelf diff previous-results.jsonl current-results.jsonl --output audit-diff.md
```

Run a local scheduled audit with previous/current history managed for you:

```bash
agentshelf audit-run "snapshots/*.html" --batch --history-dir .agentshelf/runs --tasks-output agentshelf-tasks.jsonl
```

Summarize calibration hotspots from real-page snapshots and export anonymized fixture candidates:

```bash
agentshelf calibrate "snapshots/*.html" \
  --batch \
  --export-fixtures calibration-fixtures \
  --format json
agentshelf draft-labels calibration-report.json \
  --output draft-calibration-labels.json
agentshelf dashboard calibration-report.json \
  --format html \
  --output calibration-dashboard.html
```

Evaluate a rule change against human calibration labels:

```bash
agentshelf scan benchmarks/fixtures --batch --format jsonl --output calibration-results.jsonl
agentshelf evaluate calibration-results.jsonl \
  --labels examples/calibration-labels.json \
  --fail-on-regressions
```

## Example Output
```text
# AgentShelf Report: TrailBottle Pro 24oz

## Summary
- Score: 89/100
- Readiness band: strong
- Passed checks: 13/15
- Not applicable checks: 2
- Dimension scores: discoverability=100, offer_clarity=100, policy_clarity=79, agent_actionability=75
```

Weak pages return prioritized fixes:

```text
## Top Fixes
- Expose a machine-readable price near the purchase controls.
- State whether the item is in stock, backordered, or unavailable.
- Add a compact specifications section for key product attributes.
```

## CLI
```bash
agentshelf scan <file-or-dir-or-glob> [options]
agentshelf agent-audit <file-or-url> [options]
agentshelf agent-tasks <file-or-dir-or-glob> [options]
agentshelf geo-audit <file-or-url> [--brand <name>] [--category <category>] [--vertical commerce|creator_commerce|artist_store|local_service|generic] [--format markdown|json|both]
agentshelf geo-tasks <geo-report.json> [--format jsonl|json]
agentshelf validate-contract <artifact.json-or-jsonl> [--contract auto|agentshelf.geo_audit.v0|agentshelf.geo_task.v0|agentshelf.geo_tasks.v0]
agentshelf compare <raw.html> <rendered.html> [options]
agentshelf diff <baseline-results.jsonl> <current-results.jsonl> [options]
agentshelf audit-run <file-or-dir-or-glob> [options]
agentshelf calibrate <file-or-dir-or-glob-or-results.jsonl> [options]
agentshelf draft-labels <calibration-report.json> [options]
agentshelf dashboard <calibration-report.json> [options]
agentshelf evaluate <results.json-or-jsonl> --labels <labels.json> [options]
agentshelf discover --site <url> [options]
agentshelf discover --sitemap <url> [options]
agentshelf snapshot <url> --output <path> [--rendered]
agentshelf snapshot --url-file <urls.txt> --output-dir <dir> [--manifest <path>]
agentshelf render-fixtures <products.json-or-csv> [--input-format auto|agentshelf|shopify|woocommerce|headless] [--platform shopify|woocommerce|headless|all] [--tasks-output import-tasks.jsonl] [--fail-on-warnings]
```

Options:

- `--batch`: allow directory or glob scanning
- `--config <path>`: load repeatable scan defaults from JSON
- `--format markdown|json|jsonl|sarif`: choose report format
- `--profile auto|generic|shopify|woocommerce|headless`: choose or auto-detect storefront extraction behavior
- `--output <path>`: write output to a file
- `--min-score <0-100>`: return non-zero when any page scores below this value
- `--fail-on weak|not_ready`: return non-zero when any page is at or below the selected band

`agent-audit` emits JSON with stable fields for coding agents: `target`, `score`, `band`, `blocking_issues`, `agent_tasks`, `evidence`, `next_actions`, `confidence`, and `warnings`.

`agent-tasks` emits JSONL remediation tasks across one page or a batch, so coding agents can pick up precise page areas, reasons, and acceptance checks.

`geo-audit` emits a broader GEO report for AI-readable commerce. Use it when the question is not only "does this product page expose price/schema/policy?" but "what page, prompt, entity, trust, and patch work would make this merchant easier for generative engines and AI shopping agents to understand and cite?" URL mode attempts lightweight `robots.txt`, `sitemap.xml`, and `llms.txt` checks; local-file mode keeps the report runnable without network access. `--format both --out reports/name` writes `reports/name.md` and `reports/name.json`.

`geo-tasks` turns `geo-audit --format json` output into JSONL work items for coding agents. Each row includes `files_or_page_area`, `reason`, `suggested_copy`, optional `suggested_schema`, `acceptance_check`, and `verification_command`.

`validate-contract` validates AgentShelf JSON and JSONL artifacts before a coding agent acts on them. It currently covers `agentshelf.geo_audit.v0`, `agentshelf.geo_task.v0`, and the `agentshelf.geo_tasks.v0` JSON wrapper using the published schemas in `schemas/` plus dependency-free structural checks.

`snapshot` fetches raw HTML with the standard library by default. Use `--rendered` for a Playwright-backed single-page capture when product data is injected by JavaScript. Rendered mode is optional so the base CLI stays lightweight.

`render-fixtures` turns product exports into deterministic Shopify, WooCommerce, and headless HTML snapshots. It accepts AgentShelf's normalized product JSON, Shopify product JSON, WooCommerce product CSV, and generic headless catalog JSON. Use it in CI when you can export catalog data or template data before deployment but do not want live crawling or browser capture in every PR. The output manifest includes import validation warnings for missing price, currency, stock, variants, shipping, returns, specs, or variant option context; add `--fail-on-warnings` when those gaps should fail CI before scan results are trusted. Add `--tasks-output import-tasks.jsonl` when a coding agent should fix the export job or catalog mapper.

`compare` shows whether rendered capture unlocks agent-readiness signals that raw HTML misses. It reports score deltas, dimension deltas, newly visible evidence, regressions, and an agent recommendation.

`diff` compares two `agentshelf scan --format json|jsonl` outputs. It reports page-set regressions, improvements, new or resolved blocking issues, catalog additions/removals, and the next remediation tasks an agent should pick up.

`audit-run` is the scheduled-job wrapper around `scan` and `diff`. It writes `<history-dir>/current-results.jsonl`, rotates the previous run into `<history-dir>/previous-results.jsonl`, archives each run as `results-<timestamp>.jsonl`, writes an `audit-diff.md` report, and can emit `agent-tasks` JSONL in the same pass.

`calibrate` reviews real-page scan output for likely false-positive and false-negative categories. It can scan HTML snapshots directly or read existing `scan --format json|jsonl` artifacts with `--from-results`. Use `--export-fixtures` to write anonymized local HTML candidates plus metadata sidecars for benchmark review.

`draft-labels` turns `calibrate --format json` output into editable draft labels. Draft labels use `verdict: needs_review` and are skipped by `evaluate` until a human changes them to `true_positive` or `false_positive`.

`dashboard` renders `calibrate --format json` output as standalone HTML or Markdown. Use it as a CI artifact or merchant-facing review queue when the page set is too large for raw JSON.

`evaluate` compares scan results against a human label file. Use it after calibration reviews to lock confirmed true positives and false positives, then run it in CI with `--fail-on-regressions` before changing rules or thresholds.

`discover` reads `robots.txt` for `Sitemap:` hints or accepts an explicit sitemap URL. It filters product-like URLs and emits a URL list for `snapshot --url-file`; it does not crawl arbitrary site links.

## Production Workflows
Use a config file when AgentShelf runs in CI or scheduled audits:

```json
{
  "format": "sarif",
  "min_score": 70,
  "fail_on": "not_ready",
  "output": "agentshelf-results.sarif"
}
```

Use SARIF when you want GitHub code scanning annotations:

```bash
agentshelf scan "snapshots/*.html" --batch --format sarif --output agentshelf-results.sarif
```

Use `agent-tasks` when a coding agent should directly edit a product template, fixture, or generated page until blocking issues are gone.

Use `compare` before adopting rendered capture broadly:

```bash
agentshelf compare examples/js_product_raw.html examples/js_product_rendered.html --format markdown
```

If compare says raw capture is sufficient, keep the cheaper raw workflow. If rendered unlocks price, inventory, variant, or schema signals, use `snapshot --rendered` for that page class.

End-to-end scheduled audit:

```bash
agentshelf discover --site https://example.com --limit 100 --output product-urls.txt
agentshelf snapshot --url-file product-urls.txt --output-dir snapshots --manifest snapshots/manifest.json
agentshelf audit-run "snapshots/*.html" \
  --batch \
  --history-dir .agentshelf/runs \
  --tasks-output agentshelf-tasks.jsonl \
  --min-score 70
agentshelf calibrate .agentshelf/runs/current-results.jsonl \
  --from-results \
  --format json \
  --output calibration-report.json
agentshelf dashboard calibration-report.json \
  --format html \
  --output calibration-dashboard.html
agentshelf draft-labels calibration-report.json \
  --output draft-calibration-labels.json
agentshelf evaluate .agentshelf/runs/current-results.jsonl \
  --labels examples/calibration-labels.json \
  --fail-on-regressions
```

Pre-merge fixture audit from product data:

```bash
agentshelf render-fixtures examples/storefront-products.json \
  --platform all \
  --output-dir snapshots \
  --manifest snapshots/manifest.json
agentshelf scan snapshots --batch --format sarif --output agentshelf-results.sarif --min-score 85
agentshelf agent-tasks snapshots --batch --output agentshelf-tasks.jsonl
```

This is the lowest-ops path for coding agents: generate deterministic storefront-shaped HTML, run AgentShelf, then edit product data or templates until `agentshelf-tasks.jsonl` has no high-priority tasks.

Native merchant export audit:

```bash
agentshelf render-fixtures examples/woocommerce-products.csv \
  --input-format auto \
  --platform woocommerce \
  --output-dir snapshots/woocommerce \
  --manifest snapshots/woocommerce/manifest.json \
  --tasks-output snapshots/woocommerce/import-tasks.jsonl \
  --fail-on-warnings
agentshelf scan snapshots/woocommerce --batch --profile woocommerce --format jsonl --min-score 85
```

On the first run, `audit-run` creates a baseline. On later runs, it automatically writes `.agentshelf/runs/audit-diff.md` from the last saved result set. In CI, upload `.agentshelf/runs/audit-diff.md`, `calibration-dashboard.html`, `draft-calibration-labels.json`, and `agentshelf-tasks.jsonl` as review artifacts so humans see the merchant-level regression summary and agents get machine-actionable fixes.

Use calibration reports before changing scoring rules. A common loop is: run real merchant snapshots, inspect `rendered_capture_review`, `profile_rule_review`, `policy_schema_review`, and `offer_extraction_review`, then export anonymized fixture candidates for cases that should become benchmark coverage.

When you want to turn calibration findings into regression coverage, run `draft-labels`, review the generated JSON, then change each useful label from `needs_review` to `true_positive` or `false_positive`. Draft labels are safe to commit because `evaluate` skips them until they are confirmed.

For a complete GitHub Actions artifact pipeline, see [`.github/workflows/agentshelf-artifacts.yml`](.github/workflows/agentshelf-artifacts.yml). It writes:

- `render-fixtures-manifest.json`, `render-fixtures-summary.json`, and `import-tasks.jsonl` when a catalog export is provided.
- `agentshelf-results.sarif` for GitHub code scanning annotations.
- `agentshelf-results.jsonl` for dashboards, diffs, and later evaluation.
- `agentshelf-tasks.jsonl` for Codex-style remediation agents.
- `calibration-report.json` plus HTML and Markdown dashboards for merchant review.
- `draft-calibration-labels.json` for turning review findings into confirmed labels.
- `calibration-evaluation.md` for checking confirmed labels when they exist.

The workflow intentionally uploads artifacts before enforcing the score gate. In a merchant repository, copy it, replace the default `path` with generated storefront snapshots such as `snapshots/*.html`, and add a `pull_request` trigger when the threshold is ready to block PRs.

It can also render fixtures from a merchant export before scanning:

```yaml
with:
  catalog: "exports/woocommerce-products.csv"
  input_format: woocommerce
  fixture_platform: woocommerce
  fail_on_import_warnings: "true"
  min-score: "85"
```

When `catalog` is set, the workflow uploads both import-level tasks (`import-tasks.jsonl`) and page-level tasks (`agentshelf-tasks.jsonl`), then fails only after artifacts are available for review.

Calibration labels use this shape:

```json
{
  "contract": "agentshelf.calibration_labels.v1",
  "labels": [
    {
      "source": "snapshots/product.html",
      "kind": "check",
      "id": "subscription_terms",
      "verdict": "true_positive",
      "note": "Subscription cadence and cancellation terms are genuinely missing."
    },
    {
      "source": "snapshots/strong-product.html",
      "kind": "check",
      "id": "return_policy_schema",
      "verdict": "false_positive",
      "note": "Return policy schema is present in a storefront-specific structure."
    }
  ]
}
```

Supported label kinds are `check`, `blocking_issue`, `agent_task`, `category`, and `warning`. `true_positive` means the finding should remain present; `false_positive` means it should be absent after the rule is fixed.

## GitHub Action
Use AgentShelf as a PR gate for product-page snapshots, generated storefront HTML, or theme fixture output. The Action is intentionally local-input first: it audits files produced by your build or fixture job, then fails the PR only after writing a report and a GitHub Step Summary.

Recommended first rollout:

1. Start with `format: markdown` and `min-score: "70"` so humans can inspect failures.
2. Upload `agentshelf-report.md` as an artifact on every run.
3. Add `agentshelf agent-tasks` or the full artifact workflow when you want Codex-style agents to fix pages automatically.
4. Pin a release tag such as `wureny/AgentShelf@v0.1.0` once the first release exists. Use `@main` only while testing this repository.

```yaml
name: AgentShelf

on:
  pull_request:

jobs:
  audit-commerce-pages:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Audit product-page snapshots
        uses: wureny/AgentShelf@v0.1.0
        with:
          path: "snapshots/**/*.html"
          min-score: "70"
          fail-on: not_ready
          format: markdown
          output: agentshelf-report.md
          profile: auto

      - name: Upload AgentShelf report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: agentshelf-report
          path: agentshelf-report.md
          if-no-files-found: warn
```

See [docs/workflows/agentshelf-pr-gate.yml](docs/workflows/agentshelf-pr-gate.yml) for a copyable PR gate.

Use SARIF when you want GitHub code scanning annotations:

```yaml
- name: Audit product-page snapshots
  uses: wureny/AgentShelf@v0.1.0
  with:
    path: "snapshots/**/*.html"
    min-score: "85"
    format: sarif
    output: agentshelf-results.sarif

- uses: github/codeql-action/upload-sarif@v3
  if: always()
  with:
    sarif_file: agentshelf-results.sarif
```

When the gate fails, AgentShelf writes a short failure summary to the workflow log:

```text
AgentShelf gate failed.
Failed pages: 1 of 4
Minimum score: 70

Pages to fix:
- TrailBottle Landing Page (snapshots/trailbottle.html): score 31/100, band not_ready
  - Expose a machine-readable price near the purchase controls.
  - State whether the item is in stock, backordered, or unavailable.
  - Add delivery timing or shipping-cost guidance near checkout intent.

Next steps:
- Read the report output for evidence and exact failed checks.
- Run `agentshelf agent-tasks <path> --batch --output agentshelf-tasks.jsonl` for coding-agent remediation tasks.
- Re-run the same scan after fixing product data, templates, or generated snapshots.
```

If you want review artifacts, calibration dashboards, SARIF, JSONL results, and coding-agent task queues in one workflow, use the included artifact workflow:

```bash
cp .github/workflows/agentshelf-artifacts.yml <storefront-repo>/.github/workflows/agentshelf-artifacts.yml
```

Run it manually first with `workflow_dispatch`. Once the dashboard and draft labels match your merchant review process, add a `pull_request` trigger and point either `path` at your generated product-page snapshots or `catalog` at a product export that AgentShelf should render before scanning.

For Codex or another coding agent, the most useful artifact is `agentshelf-tasks.jsonl`. Each row names the page, the task id, the reason, the likely file or page area, and an acceptance check. That lets an agent edit templates or catalog mappers without reverse-engineering a prose report.

## JSON Output
JSON reports include stable fields for dashboards and CI:

```json
{
  "page": {"title": "TrailBottle Pro 24oz", "source": "examples/sample_product_page.html"},
  "score": 100,
  "band": "strong",
  "checks": [],
  "commerce_signals": {
    "adapter_profile": {
      "requested": "auto",
      "detected": "shopify",
      "active": "shopify"
    },
    "variant_count": 2,
    "variants_with_price": 2,
    "variants_with_availability": 2,
    "option_names": ["Size", "Color"],
    "selling_plan_group_count": 1,
    "metafield_keys": ["custom.materials"],
    "has_return_policy_schema": true,
    "subscription": {"intent": true, "has_cadence": true, "has_cancellation": true},
    "bundle": {"intent": false},
    "regional_shipping": {"intent": true, "regions": ["US"], "has_timing": true}
  },
  "top_fixes": [],
  "agent_risks": []
}
```

## Agent Contract
`agentshelf agent-audit` is designed for tools like Codex or Claude Code. Each `agent_tasks` item includes:

- `id`: stable task id such as `add_product_jsonld` or `expose_variant_prices`
- `reason`: why the fix matters to a shopping agent
- `files_or_page_area`: where an implementation agent should look
- `acceptance_check`: how to know the fix is complete
- `priority`: `high` or `medium`

## GEO Skill For AI-Readable Commerce
`agentshelf geo-audit` is the first GEO Skill surface. It is built for merchants, consultants, and coding agents that need a structured plan for making commerce pages easier for generative engines and AI shopping systems to crawl, index, understand, cite, compare, and recommend.

The repo-local skill is intentionally small and operational:

- [skills/agentshelf-geo/SKILL.md](skills/agentshelf-geo/SKILL.md): the audit-task-edit-verify loop for Codex-style agents.
- [skills/agentshelf-geo/references/task-contract.md](skills/agentshelf-geo/references/task-contract.md): the JSONL task contract emitted by `geo-tasks`.

Example:

```bash
agentshelf geo-audit --url https://example.com/products/custom-teacup \
  --brand "Example Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --market US \
  --competitor Etsy \
  --persona "tea lovers" \
  --use-case "meaningful custom gifts" \
  --format both \
  --out reports/example-studio-geo
```

Agent workflow:

```bash
agentshelf geo-audit examples/artist_store_product.html \
  --brand "Moon Kiln Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --format json \
  --output reports/moon-kiln-geo-report.json

agentshelf geo-tasks reports/moon-kiln-geo-report.json \
  --output reports/moon-kiln-geo-tasks.jsonl

agentshelf validate-contract reports/moon-kiln-geo-report.json
agentshelf validate-contract reports/moon-kiln-geo-tasks.jsonl --contract agentshelf.geo_task.v0

# Codex reads reports/moon-kiln-geo-tasks.jsonl, edits the relevant page/template/schema,
# then reruns geo-audit and scan as verification gates.
```

The JSON report uses the `agentshelf.geo_audit.v0` contract and includes:

- `storeProfile`: normalized brand, domain, vertical, markets, products, personas, use cases, competitors, positioning, and claims.
- `pages`: extracted page facts including page type, title, meta description, H1, headings, canonical, links, images, schema types, Product data, FAQ data, claims, and crawl status.
- `categoryScores`: crawlability, indexability, structured data, content extractability, entity consistency, commerce attributes, trust, AI intent coverage, external authority, and GTM scores.
- `issues`: deterministic findings with severity, category, why it matters, recommendation, confidence, and page URL.
- `opportunities`: suggested collection pages, gift guides, FAQ assets, commission process pages, artist entity pages, and schema work.
- `promptPanel`: 100-150 deterministic prompts grouped across brand, category, gift, comparison, alternative, customization, trust, shipping, price/value, material/craft, buyer persona, and GTM intent buckets.
- `patchSuggestions`: opening answer blocks, FAQ blocks, Product schema skeletons, Organization schema skeletons, image alt text guidance, collection briefs, gift guide briefs, commission process pages, and artist factsheets.
- `geo-tasks`: JSONL implementation queue derived from patch suggestions and high-severity issues.

Published contract schemas:

- [schemas/agentshelf.geo_audit.v0.schema.json](schemas/agentshelf.geo_audit.v0.schema.json)
- [schemas/agentshelf.geo_task.v0.schema.json](schemas/agentshelf.geo_task.v0.schema.json)

`artist_store` and `creator_commerce` verticals add templates for one-of-one goods, handmade gifts, personalized objects, artist-made products, Chinese calligraphy, custom teacups, commission processes, and artist/studio entity factsheets. These are templates, not hard-coded business assumptions; pass `--category`, `--persona`, `--use-case`, and `--key-product` to steer the output.

Current GEO non-goals:

- no live ranking or visibility claims for ChatGPT Search, Google AI Overviews / AI Mode, Perplexity, Copilot, Claude, or Gemini
- no Search Console, Bing Webmaster Tools, or paid API integrations
- no arbitrary site-wide crawling
- no fake reviews, ratings, external authority, or platform-monitoring data

## Rule Philosophy
AgentShelf rules should be deterministic, explainable, and operator-actionable. Every failed check should point to a concrete storefront improvement, not just a score penalty.

AgentShelf treats Shopify/theme-style embedded product data as commerce evidence, not noise. Variant JSON can satisfy price, availability, and variant-readiness checks when it includes readable options, price, and stock context; incomplete variant JSON is reported as incomplete instead of being overtrusted.

Adapter profiles let production users choose deterministic extraction behavior:

- `auto`: detect storefront markers and choose a profile.
- `generic`: avoid storefront-specific assumptions.
- `shopify`: prioritize Shopify theme JSON, variants, selling plans, metafield-like keys, and policy snippets.
- `woocommerce`: prioritize WooCommerce variation forms and `data-product_variations`.
- `headless`: prioritize app-state JSON such as `__NEXT_DATA__`, `__NUXT__`, and initial state exports.

Profile-specific checks are applicable only when AgentShelf detects the relevant merchant intent. A normal single-SKU product page is not penalized for missing subscription or bundle details. A page that advertises `Subscribe and save`, a `bundle`, or destination-specific delivery is expected to expose enough terms for an agent to act safely.

Production-oriented profile rules currently cover:

- return policy schema: visible return promises should be backed by `hasMerchantReturnPolicy` metadata.
- subscription terms: subscription offers should expose cadence, price or discount, and cancellation terms.
- bundle components: kits and bundles should list included items plus bundle-level price and availability.
- regional shipping promises: destination-specific shipping copy should include the region plus timing or cost.

## Storefront Fixture Input
`render-fixtures` accepts:

- `--input-format agentshelf`: a JSON list or an object with a `products` list.
- `--input-format shopify`: Shopify product JSON as `{product: ...}`, `{products: [...]}`, or a product list.
- `--input-format woocommerce`: WooCommerce product CSV with parent variable products and variation rows.
- `--input-format headless`: generic catalog JSON using `products`, `items`, `nodes`, `edges`, `data.products`, or `catalog.products`.
- `--input-format auto`: `.csv` files are treated as WooCommerce; JSON is inspected for Shopify or headless markers before falling back to AgentShelf's normalized shape.

Each product should include enough purchase-decision data for an agent to answer price, stock, delivery, return, fit, and variant questions.

The manifest includes a validation block:

```json
{
  "validation": {
    "status": "warning",
    "warning_count": 2,
    "warnings": [
      {
        "severity": "warning",
        "product": "TrailBottle Pro 24oz",
        "field": "shipping",
        "message": "Product export did not include shipping policy text; fixture generation used generic shipping copy.",
        "action": "Add shipping or shippingPolicy to the export."
      }
    ]
  }
}
```

Use `--fail-on-warnings` in production CI so missing import data fails before fallback text creates overconfident snapshots.

Use `--tasks-output` to produce JSONL tasks for coding agents:

```json
{
  "source": "catalog-export.json",
  "input_format": "headless",
  "product": "TrailBottle Pro 24oz",
  "task": {
    "id": "fix_import_shipping",
    "reason": "Product export did not include shipping policy text; fixture generation used generic shipping copy.",
    "files_or_page_area": "Product export shipping or shippingPolicy field.",
    "acceptance_check": "Re-run `agentshelf render-fixtures ... --format json --fail-on-warnings` and confirm no validation warning remains for `shipping`.",
    "priority": "medium",
    "field": "shipping",
    "action": "Add shipping or shippingPolicy to the export."
  }
}
```

```json
{
  "products": [
    {
      "title": "TrailBottle Pro 24oz",
      "handle": "trailbottle-pro-24oz",
      "price": "39.00",
      "currency": "USD",
      "availability": "in_stock",
      "shipping": "Ships in 2 business days. Free US shipping on qualifying orders.",
      "returns": "30-day returns accepted for unused bottles.",
      "specs": {"Capacity": "24oz", "Material": "18/8 stainless steel"},
      "variants": [
        {"title": "24oz / Moss", "price": "39.00", "available": true, "options": {"Size": "24oz", "Color": "Moss"}}
      ]
    }
  ]
}
```

Generated fixtures are not a substitute for a rendered crawl when third-party apps inject reviews, subscriptions, or inventory after page load. They are for stable CI coverage from known product data and templates.

## Why This Is Not Just SEO/Schema Checking
AgentShelf checks whether a shopping agent can make a reliable purchase recommendation, not only whether a page has rich-result metadata. The benchmark fixtures cover agent-specific failures:

- variant-heavy pages where option choice matters
- embedded storefront JSON where price, stock, subscriptions, or metafields are not visible as plain copy
- profile-specific Shopify, WooCommerce, and headless storefront extraction contracts
- subscription bundles with missing cancellation, component, return-schema, or regional delivery details
- visible price or stock contradicting JSON-LD
- JS-rendered placeholder HTML that static scanners may overtrust
- pages with schema but no policy or fit answers
- pages with visible copy but no merchant-feed metadata

Run the benchmark set:

```bash
agentshelf scan benchmarks/fixtures --batch --format jsonl
python3 -m unittest tests.test_engine.BenchmarkTests
```

See [Profile Benchmarks](docs/PROFILE_BENCHMARKS.md) for the adapter-specific fixture contract.

## Current Non-Goals
- arbitrary site-wide crawling
- checkout automation
- Shopify app installation
- paid API integrations

## Local Development
```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
agentshelf scan examples/sample_product_page.html --format markdown --min-score 85
agentshelf agent-audit examples/weak_product_page.html --contract v1
agentshelf agent-tasks examples --batch
agentshelf geo-audit examples/artist_store_product.html --brand "Moon Kiln Studio" --category "custom handmade teacups" --vertical artist_store --format json --output /tmp/agentshelf-geo-report.json
agentshelf geo-tasks /tmp/agentshelf-geo-report.json --output /tmp/agentshelf-geo-tasks.jsonl
agentshelf validate-contract /tmp/agentshelf-geo-report.json
agentshelf validate-contract /tmp/agentshelf-geo-tasks.jsonl --contract agentshelf.geo_task.v0
agentshelf compare examples/js_product_raw.html examples/js_product_rendered.html --format json
agentshelf discover --sitemap https://example.com/sitemap.xml --limit 10
agentshelf render-fixtures examples/storefront-products.json --platform all --output-dir snapshots --manifest snapshots/manifest.json
agentshelf render-fixtures examples/shopify-products.json --input-format shopify --platform shopify --output-dir snapshots/shopify
agentshelf render-fixtures examples/woocommerce-products.csv --input-format woocommerce --platform woocommerce --output-dir snapshots/woocommerce --tasks-output snapshots/woocommerce/import-tasks.jsonl --fail-on-warnings
agentshelf render-fixtures examples/headless-catalog.json --input-format headless --platform headless --output-dir snapshots/headless
agentshelf scan examples/woocommerce_variable_product.html --profile woocommerce --format json
agentshelf scan examples/headless_product_state.html --profile headless --format json
agentshelf calibrate benchmarks/fixtures --batch --format markdown
agentshelf calibrate benchmarks/fixtures --batch --format json --output calibration-report.json
agentshelf dashboard calibration-report.json --format markdown
agentshelf draft-labels calibration-report.json --output draft-calibration-labels.json
agentshelf evaluate calibration-results.jsonl --labels examples/calibration-labels.json
python3 -m pip install -e ".[render]"  # optional rendered snapshots
```

## Example Files
- [Strong sample page](examples/sample_product_page.html)
- [Weak sample page](examples/weak_product_page.html)
- [Artist-store GEO sample page](examples/artist_store_product.html)
- [JS raw sample page](examples/js_product_raw.html)
- [JS rendered sample page](examples/js_product_rendered.html)
- [Shopify-style variant sample page](examples/shopify_variant_product.html)
- [WooCommerce variable product sample page](examples/woocommerce_variable_product.html)
- [Headless app-state sample page](examples/headless_product_state.html)
- [Storefront product export example](examples/storefront-products.json)
- [Shopify product export example](examples/shopify-products.json)
- [WooCommerce CSV export example](examples/woocommerce-products.csv)
- [Headless catalog export example](examples/headless-catalog.json)
- [Calibration labels example](examples/calibration-labels.json)
- [Draft calibration labels example](examples/draft-calibration-labels.json)
- [GEO audit schema](schemas/agentshelf.geo_audit.v0.schema.json)
- [GEO task schema](schemas/agentshelf.geo_task.v0.schema.json)
- [Sample report](outputs/sample_report.md)

## License
MIT
