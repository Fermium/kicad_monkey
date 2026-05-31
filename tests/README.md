# KiCad Monkey Tests

This suite follows the same hygiene model as `altium_monkey`:
- persistent file-backed fixtures resolve through `WN_TEST_CORPUS`
- the default public-repo corpus mirror lives under `tests/corpus`
- synthetic tests may stay local
- `input/`, `reference_output/`, and `output/` are the standard case buckets
- `output/` is transient

`toolz-tests/suites/kicad_monkey/tests/rack.py` is only a thin delegating wrapper to the installed `wn-rack`
CLI. It is not a local fork of the rack framework.

## Quick Start

```powershell
cd C:\ELI\wn-hw-workspace\toolz\kicad_monkey
$env:WN_TEST_SUITES_ROOT = "C:\ELI\wn-hw-workspace\toolz-tests"
uv sync --group dev
uv run python "$env:WN_TEST_SUITES_ROOT\suites\kicad_monkey\tests\rack.py" list
```

`tests/conftest.py` points `WN_TEST_CORPUS` at `tests/corpus` when no usable
external KiCad corpus is configured. Set `WN_TEST_CORPUS` only when you want to
override the package-local mirror.

Run a stratum:

```powershell
uv run python "$env:WN_TEST_SUITES_ROOT\suites\kicad_monkey\tests\rack.py" run L1_parsing
```

Regenerate the manifest-driven SVG review page:

```powershell
uv run python "$env:WN_TEST_SUITES_ROOT\suites\kicad_monkey\tests\generate_manifest_svg_review.py"
```

Generate the downstream KiCad CLI vs IR SVG comparison report:

```powershell
uv run python "$env:WN_TEST_SUITES_ROOT\suites\kicad_monkey\tests\generate_cli_svg_comparison.py"
```

## Strata

- `L0_foundation`: S-expression parsing and low-level syntax behavior
- `L1_parsing`: core parsing, round-trip, and shared-corpus readiness
- `L2_tools`: extraction, splitting, merging, indexing
- `L3_rendering`: SVG and 2D rendering
- `L4_applications`: higher-level workflows and external-tool validation

## Lanes

KiCad follows the shared lane model:
- `fast`: default smoke/structural lane
- `full`: broader routine-validation lane
- `strict`: heavier or stricter validation lane

The early KiCad strata are still converging on how much data each lane should cover, but the lane names are fixed now.

## Corpus Layout

Examples:
- `${WN_TEST_CORPUS}/kicad/common/board/input`
- `${WN_TEST_CORPUS}/kicad/common/footprints/input`
- `${WN_TEST_CORPUS}/kicad/common/reference_symbols/input`
- `${WN_TEST_CORPUS}/kicad/common/reference_schematics/input`
- `${WN_TEST_CORPUS}/kicad/common/reference_worksheets/input`
- `${WN_TEST_CORPUS}/kicad/pcb_roundtrip_features/input`

Keep new persistent assets under `tests/corpus/kicad/...` with the mirrored
corpus layout unless they are synthetic/local-only by design.
