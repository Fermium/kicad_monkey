# Post-mortem: pcbnew scientific-notation parser truncation

**Status: RESOLVED — the bug is in the staged corpus binary only,
not in upstream KiCad.** Upstream fix (commit `934a5bac34`,
2026-02-25) is genuinely in place. The kicad-cli we were testing
against was produced by `kicad-win-builder` (a *packaging* pipeline,
not a development pipeline), which keeps its own clone of the kicad
source at `kicad-win-builder/.build/kicad/`. That clone predates the
fix. The kicad-dev debug build at
`C:\eli\kicad_build\kicad\build\msvc-win64-debug\` *does* compile the
fix correctly (verified by disassembling its `?parseDouble@DSNLEXER@@IEAANXZ`
symbol — see "Debug build verification" below).

## Root cause

The wrong oracle binary. Our regression suite ran `kicad-cli pcb
upgrade` from the corpus-staged binary (`99c64afbf83f` and
`00911f90fd99` under `tools/kicad-cli/<short-hash>/bin/`). Those were
built by `kicad-win-builder` against its own source clone:

```text
$ grep kicad_SOURCE kicad-win-builder/.build/kicad/build/x64-windows-Release/CMakeCache.txt
kicad_SOURCE_DIR:STATIC=C:/eli/kicad_build/kicad-win-builder/.build/kicad
CMAKE_HOME_DIRECTORY:INTERNAL=C:/eli/kicad_build/kicad-win-builder/.build/kicad
```

That source tree has the **pre-fix** dsnlexer.cpp:

```cpp
// .build/kicad/common/dsnlexer.cpp:870
fast_float::from_chars( ..., fast_float::chars_format::skip_white_space );
```

vs. the canonical (and patched) source we kept reading:

```cpp
// kicad/common/dsnlexer.cpp:862-872
#define FROM_CHARS_FLAGS ( fast_float::chars_format::skip_white_space \
                         | fast_float::chars_format::general )
fast_float::from_chars( ..., FROM_CHARS_FLAGS );
```

It also bundles an older fast_float (`FASTFLOAT_VERSION_MINOR=0`,
i.e. 8.0.x) versus 8.2.2 in the canonical tree. Both copies define
`general = fixed | scientific = 5`, but that doesn't matter because
the call-site never ORs `general` into the flags.

## Smoking-gun: release .obj inspection

Section `0x20C` of the May-8 21:15 release
`.build/.../kicommon.dir/dsnlexer.cpp.obj` is `?parseDouble@DSNLEXER@@IEAANXZ`.
First 16 bytes after the prolog:

```
0040: 42 10 4c 03 c2  48 c7 44 24 60 00 01 00 00  48 8d
                      ^^ ^^ ^^^^^^^^^ ^^^^^^^^^^^
                      mov qword [rsp+0x60], 0x100
```

`0x100` = `skip_white_space` alone, no `general` bit. With the fix
compiled in it would have been `0x105` (`skip_white_space | general`).

## Debug build verification

The kicad-dev debug build at
`C:\eli\kicad_build\kicad\build\msvc-win64-debug\common\CMakeFiles\kicommon.dir\dsnlexer.cpp.obj`
(Mar-29 build, compiled by `kicad-dev/scripts/configure.ps1` +
`build_cli.ps1` from canonical source). Disasm of parseDouble:

```
0054: ba 05 00 00 00       mov edx, 0x5         ; general
0059: b9 00 01 00 00       mov ecx, 0x100       ; skip_white_space
005e: e8 .. .. .. ..       call operator|(chars_format, chars_format)
0063: 48 89 84 24 c8 01... mov [rsp+0x1c8], rax ; store OR result as format
```

Both flag bits are present and OR'd at runtime. The fix is genuinely
in the debug binary. The Mar-29 debug build's preserve-`3e-06`
behaviour observed earlier is therefore the correct (fixed) parser at
work, not "upgrade skipping the body" as we hypothesised.

## Why every release "rebuild attempt" was a no-op for this bug

- Editing `C:\eli\kicad_build\kicad\common\dsnlexer.cpp` left the
  `kicad-win-builder/.build/kicad/common/dsnlexer.cpp` copy untouched.
- Force-deleting `dsnlexer.cpp.obj` and re-running ninja recompiled
  the **same unfixed translation unit**. Identical input → identical
  machine code (the .dll byte-diff was 13 PE-header timestamp bytes,
  consistent with no content change).
- Both staged corpus binaries (`99c64afbf83f`, `00911f90fd99`) came
  from the same kicad-win-builder pipeline off the same `.build/kicad/`
  clone, so their `MANIFEST.toml` `kicad_commit` field is **misleading** —
  it records the upstream hash someone *intended* to build, not the
  hash actually compiled.

---

## What we observed

Running `kicad-cli pcb upgrade --force` against a `.kicad_pcb`
fixture whose `(thermal_gap ...)` was edited to scientific notation:

| Input on disk        | Re-emitted as       |
|----------------------|---------------------|
| `(thermal_gap 3e-06)`     | `(thermal_gap 3)`     |
| `(thermal_gap 1.5e-06)`   | `(thermal_gap 1.5)`   |
| `(thermal_gap 1.5E-06)`   | `(thermal_gap 1.5)`   |
| `(thermal_gap 0.5e-06)`   | `(thermal_gap 0.5)`   |
| `(thermal_gap 1e-3)`      | `(thermal_gap 1)`     |
| `(thermal_gap 3e+0)`      | `(thermal_gap 3)`     |
| `(thermal_gap 3.0e-06)`   | `(thermal_gap 3)`     |
| `(thermal_gap +3e-06)`    | "Failed to load board" (parse rejected) |

Pattern: lexer kept the `[+-]?[0-9]*\.?[0-9]+` mantissa, dropped the
`[eE][+-]?[0-9]+` exponent. This is a silent factor-of-up-to-1e6
data-corruption bug. It looked completely real.

## Upstream fix

The fix is upstream commit `934a5bac34` (Ian McInerney, 2026-02-25):

```diff
--- a/common/dsnlexer.cpp
+++ b/common/dsnlexer.cpp
+#define FROM_CHARS_FLAGS ( fast_float::chars_format::skip_white_space | fast_float::chars_format::general )

  double DSNLEXER::parseDouble()
  {
      ...
-     fast_float::from_chars( str.data(), str.data() + str.size(), dval,
-                             fast_float::chars_format::skip_white_space );
+     fast_float::from_chars( str.data(), str.data() + str.size(), dval,
+                             FROM_CHARS_FLAGS );
```

The `chars_format::skip_white_space` flag accepts only fixed-point;
adding `chars_format::general` lets `fast_float::from_chars` parse
scientific notation as well. One-line change, present in canonical
source `C:\eli\kicad_build\kicad\` for months prior to our
investigation. **There is nothing left to upstream.**

## Confirmed staleness diagnosis

Our shared corpus stages kicad-cli binaries at e.g.:
```
<corpus>\tools\kicad-cli\99c64afbf83f\bin\kicad-cli.exe
```

`MANIFEST.toml` claimed a post-fix kicad commit hash, but the binary's
mtime was **2026-01-28** — a month *before* the fix landed. Every
staged binary up through 2026-05-08 was produced by the kicad-win-builder
packaging pipeline, which compiles from its own stale clone at
`kicad-win-builder/.build/kicad/`, not from canonical source. The
`.obj` disassembly above (`mov qword [rsp+0x60], 0x100` — pre-fix)
confirms it.

The debug kicad-cli at `C:\eli\kicad_build\kicad\build\msvc-win64-debug\`
(built by `kicad-dev/scripts/configure.ps1` + `build_cli.ps1` from
canonical source) preserves the input correctly:

```
(thermal_gap 3e-06)   ->   (thermal_gap 3e-06)
```

## Resolution (2026-05-09)

Built a release kicad-cli (`76f8839fd232`) directly from canonical
source `C:\eli\kicad_build\kicad\` and staged it under
`<corpus>\tools\kicad-cli\76f8839fd232\`. The two prior
kicad-win-builder-based stagings (`99c64afbf83f`, `00911f90fd99`)
were deleted. With the corrected oracle binary, `EmptyZone.kicad_pcb`
round-trips cleanly without any selective float-formatting workaround.

## Implications for kicad_monkey

- **Don't use `kicad-win-builder` for development oracles.** It's a
  packaging pipeline with its own source clone. For corpus staging,
  build a release kicad-cli directly from `C:\eli\kicad_build\kicad\`.
- **Current oracle is `76f8839fd232`** (release, RelWithDebInfo, built
  2026-05-09 from canonical source — has the FROM_CHARS_FLAGS fix).
  See `toolz-tests/tools/kicad-cli/MANIFEST.toml`.
- **Slice 31a (custom float emit) is permanently moot.** With a
  correct oracle, the lexer round-trips scientific notation natively.
  No downstream workaround is needed and re-attempting one would
  regress fixtures whose source intentionally uses scientific
  notation (e.g. `variants.kicad_pcb` arc endpoints).
- **No upstream filing required for this bug.** It was already fixed
  in February. Any future pcbnew scientific-notation reproducer
  should first be re-checked against canonical-source kicad-cli to
  confirm it still mis-parses post-`934a5bac34` before being filed.

## Lessons

1. When a bug looks suspiciously old but isn't fixed in the upstream
   we have on disk, always check whether the *binary we are running*
   is actually the build of the source we are reading. The fix-vs-
   binary mismatch can be invisible if both file paths reference the
   same commit hash.
2. **Always check `CMakeCache.txt` for `CMAKE_HOME_DIRECTORY` / the
   project's `_SOURCE_DIR` value before trusting any wrapper script
   that names a "source dir" variable.** Wrappers around `cmake --build`
   don't change the configured source path; only `cmake -S <dir>` does.
3. `kicad-win-builder` keeps its own clone of the kicad source tree
   under `.build/kicad/`. Any "build kicad" workflow that doesn't
   explicitly rsync from the canonical `C:\eli\kicad_build\kicad` is
   compiling stale code.
4. Inspecting the compiled `.obj` directly with `dumpbin /HEADERS`
   plus a hex search for the expected immediate constant (here:
   `0x105` for `skip_white_space | general` vs `0x100` for
   `skip_white_space` alone) is the fastest way to confirm whether a
   one-line source change actually made it into the binary. More
   reliable than re-running an integration test.
5. Before authoring an upstream patch, search the upstream tree for
   any pre-existing test that targets the symptom — `grep -ri
   scientific qa/tests/` would have found `ScientificNotationLoading`
   immediately and short-circuited a half-day of investigation.
