# Removing `preserve_embedded_data_formatting` — empirical case

**Date:** 2026-05-09
**Slice:** Phase C-B follow-on
**Outcome:** Removed the function and rewired its 4 callsites in `kicad_filter_core.py` to plain `format_kicad_sexp(...) + ensure-trailing-newline`. Removal is a **net bug fix**, not just a cleanup.

## Background

`preserve_embedded_data_formatting` was a regex post-processor used by `kicad__fp_filter`, `kicad__sym_filter`, and `kicad__sch_filter` to "preserve the original formatting for sections containing base64 data." It worked by:

1. Calling `format_kicad_sexp(filtered_s_expr)` to format the filtered tree.
2. Locating each `(embedded_files ...)` and `(image ...)` block in the formatted output and **blob-replacing it with the corresponding text from the original file**, byte-for-byte (chunked formatting and all).
3. Then running a regex substitution to overwrite `(name "...")` to `{footprint_name}.STEP` — a hidden filename-renaming side effect that the docstring did not document.

The Phase-C-B plan flagged this for possible removal: "the post-Phase-B emit handles `embedded_files`/`image` chunked data correctly." Validating that claim required an empirical check before pulling the trigger, since silently corrupting embedded STEP/PNG payloads would be a high-impact regression.

## Method

`docs/research/embedded_data_emit_check.py`. For each fixture:

1. Read original text, parse to s-expr.
2. Re-emit two ways, **without running any filters** (so the only variable is the formatter):
   - `with-regex` = `preserve_embedded_data_formatting(orig, sexp)`
   - `without-regex` = `format_kicad_sexp(sexp)` + ensure trailing newline
3. Stage all three files (orig + with + without) in sibling `.pretty` dirs with the **same basename** (so kicad-cli does not rename `(footprint "..."`).
4. Run `kicad-cli {fp,pcb,sch} upgrade --force` on each; record return code, oracle output, and the kicad-cli-canonicalized text.
5. Compare:
   - text equality of the canonicalized outputs (`orig` vs `with`, `orig` vs `without`, `with` vs `without`)
   - whitespace-independent equality of the concatenated base64 payload bytes (the actual data integrity check)

## Results

7 fixtures (3 footprints with embedded STEP, 4 PCBs with embedded footprints/STEP, 1 schematic for a no-embedded baseline):

| Metric | Value |
|---|---|
| `with-regex` SEGFAULTs in kicad-cli | **4 / 4 PCBs** (`0xC0000005` / ACCESS_VIOLATION) |
| `without-regex` accepted by kicad-cli | **7 / 7** |
| Payload bytes (concatenated `(data ...)` across all chunks) — `without-regex` byte-equal to original | **3 / 3 footprints** (PCBs not measurable because `with` SEGFAULTed) |
| `without-regex` text-equal to oracle of original after canonicalization | **4 / 7** (the others differ only in chunk-line placement; kicad-cli passes that through) |

Per-fixture summary:

```
SODFL1608X65N.kicad_mod              without==orig, payload bytes equal
OSC_KYOCERA_KV7050B-C3.kicad_mod     without==orig, payload bytes equal
SAMTEC_MTLW-102-07-L-S-250.kicad_mod without==orig, payload bytes equal
vme-wren.kicad_pcb                   with-regex SEGFAULT, without-regex OK
11-10084__speedy_processing_module__A.kicad_pcb  with-regex SEGFAULT, without-regex OK
speedy.kicad_pcb                     with-regex SEGFAULT, without-regex OK
component_designator_top.kicad_pcb   with-regex SEGFAULT, without-regex OK, without==orig
```

## Diagnosis: why the regex SEGFAULTs on PCBs

The blob-replace step searches the original text for `\t(embedded_files` (one tab — the indent level it expects for footprint files where `embedded_files` is a top-level child of `(footprint ...)`). On a PCB, embedded footprints are nested an extra level, so `(embedded_files ...)` appears at *deeper* indentation. The single-tab pattern still finds matches (greedy text scan), but the matched range and the corresponding range in the formatted output are not at the same nesting depth. The blob is spliced in with mismatched paren structure, and kicad-cli's parser walks off the end and crashes (ACCESS_VIOLATION).

The bug was masked because:
- The function is only exercised end-to-end by file-IO entry points; the unit test only checked the no-embedded passthrough branch.
- The PCB entry point (`kicad__pcb_filter`) had already been switched to plain `format_kicad_sexp` with a comment ("very slow for large PCBs") — it never went through the regex path. That was an unintentional but lucky avoidance of the crash.
- Footprints exposed the **other** bug (silent filename rewrite) but kicad-cli still accepted the malformed-but-parseable output.

## Diagnosis: the hidden filename rewrite

`preserve_embedded_data_formatting` ran an unconditional `re.sub` rewriting the first `(name "..."`) inside the preserved `embedded_files` block to `{footprint_name}.STEP`. This is a content modification, not formatting preservation, and:
- Renames PDF datasheets to `.STEP` (observed on `OSC_KYOCERA_KV7050B-C3.kicad_mod`, which has a `(type datasheet)` PDF, not a STEP model).
- Hides what `fp_filter__normalized_embedded_model_naming` does in the in-place mutation — same rewrite, but the regex would clobber any other embedded file regardless of type or filter intent.

Removing the regex makes filter behavior single-source: the filter chain (which does the rename correctly via `fp_filter__normalized_embedded_model_naming`) is the only thing modifying content, and the formatter is purely a formatter.

## Action taken

`kicad_filter_core.py`:
- Removed `preserve_embedded_data_formatting` (~110 LOC including the regex helpers).
- Added a small `_emit(sexp)` private helper that calls `format_kicad_sexp` + ensures a trailing newline.
- Rewired all 4 callsites (`kicad__fp_filter`, `kicad__sym_filter`, `kicad__sch_filter` MODE 2 + MODE 3) to use `_emit`.
- `kicad__pcb_filter` already used `format_kicad_sexp` directly — switched to `_emit` for consistency, removed the obsolete comment.

`__init__.py`:
- Removed `preserve_embedded_data_formatting` from `__all__`, the lazy `__getattr__` membership tuple, the import block, and the lookup dict.

`toolz-tests/.../test_L2_004_filter_framework.py`:
- Dropped the `preserve_embedded_data_formatting` callable assertion in `test_module_imports`.
- Removed `TestPreserveEmbeddedDataFormatting` (only had a no-op passthrough test).
- Updated docstring to "1 formatting helper" instead of 2.

## Validation

- L0 + L2 = **124 passed** (was 125; one test removed because the function it tested no longer exists).
- L1 source-model hygiene = **2 passed**.
- Direct integration: `kicad__pcb_filter(speedy.kicad_pcb)` + `kicad-cli pcb upgrade --force` = **OK**.
- Direct integration: `kicad__fp_filter(SODFL1608X65N.kicad_mod)` + `kicad-cli fp upgrade --force` = **OK**.
