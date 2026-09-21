# Contributing

## Development baseline

Use Python 3.14.2 or newer and the Home Assistant version pinned in
`pyproject.toml`. Install dependencies with `uv sync --frozen`. Runtime tests
must run on Linux or WSL.

Before submitting a change, run:

```shell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q --cov=custom_components.netbird --cov-report=term-missing --cov-fail-under=95
```

CI also runs hassfest and HACS validation. After tests generate artifacts, it
scans the workspace with Gitleaks. These hosted checks are separate from local
Home Assistant tests and must pass before the MVP quality gate is complete.

Add focused tests for changed behavior. Keep fixtures minimal, anonymized, and
representative of documented or observed API responses.

## Scope and safety

Preserve the ConfigEntry lifecycle, async I/O, typed runtime data, translation,
and coordinator patterns selected by the integration specification. Do not add
entity platforms, services, API calls, or placeholders outside the active work
item.

Never commit credentials, cookies, private URLs, raw diagnostics, or production
API responses. Live tests must be opt-in and use a dedicated service-user token
from the environment. Logs, fixtures, exceptions, and diagnostics must redact
authentication data.

## Versioning

The project uses Semantic Versioning. Development starts at `0.x`; breaking
changes may occur between minor versions until `1.0.0`. The version in
`custom_components/netbird/manifest.json` is the integration release version.
Releases and tags are created only after the matching quality gate passes.
