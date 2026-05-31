"""
Test L0_018: variant overlay (Phase F-8)

Pure-unit coverage for the IR-record annotation that drives DNP /
exclude-from-bom / exclude-from-sim / exclude-from-pos dimming in
the F-5 SVG renderer.

The overlay is policy-driven (KiCadVariantOverlayPolicy); each
classifier consults the F-4 / F-7 record extras directly:
* symbol_instance  -> dnp / in_bom / exclude_from_sim / in_pos_files
* footprint        -> attr token list

Other record kinds (wires, labels, sheets, drawing-sheet borders)
always classify as active — variant flags are an instance concept.

Renderer wiring (svg group attrs) is exercised indirectly: dimmed
records carrying variant_state="dimmed" get opacity= / filter style
on the wrapper <g>.
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    KiCadVariantOverlayPolicy,
    VARIANT_STATE_ACTIVE,
    VARIANT_STATE_DIMMED,
    VARIANT_STATE_KEY,
    annotate_record_variant_state,
    apply_variant_overlay,
    compute_record_variant_state,
)
from kicad_monkey.kicad_plotter_ir import (
    KiCadPlotterDocument,
    KiCadPlotterOp,
    KiCadPlotterRecord,
)
from kicad_monkey.kicad_ir_to_svg import render_record
from kicad_monkey.kicad_sch_svg_renderer import (
    KiCadSvgRenderContext,
    KiCadSvgRenderOptions,
    KiCadVariantDimMode,
)


# =============================================================================
# Policy
# =============================================================================


def test_policy_default_is_dnp_only():
    p = KiCadVariantOverlayPolicy()
    assert p.dim_dnp is True
    assert p.dim_exclude_from_bom is False
    assert p.dim_exclude_from_sim is False
    assert p.dim_exclude_from_pos is False


def test_policy_assembly_view():
    p = KiCadVariantOverlayPolicy.assembly_view()
    assert p.dim_dnp is True
    assert p.dim_exclude_from_pos is True
    assert p.dim_exclude_from_bom is False
    assert p.dim_exclude_from_sim is False


def test_policy_bom_view():
    p = KiCadVariantOverlayPolicy.bom_view()
    assert p.dim_dnp is True
    assert p.dim_exclude_from_bom is True
    assert p.dim_exclude_from_pos is False
    assert p.dim_exclude_from_sim is False


def test_policy_all_axes():
    p = KiCadVariantOverlayPolicy.all_axes()
    assert p.dim_dnp is True
    assert p.dim_exclude_from_bom is True
    assert p.dim_exclude_from_sim is True
    assert p.dim_exclude_from_pos is True


def test_policy_is_frozen():
    p = KiCadVariantOverlayPolicy()
    with pytest.raises(Exception):
        p.dim_dnp = False  # type: ignore[misc]


# =============================================================================
# Helpers
# =============================================================================


def _sym(uuid: str = "u-sym", **extras) -> KiCadPlotterRecord:
    base = {"in_bom": True, "on_board": True, "dnp": False,
            "exclude_from_sim": False, "in_pos_files": True}
    base.update(extras)
    return KiCadPlotterRecord(
        uuid=uuid, kind="symbol_instance", object_id="X1", extras=base,
    )


def _fp(uuid: str = "u-fp", attr: list | None = None) -> KiCadPlotterRecord:
    return KiCadPlotterRecord(
        uuid=uuid, kind="footprint", object_id="R1",
        extras={"name": "R_0805", "attr": list(attr or [])},
    )


# =============================================================================
# compute_record_variant_state — symbol_instance
# =============================================================================


def test_symbol_active_when_no_flags():
    r = _sym()
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


def test_symbol_dimmed_for_dnp():
    r = _sym(dnp=True)
    p = KiCadVariantOverlayPolicy()  # default = dnp only
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_symbol_not_dimmed_for_dnp_when_policy_disables():
    r = _sym(dnp=True)
    p = KiCadVariantOverlayPolicy(dim_dnp=False)
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


def test_symbol_dimmed_for_exclude_from_bom():
    r = _sym(in_bom=False)
    p = KiCadVariantOverlayPolicy.bom_view()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_symbol_dimmed_for_exclude_from_sim():
    r = _sym(exclude_from_sim=True)
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_symbol_dimmed_for_exclude_from_pos():
    r = _sym(in_pos_files=False)
    p = KiCadVariantOverlayPolicy.assembly_view()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_symbol_default_policy_ignores_bom_and_pos():
    """Default policy only flags DNP; in_bom=False alone stays active."""
    r = _sym(in_bom=False, in_pos_files=False)
    p = KiCadVariantOverlayPolicy()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


def test_symbol_missing_extras_treated_as_included():
    """No extras at all → all defaults (in_bom=True etc.) → active."""
    r = KiCadPlotterRecord(uuid="u", kind="symbol_instance", object_id="X")
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


# =============================================================================
# compute_record_variant_state — footprint
# =============================================================================


def test_footprint_active_when_no_attrs():
    r = _fp(attr=["smd"])
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


def test_footprint_dimmed_for_dnp_attr():
    r = _fp(attr=["smd", "dnp"])
    p = KiCadVariantOverlayPolicy()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_footprint_dimmed_for_exclude_from_bom_attr():
    r = _fp(attr=["smd", "exclude_from_bom"])
    p = KiCadVariantOverlayPolicy.bom_view()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_footprint_dimmed_for_exclude_from_pos_attr():
    r = _fp(attr=["smd", "exclude_from_pos"])
    p = KiCadVariantOverlayPolicy.assembly_view()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_footprint_attr_match_is_case_insensitive():
    r = _fp(attr=["DNP"])
    p = KiCadVariantOverlayPolicy()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_DIMMED


def test_footprint_missing_attr_extras_active():
    r = KiCadPlotterRecord(uuid="u", kind="footprint", object_id="R")
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


# =============================================================================
# compute_record_variant_state — non-variant kinds
# =============================================================================


@pytest.mark.parametrize(
    "kind",
    ["wire", "label", "sheet", "drawing_sheet", "lib_symbol", "lib_subsymbol"],
)
def test_non_variant_kinds_always_active(kind):
    r = KiCadPlotterRecord(
        uuid="u", kind=kind, object_id="x",
        extras={"dnp": True, "in_bom": False, "in_pos_files": False,
                "attr": ["dnp", "exclude_from_bom"]},
    )
    p = KiCadVariantOverlayPolicy.all_axes()
    assert compute_record_variant_state(r, policy=p) == VARIANT_STATE_ACTIVE


# =============================================================================
# annotate_record_variant_state
# =============================================================================


def test_annotate_sets_variant_state_dimmed():
    r = _sym(dnp=True)
    p = KiCadVariantOverlayPolicy()
    out = annotate_record_variant_state(r, policy=p)
    assert out.extras[VARIANT_STATE_KEY] == VARIANT_STATE_DIMMED


def test_annotate_sets_variant_state_active():
    r = _sym()
    p = KiCadVariantOverlayPolicy.all_axes()
    out = annotate_record_variant_state(r, policy=p)
    assert out.extras[VARIANT_STATE_KEY] == VARIANT_STATE_ACTIVE


def test_annotate_does_not_mutate_input():
    r = _sym(dnp=True)
    p = KiCadVariantOverlayPolicy()
    _ = annotate_record_variant_state(r, policy=p)
    assert VARIANT_STATE_KEY not in r.extras


def test_annotate_preserves_other_extras():
    r = _sym(dnp=True)
    r.extras["lib_id"] = "Device:R"
    out = annotate_record_variant_state(r, policy=KiCadVariantOverlayPolicy())
    assert out.extras["lib_id"] == "Device:R"
    assert out.extras["dnp"] is True


def test_annotate_preserves_uuid_kind_object_id_operations():
    op = KiCadPlotterOp.circle(cx=0, cy=0, diameter_nm=1_000_000)
    r = KiCadPlotterRecord(
        uuid="u", kind="symbol_instance", object_id="R1",
        operations=[op],
        extras={"dnp": True},
    )
    out = annotate_record_variant_state(r, policy=KiCadVariantOverlayPolicy())
    assert out.uuid == "u"
    assert out.kind == "symbol_instance"
    assert out.object_id == "R1"
    assert len(out.operations) == 1


# =============================================================================
# apply_variant_overlay
# =============================================================================


def test_apply_variant_overlay_annotates_every_record():
    doc = KiCadPlotterDocument(records=[
        _sym(uuid="a"),
        _sym(uuid="b", dnp=True),
        _fp(uuid="c", attr=["dnp"]),
        KiCadPlotterRecord(uuid="d", kind="wire", object_id=""),
    ])
    out = apply_variant_overlay(doc, policy=KiCadVariantOverlayPolicy())
    states = [r.extras.get(VARIANT_STATE_KEY) for r in out.records]
    assert states == [
        VARIANT_STATE_ACTIVE,    # a — no flags
        VARIANT_STATE_DIMMED,    # b — dnp
        VARIANT_STATE_DIMMED,    # c — fp dnp attr
        VARIANT_STATE_ACTIVE,    # d — non-variant kind
    ]


def test_apply_variant_overlay_does_not_mutate_input_doc():
    r = _sym(dnp=True)
    doc = KiCadPlotterDocument(records=[r])
    _ = apply_variant_overlay(doc, policy=KiCadVariantOverlayPolicy())
    assert VARIANT_STATE_KEY not in r.extras


def test_apply_variant_overlay_preserves_doc_metadata():
    doc = KiCadPlotterDocument(
        records=[_sym()],
        source_path="path/to.kicad_sch",
        source_kind="SCH",
        document_id="my-doc",
        canvas={"width_nm": 10, "height_nm": 20},
    )
    out = apply_variant_overlay(doc, policy=KiCadVariantOverlayPolicy())
    assert out.source_path == "path/to.kicad_sch"
    assert out.source_kind == "SCH"
    assert out.document_id == "my-doc"
    assert out.canvas == {"width_nm": 10, "height_nm": 20}


# =============================================================================
# Renderer wiring (extras["variant_state"] -> <g> attrs)
# =============================================================================


def _ctx(mode: KiCadVariantDimMode, opacity: float = 0.6) -> KiCadSvgRenderContext:
    opts = KiCadSvgRenderOptions(
        variant_dim_mode=mode,
        variant_dim_opacity=opacity,
    )
    return KiCadSvgRenderContext(
        sheet_width_nm=100_000_000,
        sheet_height_nm=100_000_000,
        options=opts,
    )


def _circle_record(state: str | None) -> KiCadPlotterRecord:
    op = KiCadPlotterOp.circle(cx=0, cy=0, diameter_nm=10_000_000)
    extras = {} if state is None else {VARIANT_STATE_KEY: state}
    return KiCadPlotterRecord(
        uuid="r", kind="symbol_instance", object_id="R1",
        operations=[op], extras=extras,
    )


def test_render_record_active_no_overlay():
    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY)
    out = render_record(_circle_record(VARIANT_STATE_ACTIVE), ctx=ctx)
    assert "opacity=" not in out
    assert "data-variant-state" not in out


def test_render_record_dimmed_no_overlay_when_mode_NONE():
    ctx = _ctx(KiCadVariantDimMode.NONE)
    out = render_record(_circle_record(VARIANT_STATE_DIMMED), ctx=ctx)
    assert "opacity=" not in out
    assert "filter:" not in out
    assert "data-variant-state" not in out


def test_render_record_dimmed_dim_overlay_emits_opacity():
    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY, opacity=0.4)
    out = render_record(_circle_record(VARIANT_STATE_DIMMED), ctx=ctx)
    assert 'opacity="0.400"' in out
    assert 'data-variant-state="dimmed"' in out


def test_render_record_dimmed_greyscale_emits_filter():
    ctx = _ctx(KiCadVariantDimMode.GREYSCALE)
    out = render_record(_circle_record(VARIANT_STATE_DIMMED), ctx=ctx)
    assert 'filter:grayscale(100%)' in out
    assert 'data-variant-state="dimmed"' in out


def test_render_record_dim_overlay_clamps_opacity_above_one():
    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY, opacity=2.5)
    out = render_record(_circle_record(VARIANT_STATE_DIMMED), ctx=ctx)
    assert 'opacity="1.000"' in out


def test_render_record_dim_overlay_clamps_opacity_below_zero():
    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY, opacity=-0.5)
    out = render_record(_circle_record(VARIANT_STATE_DIMMED), ctx=ctx)
    assert 'opacity="0.000"' in out


def test_render_record_missing_variant_state_no_overlay():
    """Records without variant_state extras render unchanged even
    in DIM_OVERLAY mode — overlay only fires on explicit annotation."""
    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY)
    out = render_record(_circle_record(None), ctx=ctx)
    assert "opacity=" not in out
    assert "data-variant-state" not in out


# =============================================================================
# End-to-end: apply_variant_overlay -> render_record
# =============================================================================


def test_e2e_overlay_then_render_dims_dnp_only():
    """End-to-end: F-8 annotation followed by F-5 render."""
    op = KiCadPlotterOp.circle(cx=0, cy=0, diameter_nm=10_000_000)
    ok = KiCadPlotterRecord(
        uuid="ok", kind="symbol_instance", object_id="R1",
        operations=[op], extras={"dnp": False, "in_bom": True},
    )
    bad = KiCadPlotterRecord(
        uuid="bad", kind="symbol_instance", object_id="R2",
        operations=[op], extras={"dnp": True, "in_bom": True},
    )
    doc = KiCadPlotterDocument(records=[ok, bad])
    annotated = apply_variant_overlay(doc, policy=KiCadVariantOverlayPolicy())

    ctx = _ctx(KiCadVariantDimMode.DIM_OVERLAY, opacity=0.5)
    out_ok = render_record(annotated.records[0], ctx=ctx)
    out_bad = render_record(annotated.records[1], ctx=ctx)

    assert "opacity=" not in out_ok
    assert 'opacity="0.500"' in out_bad
