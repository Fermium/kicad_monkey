# Package-Local Test Corpus

This directory carries the public KiCad test corpus so the public repository
can run corpus-backed tests without depending on a machine-local
`WN_TEST_CORPUS`.

The tracked public form is `kicad.zip`, stored through Git LFS. It contains a
top-level `kicad/` directory matching the external corpus layout:

```text
tests/corpus/kicad.zip
  kicad/...
```

For local review, the unpacked mirror may exist at `tests/corpus/kicad/`; that
directory is gitignored. Tests prefer the loose mirror when present. Otherwise
`tests/_suite_paths.py` extracts `kicad.zip` to `tests/corpus/.unpacked/` and
uses that path as the default `WN_TEST_CORPUS`.

Source snapshot:

- Mirrored root: `tests/corpus/kicad`
- Excluded generated/local-only directories: `output`, `review`,
  `review_tmp`, `.git`, `.history`
- Preserved oracle/reference directories such as `reference_output`

Archive SOP:

```powershell
uv run --extra test python scripts/package_kicad_corpus.py
uv run --extra test python scripts/package_kicad_corpus.py --check
uv run --extra test python tests/rack.py run L99_signoff
```

These assets are for repository tests and review. They are excluded from sdist
artifacts by `pyproject.toml`.
