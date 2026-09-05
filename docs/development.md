# Development

Work from the repository root with Python 3.11+ and uv. The package uses a `src/`
layout; `uv sync` installs it into the local environment so imports resolve correctly.

## Install the development environment

```bash
uv sync --locked --extra all --group dev --group demo
```

Install FFmpeg and ffprobe to exercise local media operations. Provider credentials
are unnecessary for the offline test suite.

## Run checks

```bash
uv run ruff check src tests scripts examples demo
uv run ruff format --check src tests scripts examples demo
uv run --group demo mypy src/video_context_pipeline demo
uv run --group demo python -m unittest discover -s tests
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

## Maintain the browser demo

The optional FastAPI/Uvicorn application lives in `demo/`, outside the library.
Install its dependency group alongside development tools:

```bash
uv sync --locked --extra all --group dev --group demo
uv run --locked --extra all --group dev --group demo python -m unittest discover -s tests -p 'test_demo*.py'
uv run --locked --group dev mkdocs build --strict
```

Keep the page, the [feature-coverage table](demo.md#feature-coverage), related guides,
and focused demo checks current in the same change whenever public capabilities or
configuration change. Do not add provider workarounds in the demo when a required
download or processing capability is missing from the library: stop and report the
gap. Run offline checks without provider keys; paid provider calls remain manual.
See the [demo guide](demo.md) for local execution and container validation.
