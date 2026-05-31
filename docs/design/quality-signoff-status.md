# Quality Signoff Status

Status: public-release bootstrap audit
Last updated: 2026-05-31

## Passing Gates

- `L99_signoff` checks date-version metadata, changelog coverage, public
  package metadata, sdist boundaries, and the promoted public API contract.
- `L99_signoff` checks design-doc entry points, the major-interface manifest,
  promoted public class design sections, and Rack test ownership links.
- `L99_signoff` runs `ruff check` across `src/py/kicad_monkey`, L99 signoff
  tests, the promoted API contract test, and the corpus packaging script.
- `L99_signoff` runs package-wide pyright against `src/py/kicad_monkey` through
  `pyrightconfig.json`.
- `tests/corpus/kicad.zip` is the public test-corpus transport. The loose
  corpus mirror is ignored locally and extracted on demand by test helpers.
- CI prepares the corpus archive, runs Rack L0 and L99, builds the package,
  runs `twine check`, and verifies installed-package imports.

## Active Quality Ratchet

Ruff and pyright are installed in the test extra and remain release-signoff
tools. The source package is now ruff-clean and pyright-clean, and both are
hard-gated by L99.

Known remaining package-wide ruff work is in older non-L99 tests and any future
developer-only scripts. Package pyright is at zero diagnostics under
`typeCheckingMode = "standard"` with `reportUnsupportedDunderAll` suppressed
for the intentionally broad lazy package export table.

Current local package pyright run:

```text
uv run --extra test pyright
-> 0 errors, 0 warnings, 0 informations
```

Before the first public push:

1. Keep `src/py/kicad_monkey` package-wide ruff and pyright clean.
2. Keep package pyright at zero while downstream consumers move to the public
   API surface.
3. Add conformance contracts under `docs/contracts/` for any stable JSON,
   corpus manifest, or cruncher-facing output that leaves the package.
4. Use the first `kicad-cruncher` integration pass to decide which provisional
   `__all__` exports graduate into the promoted public contract.
