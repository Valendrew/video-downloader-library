# Project requirements

- Build a modular Python library. Components must work independently or through the optional pipeline.
- Support Python 3.11 and newer. Use uv for dependencies, locking, tests and builds.
- Keep a src layout, typed public interfaces and optional provider dependencies.
- Require explicit applicable settings. Reject invalid configuration instead of silently substituting values.
- Every requested pipeline component must succeed. On failure, cancel pending work where possible, clean up owned temporary files and raise a clear error.
- Keep public output formats predictable. Separate user-facing outputs from model input formatting.
- Keep blocking operations off the event loop. Preserve caller-owned files.
- Log factual operational information using standard Python logging. Never log secrets, private content, cost estimates or inferred usage.
- Validate changed provider parameters through limited direct API checks. Keep paid calls out of routine CI and document anything not verified.
- Run focused tests for changed behavior. Keep offline tests compatible with supported Python versions.
- Update concise documentation and examples whenever public behavior or configuration changes.
- Keep the demo page and its feature-coverage table in docs/demo.md current whenever public capabilities or configuration change; update related documentation and focused demo checks in the same change. Keep demo concerns outside the library. Stop and report missing reference-required download or processing capabilities instead of implementing provider workarounds in the demo.
- Treat external projects as private compatibility references. Never commit their code or modify them unless explicitly requested.
- Do not commit, push, publish or deploy unless requested.
