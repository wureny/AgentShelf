# AgentShelf

Open-source product page audits for AI shopping agents.

AgentShelf checks whether product pages expose the signals AI shopping agents need for discovery, ranking, and purchase recommendations: product title, price, availability, shipping, returns, specs, reviews, FAQ, and Product structured data.

It also reads storefront implementation signals that matter in real Shopify/DTC pages: embedded product JSON, variant arrays, selling plan groups, metafield-like keys, and policy snippets.

## Who It Helps
- Shopify and DTC operators preparing storefronts for agentic commerce
- AI commerce consultants doing quick storefront readiness audits
- indie commerce founders validating whether product pages are machine-readable

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

## Example Output
```text
# AgentShelf Report: TrailBottle Pro 24oz

## Summary
- Score: 93/100
- Readiness band: strong
- Passed checks: 12/13
- Dimension scores: discoverability=100, offer_clarity=100, policy_clarity=100, agent_actionability=75
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
agentshelf compare <raw.html> <rendered.html> [options]
agentshelf diff <baseline-results.jsonl> <current-results.jsonl> [options]
agentshelf audit-run <file-or-dir-or-glob> [options]
agentshelf discover --site <url> [options]
agentshelf discover --sitemap <url> [options]
agentshelf snapshot <url> --output <path> [--rendered]
agentshelf snapshot --url-file <urls.txt> --output-dir <dir> [--manifest <path>]
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

`snapshot` fetches raw HTML with the standard library by default. Use `--rendered` for a Playwright-backed single-page capture when product data is injected by JavaScript. Rendered mode is optional so the base CLI stays lightweight.

`compare` shows whether rendered capture unlocks agent-readiness signals that raw HTML misses. It reports score deltas, dimension deltas, newly visible evidence, regressions, and an agent recommendation.

`diff` compares two `agentshelf scan --format json|jsonl` outputs. It reports page-set regressions, improvements, new or resolved blocking issues, catalog additions/removals, and the next remediation tasks an agent should pick up.

`audit-run` is the scheduled-job wrapper around `scan` and `diff`. It writes `<history-dir>/current-results.jsonl`, rotates the previous run into `<history-dir>/previous-results.jsonl`, archives each run as `results-<timestamp>.jsonl`, writes an `audit-diff.md` report, and can emit `agent-tasks` JSONL in the same pass.

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
```

On the first run, `audit-run` creates a baseline. On later runs, it automatically writes `.agentshelf/runs/audit-diff.md` from the last saved result set. In CI, upload `.agentshelf/runs/audit-diff.md` and `agentshelf-tasks.jsonl` as review artifacts so humans see the merchant-level regression summary and agents get machine-actionable fixes.

## GitHub Action
Use AgentShelf as a PR gate for product-page snapshots, generated storefront HTML, or theme fixture output.

```yaml
name: AgentShelf

on:
  pull_request:

jobs:
  audit-commerce-pages:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: wureny/AgentShelf@main
        with:
          path: "examples/*.html"
          min-score: "70"
          fail-on: not_ready
          format: sarif
          output: agentshelf-results.sarif
          profile: auto
```

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
    "metafield_keys": ["custom.materials"]
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

## Rule Philosophy
AgentShelf rules should be deterministic, explainable, and operator-actionable. Every failed check should point to a concrete storefront improvement, not just a score penalty.

AgentShelf treats Shopify/theme-style embedded product data as commerce evidence, not noise. Variant JSON can satisfy price, availability, and variant-readiness checks when it includes readable options, price, and stock context; incomplete variant JSON is reported as incomplete instead of being overtrusted.

Adapter profiles let production users choose deterministic extraction behavior:

- `auto`: detect storefront markers and choose a profile.
- `generic`: avoid storefront-specific assumptions.
- `shopify`: prioritize Shopify theme JSON, variants, selling plans, metafield-like keys, and policy snippets.
- `woocommerce`: prioritize WooCommerce variation forms and `data-product_variations`.
- `headless`: prioritize app-state JSON such as `__NEXT_DATA__`, `__NUXT__`, and initial state exports.

## Why This Is Not Just SEO/Schema Checking
AgentShelf checks whether a shopping agent can make a reliable purchase recommendation, not only whether a page has rich-result metadata. The benchmark fixtures cover agent-specific failures:

- variant-heavy pages where option choice matters
- embedded storefront JSON where price, stock, subscriptions, or metafields are not visible as plain copy
- visible price or stock contradicting JSON-LD
- JS-rendered placeholder HTML that static scanners may overtrust
- pages with schema but no policy or fit answers
- pages with visible copy but no merchant-feed metadata

Run the benchmark set:

```bash
agentshelf scan benchmarks/fixtures --batch --format jsonl
```

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
agentshelf compare examples/js_product_raw.html examples/js_product_rendered.html --format json
agentshelf discover --sitemap https://example.com/sitemap.xml --limit 10
agentshelf scan examples/woocommerce_variable_product.html --profile woocommerce --format json
agentshelf scan examples/headless_product_state.html --profile headless --format json
python3 -m pip install -e ".[render]"  # optional rendered snapshots
```

## Example Files
- [Strong sample page](examples/sample_product_page.html)
- [Weak sample page](examples/weak_product_page.html)
- [JS raw sample page](examples/js_product_raw.html)
- [JS rendered sample page](examples/js_product_rendered.html)
- [Shopify-style variant sample page](examples/shopify_variant_product.html)
- [WooCommerce variable product sample page](examples/woocommerce_variable_product.html)
- [Headless app-state sample page](examples/headless_product_state.html)
- [Sample report](outputs/sample_report.md)

## License
MIT
