"""
Subtest: S-Expression Parsing
Stratum: L0_foundation
Purpose: Test KiCad S-expression parser and builder

Tests the core S-expression functionality used by all KiCad file parsing.
This is the foundation layer - if these tests fail, nothing above works.
"""

import pytest
from kicad_monkey.kicad_sexpr import (
    QuotedString,
    SexprBuilder,
    SexprError,
    SexprItem,
    build_sexp,
    format_sexp,
    parse_sexp,
    validate_bare_string,
)

# ============================================================================
# Basic Functionality Tests
# ============================================================================

def test_module_imports():
    """Verify all sexpr exports can be imported."""
    assert parse_sexp is not None
    assert build_sexp is not None
    assert format_sexp is not None
    assert QuotedString is not None
    assert SexprBuilder is not None


# ============================================================================
# parse_sexp() Tests
# ============================================================================

def test_parse_simple_sexp(simple_sexp_samples):
    """Test parsing simple S-expressions."""
    result = parse_sexp(simple_sexp_samples["simple"])
    # Parser returns integers as int, not string
    assert result == ["test", 123]


def test_parse_nested_sexp(simple_sexp_samples):
    """Test parsing nested S-expressions."""
    result = parse_sexp(simple_sexp_samples["nested"])
    # Parser returns integers as int
    assert result == ["outer", ["inner", 1, 2], 3]


def test_parse_quoted_string(simple_sexp_samples):
    """Test parsing quoted strings."""
    result = parse_sexp(simple_sexp_samples["quoted"])
    assert result == ["data", QuotedString("quoted string")]
    assert isinstance(result[1], QuotedString)


def test_parse_mixed_types(simple_sexp_samples):
    """Test parsing mixed data types (strings, integers, floats)."""
    result = parse_sexp(simple_sexp_samples["mixed"])
    assert result[0] == "test"
    assert result[1] == QuotedString("string")
    assert result[2] == 123
    assert result[3] == 4.5


def test_parse_escaped_quotes(simple_sexp_samples):
    """Test parsing strings with escaped quotes."""
    result = parse_sexp(simple_sexp_samples["escaped"])
    assert result == ["data", QuotedString('with "escaped quotes"')]


def test_parse_empty_string(simple_sexp_samples):
    """Test parsing empty quoted strings."""
    result = parse_sexp(simple_sexp_samples["empty_string"])
    assert result == ["test", QuotedString("")]


def test_parse_multiline():
    """Test parsing multiline S-expressions (KiCad style)."""
    sexp = '''(symbol
  (name "Test")
  (value "123")
)'''
    result = parse_sexp(sexp)
    assert result[0] == "symbol"
    assert result[1] == ["name", QuotedString("Test")]
    assert result[2] == ["value", QuotedString("123")]


def test_parse_error_empty():
    """Test that empty input raises SexprError."""
    with pytest.raises(SexprError, match="No or empty expression"):
        parse_sexp("")


def test_parse_error_missing_opening():
    """Test that missing initial opening parenthesis raises error."""
    with pytest.raises(SexprError, match="Missing initial opening parenthesis"):
        parse_sexp("test 123")


# ============================================================================
# build_sexp() Tests
# ============================================================================

def test_build_simple_sexp():
    """Test building simple S-expression from list."""
    data = ["test", "123"]
    result = build_sexp(data)
    assert result == "(test 123)"


def test_build_nested_sexp():
    """Test building nested S-expression."""
    data = ["outer", ["inner", "1", "2"], "3"]
    result = build_sexp(data)
    assert "inner" in result
    assert result.startswith("(outer")
    assert result.endswith(")")


def test_build_with_quoted_string():
    """Test building S-expression with QuotedString."""
    data = ["test", QuotedString("quoted string")]
    result = build_sexp(data)
    assert '"quoted string"' in result


def test_build_with_integers():
    """Test building S-expression with integers."""
    data = ["test", 123, 456]
    result = build_sexp(data)
    assert "123" in result
    assert "456" in result


def test_build_with_floats():
    """Test building S-expression with floats."""
    data = ["test", 4.5, 10.0]
    result = build_sexp(data)
    assert "4.5" in result
    assert "10" in result


def test_build_empty_string():
    """Test building S-expression with empty QuotedString."""
    data = ["test", QuotedString("")]
    result = build_sexp(data)
    assert '""' in result


# ============================================================================
# QuotedString Tests
# ============================================================================

def test_quoted_string_creation():
    """Test QuotedString object creation."""
    qs = QuotedString("test string")
    assert str(qs) == "test string"
    assert isinstance(qs, str)


def test_quoted_string_get_as_sexp():
    """Test QuotedString.get_as_sexp() method."""
    qs = QuotedString("test")
    assert qs.get_as_sexp() == '"test"'


def test_quoted_string_escaping():
    """Test QuotedString properly escapes quotes and backslashes."""
    qs = QuotedString('test "quotes"')
    result = qs.get_as_sexp()
    assert result == r'"test \"quotes\""'


def test_quoted_string_empty():
    """Test empty QuotedString."""
    qs = QuotedString("")
    assert qs.get_as_sexp() == '""'


# ============================================================================
# validate_bare_string() Tests
# ============================================================================

def test_validate_bare_string_valid():
    """Test that valid bare strings pass validation."""
    validate_bare_string("test")
    validate_bare_string("test123")
    validate_bare_string("test-name")
    validate_bare_string("test_name")


def test_validate_bare_string_with_whitespace():
    """Test that strings with whitespace fail validation."""
    with pytest.raises(SexprError, match="whitespace"):
        validate_bare_string("test string")


def test_validate_bare_string_with_parens():
    """Test that strings with parentheses fail validation."""
    with pytest.raises(SexprError, match="parentheses"):
        validate_bare_string("test()")


def test_validate_bare_string_with_quotes():
    """Test that strings with quotes fail validation."""
    with pytest.raises(SexprError, match="quotes"):
        validate_bare_string('test"string')


def test_validate_bare_string_empty():
    """Test that empty string fails validation."""
    with pytest.raises(SexprError, match="empty"):
        validate_bare_string("")


# ============================================================================
# Round-trip Testing (parse -> build -> parse)
# ============================================================================

def test_round_trip_simple():
    """Test that simple S-expressions survive parse->build->parse round trip."""
    original = "(test 123 456)"
    parsed = parse_sexp(original)
    rebuilt = build_sexp(parsed)
    reparsed = parse_sexp(rebuilt)
    assert parsed == reparsed


def test_round_trip_nested():
    """Test that nested S-expressions survive round trip."""
    original = "(outer (inner 1 2) (another 3 4) 5)"
    parsed = parse_sexp(original)
    rebuilt = build_sexp(parsed)
    reparsed = parse_sexp(rebuilt)
    assert parsed == reparsed


def test_round_trip_quoted_strings():
    """Test that quoted strings survive round trip."""
    original = '(test "quoted string" "another")'
    parsed = parse_sexp(original)
    rebuilt = build_sexp(parsed)
    reparsed = parse_sexp(rebuilt)
    assert parsed == reparsed


def test_round_trip_mixed_types():
    """Test that mixed types survive round trip."""
    original = '(test "string" 123 4.5 bareword)'
    parsed = parse_sexp(original)
    rebuilt = build_sexp(parsed)
    reparsed = parse_sexp(rebuilt)
    assert parsed == reparsed


def test_round_trip_with_format():
    """Test round trip with format_sexp() formatting."""
    original = "(test (nested 1 2) 3)"
    parsed = parse_sexp(original)
    rebuilt = build_sexp(parsed)
    formatted = format_sexp(rebuilt)
    reparsed = parse_sexp(formatted)
    assert parsed == reparsed


# ============================================================================
# SexprBuilder Tests
# ============================================================================

def test_sexpr_builder_basic():
    """Test SexprBuilder basic functionality."""
    builder = SexprBuilder("test")
    builder.addItems(["value1", "value2"])
    builder.endGroup()

    result = builder.output
    assert "(test" in result
    assert "value1" in result
    assert "value2" in result


def test_sexpr_builder_nested():
    """Test SexprBuilder with nested groups."""
    builder = SexprBuilder("outer")
    builder.startGroup("inner")
    builder.addItems(["value"])
    builder.endGroup()
    builder.endGroup()

    result = builder.output
    assert "(outer" in result
    assert "(inner" in result


# ============================================================================
# SexprItem Tests
# ============================================================================

def test_sexpr_item_simple_string():
    """Test SexprItem with simple bare string."""
    result = SexprItem("test")
    assert result == "test"


def test_sexpr_item_quoted_string():
    """Test SexprItem with QuotedString."""
    result = SexprItem(QuotedString("test"))
    assert result == '"test"'


def test_sexpr_item_with_key():
    """Test SexprItem with key parameter."""
    result = SexprItem("value", key="name")
    assert result == "(name value)"


def test_sexpr_item_integer():
    """Test SexprItem with integer."""
    result = SexprItem(123)
    assert result == "123"


def test_sexpr_item_float():
    """Test SexprItem with float."""
    result = SexprItem(4.5)
    assert result == "4.5"


def test_sexpr_item_none():
    """Test SexprItem with None (should become empty string)."""
    result = SexprItem(None)
    assert result == '""'


# ============================================================================
# format_sexp() Tests
# ============================================================================

def test_format_sexp_indentation():
    """Test that format_sexp() adds proper indentation."""
    sexp = "(outer (inner 1 2) (another 3 4))"
    formatted = format_sexp(sexp)

    # Should have newlines
    assert "\n" in formatted
    # Should have indentation
    assert "  " in formatted


def test_format_sexp_custom_indentation():
    """Test format_sexp() with custom indentation size."""
    sexp = "(outer (inner 1 2))"
    formatted = format_sexp(sexp, indentation_size=4)

    # Should use 4 spaces for indentation
    assert "    " in formatted


def test_format_sexp_max_nesting():
    """Test format_sexp() max_nesting parameter."""
    sexp = "(a (b (c (d 1))))"

    # With max_nesting=2, deeper levels stay inline
    formatted = format_sexp(sexp, max_nesting=2)

    # Should still be valid S-expression
    parsed = parse_sexp(formatted)
    assert parsed == ["a", ["b", ["c", ["d", 1]]]]
