# ADR-002: KiCad Test Corpus Layout And Lane Model

## Status

Accepted

## Context

The old KiCad test setup mixed repo-local `tests/test_cases/...` fixtures with
broader corpus data. The current package needs a corpus layout that works both
from the checked-in archive and from an externally supplied corpus root.

KiCad also needs a lane model so smoke runs and heavier validations are
predictable.

## Decision

KiCad persistent file-backed fixtures resolve from `WN_TEST_CORPUS`.

Shared corpus layout rule:
- `kicad/common/...` for reusable shared fixtures
- `kicad/<topic>/...` for focused feature or stratum assets

Preferred case shape:
- `input/`
- `reference_output/`
- `output/`

`output/` is transient and should remain local or temp-backed, not authoritative shared corpus data.
Visual tests should write generated review artifacts under the owning case's
`output/<domain>/` folder, such as `projects/<name>/output/board_svg/` or
`pcb_foundation/<case>/output/board_svg/`. This keeps human-review outputs next
to the corpus inputs and references while still keeping them out of version
control.

Real-world project domain tagging is file-role based. Assembly-procedure
projects with names ending in `_assembly` are promoted for schematic
rendering/IR and project parsing, but their `.kicad_pcb` files are intentionally
empty or header-only. They should not be expected to participate in `board_svg`
or PCB SVG review lanes unless a real board file is later added.

Lane model:
- `fast` is the default lane
- `full` is the broader routine-validation lane
- `strict` is the heavier or stricter validation lane

## Consequences

- Moving the shared KiCad corpus should require changing only `WN_TEST_CORPUS`.
- New persistent fixtures should not be introduced under repo-local `tests/test_cases/...` unless they are synthetic/local-only by design.
- Focused feature boards should not pollute the broad common board corpus when that would widen unrelated parser-equivalency sweeps.
- Future strata should record durable corpus ownership in package-local
  manifests or design docs before release.
