# Development

Work from the repository root with Python 3.11+ and uv. The package uses a `src/`
layout; `uv sync` installs it into the local environment so imports resolve correctly.

## Install the development environment

```bash
uv sync --locked --extra all --group dev
```

Install FFmpeg and ffprobe to exercise local media operations. Provider credentials
are unnecessary for the offline test suite.

## Run checks

```bash
uv run ruff check src tests scripts examples
uv run ruff format --check src tests scripts examples
uv run mypy src/video_context_pipeline
uv run python -m unittest discover -s tests
uv run mkdocs build --strict
```

For a focused check, select a test module:

```bash
uv run python -m unittest discover -s tests -p 'test_core.py'
```

CI runs the offline checks on Python 3.11 and 3.14. Live provider checks are manual;
see [provider validation](provider-validation.md) for recorded coverage and gaps.

## Build the package

```bash
uv build
```

The wheel and source archive are written to `dist/`. Review archive contents and
[dependency provenance](dependencies.md) before any publication.

## Change dependencies

Use `uv add` for dependency changes and commit the resulting `pyproject.toml` and
`uv.lock` together when preparing a change. Provider dependencies belong in optional
extras. Keep the base package importable without them.

## Project boundaries

Components must also work independently of `Pipeline`. Keep public interfaces typed,
settings explicit, blocking work off the event loop, and caller-owned files intact.
The projects under `external/` are private compatibility references; do not copy their
source into this package. See [compatibility](compatibility.md) for integration boundaries.
