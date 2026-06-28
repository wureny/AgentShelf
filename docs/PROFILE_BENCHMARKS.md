# Profile Benchmarks

AgentShelf includes profile-specific benchmark fixtures so extraction behavior stays stable for production CI and coding-agent workflows.

## Fixtures

| Fixture | Expected profile | What it proves |
| --- | --- | --- |
| `shopify_profile_variant_page.html` | `shopify` | Shopify theme markers, embedded `ProductJson`, variants, selling plans, and metafield-like keys are detected as commerce evidence. |
| `woocommerce_profile_variable_page.html` | `woocommerce` | WooCommerce `data-product_variations` arrays expose variant price, stock, and option attributes. |
| `headless_profile_state_page.html` | `headless` | Headless app state such as `__NEXT_DATA__` exposes product variants even when data is not visible as plain text. |
| `profile_rule_gap_product.html` | `shopify` | Production-style subscription bundle gaps become actionable agent tasks for subscription terms, bundle contents, regional shipping, and return policy schema. |
| `newsletter_subscribe_single_sku_page.html` | `generic` | Real-dogfood-derived newsletter subscribe copy is not treated as a purchase subscription unless selling-plan or transactional subscription intent is present. |

## Contract

Each matching file in `benchmarks/expected/` locks:

- readiness band
- blocking issue ids
- top agent task ids
- requested, detected, and active adapter profile
- core commerce signal counts such as variants with price and availability
- applicable profile-rule failures for subscription, bundle, regional shipping, and return policy schema gaps

Run the benchmark contract:

```bash
python3 -m unittest tests.test_engine.BenchmarkTests
```

Or inspect the profile output directly:

```bash
agentshelf scan benchmarks/fixtures/woocommerce_profile_variable_page.html --profile auto --format json
agentshelf scan benchmarks/fixtures/headless_profile_state_page.html --profile auto --format json
```

These are curated fixtures, not empirical claims about ranking lift in ChatGPT, Google, Perplexity, or Claude shopping agents.
