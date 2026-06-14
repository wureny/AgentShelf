# Contributing

## Local Setup
```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
```

## Adding A Readiness Rule
Rules should be deterministic, explainable, and useful to storefront operators. A good rule includes:

- a stable check id
- a clear label
- a weight
- evidence when it passes
- a specific recommendation when it fails
- at least one fixture or unit test

## Fixtures
Use sanitized product-page snapshots only. Do not commit customer data, credentials, order information, or private analytics snippets.

