# Public Release Audit

Use this checklist before tagging AgentShelf, drafting a GitHub release, or publishing the Action to GitHub Marketplace.

AgentShelf should be easy for three audiences to adopt without private context:

- Merchant operators who want product-page and GEO evidence from local snapshots or catalog exports.
- Coding agents that need deterministic tasks, acceptance checks, and verification commands.
- Maintainers who need conservative release copy, green checks, and no accidental ranking-lift claims.

## Required Checks

```bash
agentshelf public-audit .
agentshelf release-check --expected-version 0.36.0
agentshelf release-notes --version 0.36.0 --output docs/releases/v0.36.0.md
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m pip install -e . --no-build-isolation
python3 -m pip wheel . --no-deps --no-build-isolation -w /tmp/agentshelf-wheelhouse
```

`public-audit` checks release-facing files for required public adoption paths, Codex skill guidance, conservative non-claims, private local path leaks such as developer home directories or automation workspace names, and tracked generated files.

`release-check` validates version consistency, changelog coverage, pinned Action examples, generated release notes, Action metadata, bundled skill assets, and merchant onboarding templates.

`release-notes` generates review copy only. It does not publish a tag, release, or Marketplace listing.

The committed `docs/releases/v0.36.0.md` file must match the generated release notes before `release-check` passes.

## What Must Be True

- README explains merchant use, coding-agent use, production posture, and limitations near the top.
- The bundled `agentshelf-geo` skill documents the audit-task-edit-verify loop.
- `agentshelf init-merchant-repo` and `agentshelf adoption-check` provide a practical merchant repo adoption path.
- GitHub Action examples use a pinned release tag for public docs, not `@main`, after the tag exists.
- Merchant repos can run `agentshelf init-merchant-repo --install-ref <tag>` so generated workflows install AgentShelf from a reviewed release tag.
- Failure output gives humans a remediation path and leaves machine-readable artifacts for agents.
- No release-facing docs contain local machine paths, private workspace names, unfinished work markers, or raw third-party HTML.
- Release copy says AgentShelf is deterministic and local-first; it must not claim proven ChatGPT, Google, Perplexity, Claude, Gemini, Bing, ranking, conversion, or revenue lift.

## Marketplace Posture

Do not publish the Action to Marketplace until:

- `agentshelf public-audit .` passes.
- `agentshelf release-check --expected-version <version>` passes.
- CI is green on the exact commit to tag.
- A GitHub release tag exists and README examples point to that tag.
- The Marketplace description stays conservative: local product-page and GEO audits, generated artifacts, and coding-agent remediation tasks.

Do not claim empirical external-agent visibility lift unless a separate benchmark or customer study supports it.

## If The Audit Fails

Fix public-facing files first, then rerun:

```bash
agentshelf public-audit . --format json
```

Common fixes:

- Replace private local paths with relative commands or generic `/tmp` examples.
- Move internal automation notes out of public docs.
- Add missing install, skill export, adoption-check, and release-check commands.
- Remove claims that sound like guaranteed GEO ranking or sales lift.
- Keep merchant-confirmed fact boundaries explicit: Do not fabricate reviews, ratings, press, stock, shipping promises, return policies, or external authority.
