# AgentShelf

Open-source product page audits for AI shopping agents.

AgentShelf checks whether product pages expose the signals AI shopping agents need for discovery, ranking, and purchase recommendations: product title, price, availability, shipping, returns, specs, reviews, FAQ, and Product structured data.

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

Emit a JSON contract for a coding agent:

```bash
agentshelf agent-audit examples/weak_product_page.html --contract v1
```

Fetch a raw HTML snapshot for later audit:

```bash
agentshelf snapshot https://example.com/product --output snapshots/product.html
```

## Example Output
```text
# AgentShelf Report: TrailBottle Pro 24oz

## Summary
- Score: 100/100
- Readiness band: strong
- Passed checks: 9/9
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
agentshelf snapshot <url> --output <path>
```

Options:

- `--batch`: allow directory or glob scanning
- `--format markdown|json|jsonl`: choose report format
- `--output <path>`: write output to a file
- `--min-score <0-100>`: return non-zero when any page scores below this value
- `--fail-on weak|not_ready`: return non-zero when any page is at or below the selected band

`agent-audit` emits JSON with stable fields for coding agents: `target`, `score`, `band`, `blocking_issues`, `agent_tasks`, `evidence`, `next_actions`, `confidence`, and `warnings`.

`snapshot` fetches raw HTML with the standard library. It does not execute JavaScript. Pages that appear JS-rendered are flagged with `dynamic_rendering_likely` during audit.

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
          format: markdown
          output: agentshelf-report.md
```

## JSON Output
JSON reports include stable fields for dashboards and CI:

```json
{
  "page": {"title": "TrailBottle Pro 24oz", "source": "examples/sample_product_page.html"},
  "score": 100,
  "band": "strong",
  "checks": [],
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

## Why This Is Not Just SEO/Schema Checking
AgentShelf checks whether a shopping agent can make a reliable purchase recommendation, not only whether a page has rich-result metadata. The benchmark fixtures cover agent-specific failures:

- variant-heavy pages where option choice matters
- visible price or stock contradicting JSON-LD
- JS-rendered placeholder HTML that static scanners may overtrust
- pages with schema but no policy or fit answers
- pages with visible copy but no merchant-feed metadata

Run the benchmark set:

```bash
agentshelf scan benchmarks/fixtures --batch --format jsonl
```

## Current Non-Goals
- JavaScript-rendered crawling
- checkout automation
- Shopify app installation
- paid API integrations

## Local Development
```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
agentshelf scan examples/sample_product_page.html --format markdown --min-score 85
agentshelf agent-audit examples/weak_product_page.html --contract v1
```

## Example Files
- [Strong sample page](examples/sample_product_page.html)
- [Weak sample page](examples/weak_product_page.html)
- [Sample report](outputs/sample_report.md)

## License
MIT
