# Contributing

NanoTaste is still a research scaffold. Contributions should keep the repo
public-safe: no private taste files, private prompts, personal calibration
material, secrets, or strategy docs.

## Local Setup

Use Python 3.11 or newer.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

## Checks Before A PR

```bash
ruff check src tests
mypy
coverage run -m unittest discover -s tests
coverage report
python -m build
```

For wheel smoke testing:

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install dist/*.whl
nanotaste --help
nanotaste setup --yes --workspace /tmp/nanotaste-smoke --home /tmp/nanotaste-smoke-home
```

## Branches

Use one branch per sprint or logical change. This repo follows the staged flow
documented in `docs/REPOSITORY_RULES.md`: feature branches are reviewed before
they land in `testing`, and `testing` is promoted to `main` only by the owner.

## Security Expectations

- Do not add production dependencies without a reason and tests.
- Do not commit generated private experiment outputs.
- Do not use `pull_request_target` unless a security note explains why it is
  safe.
- Keep GitHub Actions pinned to full commit SHAs.
- Keep workflow permissions as narrow as possible.

## Style

Prefer small, explicit changes. NanoTaste is meant to be understandable before
it is clever.
