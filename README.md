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
```

Options:

- `--batch`: allow directory or glob scanning
- `--format markdown|json|jsonl`: choose report format
- `--output <path>`: write output to a file
- `--min-score <0-100>`: return non-zero when any page scores below this value
- `--fail-on weak|not_ready`: return non-zero when any page is at or below the selected band

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

## Rule Philosophy
AgentShelf rules should be deterministic, explainable, and operator-actionable. Every failed check should point to a concrete storefront improvement, not just a score penalty.

## Current Non-Goals
- live URL crawling
- checkout automation
- Shopify app installation
- paid API integrations

## Local Development
```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
agentshelf scan examples/sample_product_page.html --format markdown --min-score 85
```

## Example Files
- [Strong sample page](examples/sample_product_page.html)
- [Weak sample page](examples/weak_product_page.html)
- [Sample report](outputs/sample_report.md)

## License
MIT
