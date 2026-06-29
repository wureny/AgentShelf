# Store-Level GEO Audit

Store-level audit moves AgentShelf from single-page checking to a local snapshot bundle workflow. A snapshot bundle is a directory of merchant-owned HTML files produced by a storefront build, fixture renderer, scheduled snapshot job, or manual export.

## Snapshot Bundle

Example snapshot bundle:

```text
store-snapshot/
  home.html
  products/custom-calligraphy-teacup.html
  products/artist-made-cup.html
  collections/handmade-gifts.html
  collections/custom-calligraphy-gifts.html
  about.html
  commission.html
  faq.html
  shipping.html
  returns.html
```

Supported page groups include home, products, collections, about, FAQ, policies, articles or commission/process pages, and unknown pages.

## Store-Level Checks

These store-level checks are deterministic and local:

AgentShelf currently checks:

- Page type coverage: homepage, product page, collection page, about or artist page, FAQ, shipping, returns, and creator-commerce commission process pages.
- Entity consistency: configured brand or studio name visibility across titles, headings, schema, and page copy.
- Product attribute coverage: price, availability, material, dimensions, customization, lead time, shipping, returns, care, gift occasion, and packaging signals.
- Internal linking: homepage to products/collections/about, collection to products, product to FAQ/shipping/returns/commission, about to products or commission, and FAQ to next steps.
- Trust and policy coverage: FAQ, shipping, returns, contact, about/artist/studio, process, proof, portfolio, and gallery/process imagery.
- AI intent asset coverage: gift guides, comparison pages, commission process pages, artist entity factsheets, material/care guides, and shipping/lead-time FAQ.

## Command

```bash
agentshelf geo-run \
  --store-snapshot examples/fixtures/artist-store-before \
  --store-profile examples/profiles/artist-store.example.json \
  --vertical artist_store \
  --output-dir reports/artist-store \
  --format json
```

## Output Files

`geo-run --store-snapshot` writes:

- `store-report.json`: machine-readable store-level report using `agentshelf.store_geo_audit.v0`.
- `store-report.md`: merchant and GTM readable Markdown report.
- `store-report.html`: standalone HTML report with summary, scores, issues, actions, and limitations.
- `report.json`, `report.md`, `report.html`: agent-friendly aliases for the same store-level report artifacts.
- `geo-tasks.jsonl`: Codex-ready implementation task queue.
- `store-report-validation.json`: contract validation result for the JSON report.
- `geo-tasks-validation.json`: contract validation result for the task queue.
- `summary.json`: run summary for CI and automation.

## Recommended Workflow

1. Initialize or identify a merchant-owned snapshot bundle.
2. Run `agentshelf geo-run --store-snapshot`.
3. Review `report.md` with the merchant or GTM partner.
4. Give `geo-tasks.jsonl` to Codex or a developer.
5. Implement tasks using only merchant-confirmed facts.
6. Re-run `geo-run --store-snapshot` and compare store score, issue count, and task count.

This workflow is deterministic and local. It does not measure live AI provider visibility.
