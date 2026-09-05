# 04: Documentation, examples and release workflows

## Plan mapping
Approved plan documentation, packaging/release, environment variables and compatibility.
## Objective
Document the actual usable public API in short readable pages and prepare (not execute) CI, versioned GitHub release and Pages workflows.
## Prerequisites and required inputs
Verified [core](01-core.md#outcome), [media](02-media.md#outcome), and [API providers](03-providers.md#outcome). Read actual signatures; docs must not invent APIs.
## Expected result
Small MkDocs site and runnable import/configuration examples. Installation uses the repository checkout. No PyPI publication or actual deployment.
## Owned paths and exclusions
Own README.md, LICENSE, mkdocs.yml, .env.example, examples/, .github/workflows/, docs/index.md, docs/install.md, docs/configuration.md, docs/schemas.md, docs/errors-and-logging.md, docs/compatibility.md, docs/components/ and this record. Do not edit docs/implementation-plan.md, docs/provider-validation.md, other execution artifacts, .env, src/, pyproject.toml, uv.lock or external/.
## Interfaces and constraints
Use actual public config names and required args. All model/FPS/resolution/threshold/retry/timeout settings explicit in examples, with comments identifying caller choices not hidden defaults. Discovery by video/audio/text input/output links to one canonical page per component. Document allowed URL platforms and local/internal artifact distinction; audio transcription accepts public video URL, not any local audio file. Document independent components vs strict pipeline (all requested stages must succeed); text/segments/event schemas and formatting provenance; approximate vs deterministic times; env loader vs Python settings vs Gemini API resolution. Supadata sole generate no language/auto/fallback; Gemini visual only with optional independent transcript; requested outputs all returned. Explain codecs/formats/ffmpeg/JS-runtime requirements and MP3 conditional conversion as policy (not error fallback). Operational timeouts may fail workflow; no max output caps/stops/count caps. Logs factual, no raw data or dollar estimates. Clearly mark live validation gaps from provider-validation.md. Copy no code from unlicensed projects.
GitHub CI runs offline unittest suite under supported Python 3.11 and current stable (3.14), uv sync locked extras/dev, build package and strict MkDocs. Workflows should be manual/release tag triggered without auto publish on ordinary pushes: release on v* tags validates tag vs project.version, uv build, creates checksums and uploads to GitHub release; Pages explicit workflow_dispatch using official configure/upload/deploy Pages actions. Do not assume repo Pages enabled. MIT copyright Video Context Pipeline contributors. Record dependencies and provenance without claiming legal conclusions. Small docs preferred, no unnecessary jargon. Build MkDocs with explicit nav excluding internal execution artifacts using exclude_docs or appropriate known version config.
## Acceptance criteria
Docs explain all required parameters beside component they control. Examples compile and offline config construction works without network using fake keys. Docs site builds with strict links. Workflows prepare reproducible release artifacts; no release/publication performed.
## Focused checks and expected evidence
Compile examples; construct configs without API calls; strict MkDocs build. Do not rerun full suite/build owned by orchestrator unless asked. Report changed paths and commands.
## Outcome
Completed documentation, offline examples, and prepared release/Pages workflows.

Changed paths: `README.md`, `LICENSE`, `mkdocs.yml`, `.env.example`, `examples/`,
`.github/workflows/`, `docs/{index,install,configuration,schemas,errors-and-logging,compatibility}.md`,
and `docs/components/`.

The CI workflow installs ffmpeg and verifies formatting, lint, package types, the
offline suite, package build, and strict documentation build on Python 3.11 and 3.14.
The site documents the verified public contracts, all environment-loader fields,
configuration choices, component input/output boundaries, timing and formatting
provenance, local artifact ownership, compatibility requirements, operational limits,
and recorded provider-validation gaps. Publication and Pages deployment are
prepared only; no release or deployment was performed.
## Verification
Focused checks passed:

- `.validation/check-env/bin/python -m py_compile examples/offline_configuration.py examples/pipeline_request.py`
- `PYTHONPATH=src .validation/check-env/bin/python examples/offline_configuration.py`
- `PYTHONPATH=src .validation/check-env/bin/python examples/pipeline_request.py`
- `.validation/check-env/bin/python -m mkdocs build --strict`
- `.venv/bin/ruff check examples`
- `.venv/bin/ruff format --check examples`

Inspected the scoped untracked-file diff statistics. No live provider calls were made.
## Blockers
None. Core, media and providers verified.
## Consequential decisions
Upgrade trigger: release and deployment permission configuration plus public API documentation.
Evidence: workflows must publish only on explicit release/tag or manual deployment and examples must match verified component contracts.

Additional verified inputs: docs/dependencies.md is orchestrator-owned; link it in navigation and do not edit. pyproject.toml now has mkdocs/mypy/ruff dev group and HTTP/download extras, uv.lock exists. Actual repository is Valendrew/video-downloader-library. Tools: .validation/tooling/bin/uv; .validation/check-env/bin/python includes mkdocs. Operational Gemini/Supadata settings include extra required timeout/retry/poll env variables: read config.load_environment and document ALL of them, not just the initial short plan table. The full library passes mypy.
