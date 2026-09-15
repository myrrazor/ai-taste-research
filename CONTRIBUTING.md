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
python3 -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install dist/*.whl
nanotaste --help
nanotaste setup --yes --workspace /tmp/nanotaste-smoke --home /tmp/nanotaste-smoke-home
nanotaste seed --text "Prefer concrete drafts." --workspace /tmp/nanotaste-smoke --home /tmp/nanotaste-smoke-home
nanotaste catalog --workspace /tmp/nanotaste-smoke --home /tmp/nanotaste-smoke-home
```

The local studio is `nanotaste serve --no-tick`. Do not treat `website/` as
that app; it is the static marketing site.

## Branches

Use one branch per sprint or logical change. Open a pull request against `main`.

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
