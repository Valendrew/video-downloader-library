# Working on the docs

The site uses [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/),
with local system fonts, warm surfaces, teal navigation, and a coral interaction accent.
Light and dark themes share the same content and navigation.

## Preview locally

From the repository root:

```bash
uv sync --locked --group dev
uv run mkdocs serve
```

Open the local address printed by MkDocs, usually `http://127.0.0.1:8000`.
Edits to Markdown and styles reload automatically.

## Build and validate

```bash
uv run mkdocs build --strict
```

The generated site is written to `site/`. Strict mode fails on warnings, including
broken documentation links. Preview changes at desktop and mobile widths and check
both color themes, navigation, tables, and code blocks.

## Where to edit

| Location | Purpose |
| --- | --- |
| `mkdocs.yml` | Navigation, theme, search, Markdown extensions |
| `docs/stylesheets/extra.css` | Colors, typography, cards, and surfaces |
| `docs/components/` | Task-oriented usage guides |
| `docs/providers/` | Service setup, supported behavior, upstream links |
| `docs/schemas.md` | Request fields and result shapes |

Explain the purpose before the signature. Put calls in fenced Python blocks, describe
fields in tables, and state what an example needs before it can run. Link provider
features to upstream documentation while distinguishing them from this library's API.

## Deployment

The repository's **Deploy documentation** GitHub Actions workflow is manually triggered.
A local build does not publish the site. Internal execution notes and the implementation
plan are excluded from the public navigation and build.
