# Release Process

NanoTaste is not ready for public visibility or package publication. RC0 prepares
`0.1.0` as a private, pre-alpha local experiment scaffold and stops before any tag,
GitHub release, PyPI upload, deployment, or visibility change.

## Current Status

- License: MIT.
- Package metadata supports Python 3.11 and newer.
- CI builds one canonical wheel and one verified sdist on Linux/Python 3.14, then
  installs the exact wheel bytes in all six supported environments.
- CI does not publish artifacts.
- No release credentials should exist in pull-request workflows.
- Local and historical model-review output is advisory; hosted evidence remains absent
  until it is bound to the exact release commit.
- The permitted product and research claims are locked in `docs/RC0_CLAIMS.md`.

## Release Preconditions

Before publishing a release:

- all repository rules in `docs/REPOSITORY_RULES.md` are enabled;
- CI and CodeQL are green on the release branch;
- the changelog has a dated version section;
- the package version in `pyproject.toml` matches the tag;
- the built wheel was installed and smoke-tested from the artifact;
- the sdist state is `SDIST_VERIFIED` and its clean install succeeds;
- no private taste files, prompts, calibration notes, or strategy docs are in
  the release tree.

## Build

Use a clean Python 3.14 environment:

```bash
python -m pip install -r requirements-dev.txt
python -m build
PYTHONPATH=src python -m nanotaste.rc0.artifacts create \
  --dist-dir dist --source-sha "$(git rev-parse HEAD)" \
  --output dist/ARTIFACT_MANIFEST.json
PYTHONPATH=src python -m nanotaste.rc0.artifacts verify \
  --dist-dir dist --manifest dist/ARTIFACT_MANIFEST.json
```

Inspect artifacts:

```bash
python -m venv .venv-release-smoke
. .venv-release-smoke/bin/activate
python -m pip install dist/*.whl
nanotaste --help
```

## Publishing

When releases begin, prefer trusted publishing or OIDC-based publishing over
long-lived package tokens. If GitHub artifact attestations are available for the
repository, enable them before public release.

Release publishing must run only from trusted branches/tags. It must not run on
untrusted fork pull requests, and it must not use `pull_request_target`.

## Tagging

Tags should be created only after the release commit is reviewed:

```bash
git tag -s vX.Y.Z
git push origin vX.Y.Z
```

RC0 does not create a tag. A later release authorization must choose and document the
tag-signing policy before any tag is created.

## Rollback

If a release exposes private data or has a security issue:

- remove or yank the package from the package index when possible;
- publish a security advisory if user action is needed;
- rotate any affected credentials;
- add a postmortem note to the release issue.
