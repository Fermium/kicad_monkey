"""
Subtest: S-Expression Mutation Primitives
Stratum: L0_foundation
Purpose: Test the kicad_base sexpr mutation helpers added in Slice C-B-3.

Covers replace_element, remove_element, remove_all_elements, set_value,
walk, find_path, transform_descendants. These are foundation utilities
used by the filter framework refactor in Slice C-B-4.
"""

import pytest

from kicad_monkey.kicad_base import (
    find_path,
    remove_all_elements,
    remove_element,
    replace_element,
    set_value,
    transform_descendants,
    walk,
)


# ============================================================================
# replace_element
# ============================================================================

class TestReplaceElement:
    def test_replaces_first_match(self):
        sexp = ['root', ['version', 1], ['version', 2], ['name', 'foo']]
        ok = replace_element(sexp, 'version', ['version', 99])
        assert ok is True
        assert sexp == ['root', ['version', 99], ['version', 2], ['name', 'foo']]

    def test_returns_false_when_no_match(self):
        sexp = ['root', ['name', 'foo']]
        ok = replace_element(sexp, 'version', ['version', 99])
        assert ok is False
        assert sexp == ['root', ['name', 'foo']]

    def test_handles_non_list_input(self):
        assert replace_element('not a list', 'foo', ['foo', 1]) is False
        assert replace_element(None, 'foo', ['foo', 1]) is False


# ============================================================================
# remove_element
# ============================================================================

class TestRemoveElement:
    def test_removes_first_match_returns_it(self):
        sexp = ['root', ['version', 1], ['version', 2], ['name', 'foo']]
        removed = remove_element(sexp, 'version')
        assert removed == ['version', 1]
        assert sexp == ['root', ['version', 2], ['name', 'foo']]

    def test_returns_none_when_no_match(self):
        sexp = ['root', ['name', 'foo']]
        assert remove_element(sexp, 'version') is None
        assert sexp == ['root', ['name', 'foo']]


# ============================================================================
# remove_all_elements
# ============================================================================

class TestRemoveAllElements:
    def test_removes_every_match(self):
        sexp = ['root', ['fp_line', 1], ['name', 'foo'], ['fp_line', 2], ['fp_line', 3]]
        removed = remove_all_elements(sexp, 'fp_line')
        assert removed == [['fp_line', 1], ['fp_line', 2], ['fp_line', 3]]
        assert sexp == ['root', ['name', 'foo']]

    def test_returns_empty_list_when_no_match(self):
        sexp = ['root', ['name', 'foo']]
        assert remove_all_elements(sexp, 'fp_line') == []


# ============================================================================
# set_value
# ============================================================================

class TestSetValue:
    def test_replaces_existing_sublist(self):
        sexp = ['root', ['version', 1], ['name', 'foo']]
        set_value(sexp, 'version', 99)
        assert sexp == ['root', ['version', 99], ['name', 'foo']]

    def test_appends_when_missing(self):
        sexp = ['root', ['name', 'foo']]
        set_value(sexp, 'version', 99)
        assert sexp == ['root', ['name', 'foo'], ['version', 99]]

    def test_raises_on_non_list(self):
        with pytest.raises(TypeError):
            set_value('not a list', 'version', 1)


# ============================================================================
# walk
# ============================================================================

class TestWalk:
    def test_yields_all_list_nodes_depth_first(self):
        sexp = ['root', ['a', ['b', 1]], ['c', 2]]
        nodes = list(walk(sexp))
        assert nodes[0] is sexp
        assert ['a', ['b', 1]] in nodes
        assert ['b', 1] in nodes
        assert ['c', 2] in nodes
        # Strings/numbers not yielded
        assert all(isinstance(n, list) for n in nodes)
        # 4 lists total
        assert len(nodes) == 4

    def test_skips_non_list_input(self):
        assert list(walk('not a list')) == []
        assert list(walk(42)) == []
        assert list(walk(None)) == []


# ============================================================================
# find_path
# ============================================================================

class TestFindPath:
    def test_traverses_nested_path(self):
        pcb = ['kicad_pcb',
               ['setup',
                ['pcbplotparams',
                 ['layerselection', '0x00010fc_ffffffff']]]]
        result = find_path(pcb, 'setup', 'pcbplotparams')
        assert result == ['pcbplotparams', ['layerselection', '0x00010fc_ffffffff']]

    def test_returns_inner_target(self):
        pcb = ['kicad_pcb',
               ['setup',
                ['pcbplotparams',
                 ['layerselection', '0x00010fc_ffffffff']]]]
        result = find_path(pcb, 'setup', 'pcbplotparams', 'layerselection')
        assert result == ['layerselection', '0x00010fc_ffffffff']

    def test_returns_none_on_missing_segment(self):
        pcb = ['kicad_pcb', ['setup']]
        assert find_path(pcb, 'setup', 'pcbplotparams') is None
        assert find_path(pcb, 'missing', 'foo') is None


# ============================================================================
# transform_descendants
# ============================================================================

class TestTransformDescendants:
    def test_replaces_all_named_descendants(self):
        sexp = ['root',
                ['symbol', ['property', 'Reference', 'U']],
                ['symbol', ['property', 'Value', 'Foo']]]
        count = transform_descendants(
            sexp,
            'property',
            lambda p: [p[0], p[1].lower(), p[2]],
        )
        assert count == 2
        # Both properties' names are lowercased
        assert sexp[1][1] == ['property', 'reference', 'U']
        assert sexp[2][1] == ['property', 'value', 'Foo']

    def test_does_not_recurse_into_replaced_subtree(self):
        """If fn returns a list whose first element matches, we don't recurse
        into it — preventing infinite loops."""
        sexp = ['root', ['x', 1]]
        count = transform_descendants(
            sexp,
            'x',
            # Return a tree containing a fresh 'x' inside; should not be re-visited.
            lambda _: ['x', ['x', 99]],
        )
        assert count == 1
        # Only outer x replaced once; nested 'x' not touched.
        assert sexp == ['root', ['x', ['x', 99]]]

    def test_returns_zero_when_no_match(self):
        sexp = ['root', ['a', 1], ['b', 2]]
        count = transform_descendants(sexp, 'missing', lambda x: x)
        assert count == 0
        assert sexp == ['root', ['a', 1], ['b', 2]]


# ============================================================================
# Public API surface
# ============================================================================

def test_mutation_primitives_exposed_on_package():
    """Slice C-B-3: all 7 mutation primitives import via the public surface."""
    import kicad_monkey as km

    assert km.replace_element is replace_element
    assert km.remove_element is remove_element
    assert km.remove_all_elements is remove_all_elements
    assert km.set_value is set_value
    assert km.walk is walk
    assert km.find_path is find_path
    assert km.transform_descendants is transform_descendants


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
