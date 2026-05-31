# ADR-001: KiCad Module src/py Layout and Unified API Conventions

## Status

Accepted

## Date

2026-03-18

## Context

The KiCad module (`tools/kicad/`) currently has all 88 Python files at the
top level of the package. This is inconsistent with the other format modules
(Altium, EasyEDA, Eagle, OrCAD) which use `src/py/{package}/` layout.

Additionally, the API uses `from_file()`/`to_file()` patterns instead of
the unified constructor/`save()` pattern established by ADR-0043.

## Decision

### 1. Migrate to src/py layout

Move all Python source from `tools/kicad/*.py` to `tools/kicad/src/py/kicad/`.

This is a mechanical move — all internal imports use relative imports
(`from .kicad_pcb import ...`) which will continue to work unchanged.

**Migration strategy:**
- Phase 1: Create `tools/kicad/src/py/kicad/` and move files
- Phase 2: Update `tools/_source_roots.py` (already has KICAD paths stubbed)
- Phase 3: Update `tools/conftest.py` and any callers
- Phase 4: Verify all tests pass

**Risk mitigation:**
- The `__init__.py` with lazy imports continues to work as-is
- External callers use `from kicad import KiCadPcb` — path is resolved by
  `sys.path`, not by filesystem location
- Tests use `conftest.py` bootstrap — just need to ensure the new path
  is on `sys.path`

### 2. Apply unified API conventions (ADR-0043)

**Constructor = native format:**
```python
# Current
pcb = KiCadPcb.from_file("board.kicad_pcb")
sch = KiCadSchematic.from_file("design.kicad_sch")
lib = KiCadSymbolLib.from_file("library.kicad_sym")

# New (keep from_file as deprecated alias)
pcb = KiCadPcb("board.kicad_pcb")
sch = KiCadSchematic("design.kicad_sch")
lib = KiCadSymbolLib("library.kicad_sym")
```

**`save()` replaces `to_file()`:**
```python
# Current
pcb.to_file("output.kicad_pcb")
sch.to_file("output.kicad_sch")

# New (keep to_file as deprecated alias)
pcb.save("output.kicad_pcb")
sch.save("output.kicad_sch")
```

**Deprecation strategy:**
- `from_file()` remains as a classmethod alias for backward compatibility
- `to_file()` remains as an alias for `save()`
- No removal in this phase — just deprecation notes
- New code should use constructor + `save()`

### 3. Phase plan

| Phase | Scope | Risk |
|-------|-------|------|
| 1 | src/py directory move | Low — mechanical, relative imports unchanged |
| 2 | _source_roots + conftest | Low — path bootstrap update |
| 3 | Constructor pattern | Low — additive, from_file stays as alias |
| 4 | save() pattern | Low — additive, to_file stays as alias |
| 5 | Update callers in data_models | Low — change from_file → constructor |
| 6 | Verify full test suite | Gate — all tests must pass |

## Consequences

Positive:
- Consistent with Altium/EasyEDA/Eagle/OrCAD module structure
- Consistent API (ADR-0043) across all format modules
- Room for future `src/cpp` or `src/js` siblings
- No breaking changes — old API continues to work

Boundary:
- 88 files to move — large diff but mechanical
- Many callers across the codebase reference `from kicad import ...`
  which works via sys.path — no change needed for most callers
- Tests directory stays at `tools/kicad/tests/` (not moved)

## Source Anchors

- ADR-0043: `tools/data_models/docs/adr/ADR-0043-cross-module-unified-api-conventions.md`
- Altium ADR-001: `tools/altium/docs/adr/ADR_001_UNIFIED_API_CONVENTIONS.md`
