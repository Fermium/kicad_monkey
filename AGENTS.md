# KiCad Monkey Working Rules

- canonical member folder: `C:\ELI\wn-hw-workspace\toolz\kicad_monkey`
- distribution name: `kicad-monkey`
- Python import name: `kicad_monkey`
- run member sync from this folder, not the workspace root
- private tests live in `toolz-tests\suites\kicad_monkey\tests`
- use `WN_TEST_SUITES_ROOT` to find the external private Rack suite
- use `WN_TEST_CORPUS` for persistent file-backed fixtures
- future package-local tests should stay small and generic; private/corpus suites belong in `toolz-tests`
- persistent cases should follow `input/`, `reference_output/`, `output/`
- `output/` is transient and belongs in local temp/output paths, not the shared corpus
- keep `kicad_monkey` focused on parser/source-model, round-trip, basic 2D rendering, and close-to-format utilities
- keep higher-level PCB report workflows in sibling cruncher packages such as `pcb_cruncher`
- record deferred failures in `DEFERRED_FAILURES.toml`
- record persistent shared assets in `toolz-tests/manifests/test-assets.json`
- record helper scripts/tools in `HELPER_TOOL_INVENTORY.toml`
