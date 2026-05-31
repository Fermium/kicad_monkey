---
name: Bug report
about: Report incorrect API behavior or a crash
title: ""
labels: bug
assignees: ""
---

## Summary

What API call, parser/rendering path, or workflow failed?

## Version

Paste the package version.

```powershell
python -c "import kicad_monkey; print(kicad_monkey.__version__)"
```

## Steps To Reproduce

1.
2.
3.

## Expected Behavior

What did you expect to happen?

## Actual Behavior

What happened instead? Include the full error message and the last useful log lines.

## Environment

- OS:
- Python:
- kicad-monkey version:
- KiCad version, if a KiCad CLI oracle is involved:

## Files Or Fixtures

Attach only files that can be shared publicly. Do not attach proprietary KiCad
designs unless they have been cleared for public release.

## Additional Context

Mention whether this affects parsing, round-trip output, SVG/IR output,
netlist output, project/design JSON, or the public API contract.
