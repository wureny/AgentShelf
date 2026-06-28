# Releasing AgentShelf

Use this checklist before creating a public GitHub release or Marketplace-facing Action release.

## Pre-Tag Checks

```bash
agentshelf public-audit .
agentshelf release-check --expected-version 0.36.0
agentshelf release-notes --version 0.36.0 --output /tmp/agentshelf-v0.36.0-release.md
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m pip install -e . --no-build-isolation
python3 -m pip wheel . --no-deps --no-build-isolation -w /tmp/agentshelf-wheelhouse
```

`public-audit` verifies that public-facing files contain the adoption path, skill workflow, conservative non-claims, and no private local paths or unfinished markers.

`release-check` verifies the source tree has consistent package metadata, changelog coverage, release-facing README copy, Action metadata, pinned workflow examples, generated release-note coverage, public-audit status, bundled skill assets, and merchant onboarding templates.

`release-notes` generates a reviewable GitHub release draft from the matching `CHANGELOG.md` section. Review it before tagging; it intentionally keeps production posture conservative and avoids claims about external shopping-agent ranking lift.

## Tag And Release

Only create the tag after the checks pass and the release notes are reviewed:

```bash
git tag v0.36.0
git push origin v0.36.0
```

Then draft a GitHub release for `v0.36.0` using the generated release notes.

## Marketplace Posture

Publish the GitHub Action to Marketplace only after the tag exists and CI passes on the tagged commit. Marketplace copy should stay conservative:

- AgentShelf audits local product-page snapshots, generated fixtures, and catalog-derived HTML.
- It emits reports and coding-agent remediation tasks.
- It is not a hosted crawler, Shopify app, checkout automation system, or proven external-agent ranking lift tool.

## After Release

- Confirm the copyable Action example uses `wureny/AgentShelf@v0.36.0`.
- Confirm `agentshelf init-merchant-repo --install-ref v0.36.0` writes merchant workflows pinned to the released source.
