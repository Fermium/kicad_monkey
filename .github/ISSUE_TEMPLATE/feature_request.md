---
name: Feature request
about: Propose a public API, contract, or workflow improvement
title: ""
labels: enhancement
assignees: ""
---

## Summary

What should change?

## User Story

As a ..., I want ..., so that ...

Describe the KiCad workflow this supports and why the current API or behavior
is not enough.

## Affected API Or Workflow

List the API entry points, parser/rendering paths, corpus formats, or
downstream packages this affects.

```python
from kicad_monkey import KiCadDesign
```

## Proposed Contract

List expected arguments, return values, JSON fields, corpus fields, defaults,
and allowed values.

```json
{
  "example": "contract"
}
```

## Expected Outputs

Describe expected files, generated JSON, SVG, netlist data, or other outputs.

## Acceptance Criteria

- [ ] Public API docs cover the behavior
- [ ] Design docs cover usage intent and tests
- [ ] Contract docs and conformance tests cover stable JSON/corpus/API behavior, if changed
- [ ] Corpus fixtures are public or synthetic

## Public Contract Impact

- [ ] New or changed promoted API export
- [ ] New or changed JSON/corpus contract
- [ ] New or changed generated file/artifact
- [ ] New dependency
- [ ] Documentation only

## Alternatives

Mention any workaround or existing API you considered.

## Files Or Examples

Attach only files that can be shared publicly. Small synthetic examples are
preferred for tests.
