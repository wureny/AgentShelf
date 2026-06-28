# Releasing AgentShelf

Use this checklist before creating a public GitHub release or Marketplace-facing Action release.

## Pre-Tag Checks

```bash
agentshelf release-check --expected-version 0.31.0
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m pip install -e . --no-build-isolation
python3 -m pip wheel . --no-deps --no-build-isolation -w /tmp/agentshelf-wheelhouse
```

`release-check` verifies the source tree has consistent package metadata, changelog coverage, release-facing README copy, Action metadata, pinned workflow examples, bundled skill assets, and merchant onboarding templates.

## Tag And Release

Only create the tag after the checks pass and the release notes are reviewed:

```bash
git tag v0.31.0
git push origin v0.31.0
```

Then draft a GitHub release for `v0.31.0` using the matching `CHANGELOG.md` section.

## Marketplace Posture

Publish the GitHub Action to Marketplace only after the tag exists and CI passes on the tagged commit. Marketplace copy should stay conservative:

- AgentShelf audits local product-page snapshots, generated fixtures, and catalog-derived HTML.
- It emits reports and coding-agent remediation tasks.
- It is not a hosted crawler, Shopify app, checkout automation system, or proven external-agent ranking lift tool.

## After Release

- Confirm the copyable Action example uses `wureny/AgentShelf@v0.31.0`.
- Confirm `agentshelf init-merchant-repo` works from the released source.
- If the merchant template still installs from `@main`, update it in the next patch release after the tag is available.
