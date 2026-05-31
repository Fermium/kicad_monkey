"""
L0 unit tests for ``kicad_monkey.kicad_plotter_transform``.

Phase F-6.3 — covers the 2-D coordinate transform module that
re-anchors :class:`KiCadPlotterOp` payloads. Used by F-6.4 symbol-body
composition into ``schematic_to_ir``.
"""

from __future__ import annotations

import math

import pytest

from kicad_monkey import (
    KiCadPlotterTransform2D,
    apply_transform_to_op,
    apply_transform_to_ops,
    transform_orient,
    transform_point,
)
from kicad_monkey.kicad_plotter_ir import (
    KiCadFillType,
    KiCadHorizAlign,
    KiCadPlotterOp,
    KiCadPlotterOpKind,
    KiCadVertAlign,
)


# ---------------------------------------------------------------------------
# Transform dataclass
# ---------------------------------------------------------------------------


def test_default_is_identity():
    T = KiCadPlotterTransform2D()
    assert T.offset_x_nm == 0
    assert T.offset_y_nm == 0
    assert T.rotation_deg == 0.0
    assert T.mirror_x is False
    assert T.mirror_y is False


def test_identity_factory():
    T = KiCadPlotterTransform2D.identity()
    assert T == KiCadPlotterTransform2D()


def test_translation_factory():
    T = KiCadPlotterTransform2D.translation(100, 200)
    assert T.offset_x_nm == 100
    assert T.offset_y_nm == 200
    assert T.rotation_deg == 0.0
    assert T.mirror_x is False
    assert T.mirror_y is False


def test_transform_is_frozen():
    T = KiCadPlotterTransform2D()
    with pytest.raises(Exception):  # FrozenInstanceError
        T.offset_x_nm = 100  # type: ignore[misc]


# ---------------------------------------------------------------------------
# transform_point — identity / translate / rotate / mirror
# ---------------------------------------------------------------------------


def test_transform_point_identity():
    assert transform_point(100, 200, KiCadPlotterTransform2D()) == (100, 200)


def test_transform_point_translate_only():
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20)
    assert transform_point(100, 200, T) == (110, 220)


@pytest.mark.parametrize(
    "angle,inp,exp",
    [
        (0.0, (100, 200), (100, 200)),
        (90.0, (100, 0), (0, 100)),
        (90.0, (0, 100), (-100, 0)),
        (180.0, (100, 200), (-100, -200)),
        (270.0, (100, 0), (0, -100)),
        (360.0, (100, 200), (100, 200)),  # 360 ≡ 0
        (-90.0, (100, 0), (0, -100)),  # -90 ≡ 270
    ],
)
def test_transform_point_rotate_exact_multiples(angle, inp, exp):
    T = KiCadPlotterTransform2D(rotation_deg=angle)
    assert transform_point(*inp, T) == exp


def test_transform_point_rotate_arbitrary_angle():
    # 45 deg rotation of (1000, 0) → (~707, ~707)
    T = KiCadPlotterTransform2D(rotation_deg=45.0)
    out = transform_point(1000, 0, T)
    assert abs(out[0] - 707) <= 1
    assert abs(out[1] - 707) <= 1


def test_transform_point_mirror_x():
    T = KiCadPlotterTransform2D(mirror_x=True)
    assert transform_point(100, 200, T) == (100, -200)


def test_transform_point_mirror_y():
    T = KiCadPlotterTransform2D(mirror_y=True)
    assert transform_point(100, 200, T) == (-100, 200)


def test_transform_point_mirror_both_equals_180_rot():
    T_mirror_both = KiCadPlotterTransform2D(mirror_x=True, mirror_y=True)
    T_rot_180 = KiCadPlotterTransform2D(rotation_deg=180.0)
    p = (100, 200)
    assert transform_point(*p, T_mirror_both) == transform_point(*p, T_rot_180)


def test_transform_point_compose_rotate_then_translate():
    # rotate (100, 0) by 90 → (0, 100); then +(500, 500) → (500, 600)
    T = KiCadPlotterTransform2D(rotation_deg=90.0, offset_x_nm=500, offset_y_nm=500)
    assert transform_point(100, 0, T) == (500, 600)


def test_transform_point_compose_rotate_then_mirror():
    # rotate (100, 0) by 90 → (0, 100); mirror_y → (0, 100)  (X=0 unchanged)
    T = KiCadPlotterTransform2D(rotation_deg=90.0, mirror_y=True)
    assert transform_point(100, 0, T) == (0, 100)
    # rotate (100, 0) by 90 → (0, 100); mirror_x → (0, -100)
    T = KiCadPlotterTransform2D(rotation_deg=90.0, mirror_x=True)
    assert transform_point(100, 0, T) == (0, -100)


def test_transform_point_returns_int_after_rounding():
    # 30 deg of (1000, 0) → cos*1000 = 866.025... ; sin*1000 = 500.0
    T = KiCadPlotterTransform2D(rotation_deg=30.0)
    out = transform_point(1000, 0, T)
    assert isinstance(out[0], int)
    assert isinstance(out[1], int)
    assert out == (866, 500)


# ---------------------------------------------------------------------------
# transform_orient
# ---------------------------------------------------------------------------


def test_transform_orient_identity():
    T = KiCadPlotterTransform2D()
    assert transform_orient(45.0, T) == 45.0


def test_transform_orient_adds_rotation():
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    assert transform_orient(45.0, T) == 135.0


def test_transform_orient_mirror_x_inverts_sign():
    T = KiCadPlotterTransform2D(mirror_x=True)
    assert transform_orient(45.0, T) == -45.0


def test_transform_orient_mirror_y_inverts_sign():
    T = KiCadPlotterTransform2D(mirror_y=True)
    assert transform_orient(45.0, T) == -45.0


def test_transform_orient_double_mirror_cancels():
    T = KiCadPlotterTransform2D(mirror_x=True, mirror_y=True)
    assert transform_orient(45.0, T) == 45.0


# ---------------------------------------------------------------------------
# State ops pass through untouched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "SetColor",
        "SetCurrentLineWidth",
        "SetDash",
        "SetViewport",
        "SetPageSettings",
        "StartPlot",
        "EndPlot",
        "StartBlock",
        "EndBlock",
    ],
)
def test_state_ops_pass_through_unchanged(kind):
    op = KiCadPlotterOp(kind=KiCadPlotterOpKind(kind), payload={"some": "value"})
    T = KiCadPlotterTransform2D(offset_x_nm=1000, offset_y_nm=2000, rotation_deg=90)
    out = apply_transform_to_op(op, T)
    assert out.kind.value == kind
    assert out.payload == {"some": "value"}


def test_state_op_payload_is_deep_copied():
    op = KiCadPlotterOp(
        kind=KiCadPlotterOpKind("SetDash"), payload={"line_style": "SOLID", "nested": [1, 2]}
    )
    T = KiCadPlotterTransform2D()
    out = apply_transform_to_op(op, T)
    out.payload["nested"].append(3)
    assert op.payload["nested"] == [1, 2]


# ---------------------------------------------------------------------------
# Per-op-kind coordinate transforms
# ---------------------------------------------------------------------------


def test_apply_pen_to():
    op = KiCadPlotterOp.pen_to(x=100, y=200)
    out = apply_transform_to_op(op, KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20))
    assert out.payload["x"] == 110
    assert out.payload["y"] == 220
    assert out.payload["action"] == op.payload["action"]


def test_apply_circle_translates_center_preserves_diameter():
    op = KiCadPlotterOp.circle(cx=100, cy=200, diameter_nm=500, width_nm=10)
    T = KiCadPlotterTransform2D(offset_x_nm=1000, offset_y_nm=2000)
    out = apply_transform_to_op(op, T)
    assert out.payload["cx"] == 1100
    assert out.payload["cy"] == 2200
    assert out.payload["diameter_nm"] == 500
    assert out.payload["width_nm"] == 10


def test_apply_arc_three_point_transforms_all_three():
    op = KiCadPlotterOp.arc_three_point(
        start_x=10, start_y=0, mid_x=0, mid_y=10, end_x=-10, end_y=0
    )
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    assert out.payload["start_x"] == 0 and out.payload["start_y"] == 10
    assert out.payload["mid_x"] == -10 and out.payload["mid_y"] == 0
    assert out.payload["end_x"] == 0 and out.payload["end_y"] == -10


def test_apply_arc_center_angle_rotates_start_angle():
    op = KiCadPlotterOp.arc_center_angle(
        cx=0, cy=0, start_angle_deg=10.0, sweep_deg=30.0, radius_nm=100
    )
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    assert out.payload["start_angle_deg"] == 100.0
    assert out.payload["sweep_deg"] == 30.0  # no mirror → unchanged
    assert out.payload["radius_nm"] == 100


def test_apply_arc_center_angle_single_mirror_flips_sweep():
    op = KiCadPlotterOp.arc_center_angle(
        cx=0, cy=0, start_angle_deg=0.0, sweep_deg=30.0, radius_nm=100
    )
    out = apply_transform_to_op(op, KiCadPlotterTransform2D(mirror_x=True))
    assert out.payload["sweep_deg"] == -30.0


def test_apply_arc_center_angle_double_mirror_keeps_sweep():
    op = KiCadPlotterOp.arc_center_angle(
        cx=0, cy=0, start_angle_deg=0.0, sweep_deg=30.0, radius_nm=100
    )
    T = KiCadPlotterTransform2D(mirror_x=True, mirror_y=True)
    out = apply_transform_to_op(op, T)
    assert out.payload["sweep_deg"] == 30.0


def test_apply_bezier_curve_transforms_all_four_points():
    op = KiCadPlotterOp.bezier_curve(
        start_x=0, start_y=0,
        ctrl1_x=100, ctrl1_y=0,
        ctrl2_x=200, ctrl2_y=100,
        end_x=300, end_y=100,
    )
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20)
    out = apply_transform_to_op(op, T)
    assert (out.payload["start_x"], out.payload["start_y"]) == (10, 20)
    assert (out.payload["ctrl1_x"], out.payload["ctrl1_y"]) == (110, 20)
    assert (out.payload["ctrl2_x"], out.payload["ctrl2_y"]) == (210, 120)
    assert (out.payload["end_x"], out.payload["end_y"]) == (310, 120)


def test_apply_rect_transforms_both_corners():
    op = KiCadPlotterOp.rect(x1=0, y1=0, x2=100, y2=200, corner_radius_nm=5, width_nm=2)
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20)
    out = apply_transform_to_op(op, T)
    assert out.payload["x1"] == 10
    assert out.payload["y1"] == 20
    assert out.payload["x2"] == 110
    assert out.payload["y2"] == 220
    assert out.payload["corner_radius_nm"] == 5
    assert out.payload["width_nm"] == 2


def test_apply_plot_poly_transforms_all_points():
    op = KiCadPlotterOp.plot_poly(points=[[0, 0], [100, 0], [100, 100]])
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    assert out.payload["points"] == [[0, 0], [0, 100], [-100, 100]]


def test_apply_plot_poly_preserves_fill_and_width():
    op = KiCadPlotterOp.plot_poly(
        points=[[0, 0], [10, 10]],
        fill=KiCadFillType.FILLED_SHAPE,
        width_nm=42,
    )
    out = apply_transform_to_op(op, KiCadPlotterTransform2D())
    assert out.payload["fill"] == KiCadFillType.FILLED_SHAPE.value
    assert out.payload["width_nm"] == 42


def test_apply_text_transforms_position_and_orient():
    op = KiCadPlotterOp.text(
        x=100, y=200, text="hi",
        size_x_nm=1000, size_y_nm=1000,
        orient_deg=45.0,
    )
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20, rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    # rotate (100, 200) by 90 → (-200, 100); + (10, 20) → (-190, 120)
    assert out.payload["x"] == -190
    assert out.payload["y"] == 120
    assert out.payload["orient_deg"] == 135.0
    assert out.payload["text"] == "hi"


def test_apply_thick_segment():
    op = KiCadPlotterOp.thick_segment(start_x=0, start_y=0, end_x=100, end_y=0, width_nm=5)
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20)
    out = apply_transform_to_op(op, T)
    assert (out.payload["start_x"], out.payload["start_y"]) == (10, 20)
    assert (out.payload["end_x"], out.payload["end_y"]) == (110, 20)
    assert out.payload["width_nm"] == 5


def test_apply_thick_arc():
    op = KiCadPlotterOp.thick_arc(
        cx=0, cy=0, start_angle_deg=0.0, sweep_deg=90.0, radius_nm=100, width_nm=5
    )
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    assert out.payload["cx"] == 0
    assert out.payload["cy"] == 0
    assert out.payload["start_angle_deg"] == 90.0


def test_apply_plot_image():
    op = KiCadPlotterOp.plot_image(x=10, y=20, width_nm=100, height_nm=50)
    out = apply_transform_to_op(op, KiCadPlotterTransform2D(offset_x_nm=5, offset_y_nm=7))
    assert out.payload["x"] == 15
    assert out.payload["y"] == 27
    assert out.payload["width_nm"] == 100
    assert out.payload["height_nm"] == 50


def test_apply_flash_pad_circle():
    op = KiCadPlotterOp.flash_pad_circle(x=10, y=20, diameter_nm=300)
    out = apply_transform_to_op(op, KiCadPlotterTransform2D(offset_x_nm=1, offset_y_nm=2))
    assert (out.payload["x"], out.payload["y"]) == (11, 22)
    assert out.payload["diameter_nm"] == 300


def test_apply_flash_pad_rect_translates_position_and_orient():
    op = KiCadPlotterOp.flash_pad_rect(
        x=100, y=200, size_x_nm=50, size_y_nm=30, orient_deg=15.0
    )
    T = KiCadPlotterTransform2D(rotation_deg=90.0)
    out = apply_transform_to_op(op, T)
    assert (out.payload["x"], out.payload["y"]) == (-200, 100)
    assert out.payload["orient_deg"] == 105.0


def test_apply_flash_pad_custom_transforms_polygons():
    op = KiCadPlotterOp.flash_pad_custom(
        x=0, y=0, size_x_nm=50, size_y_nm=30, orient_deg=0.0,
        polygons=[[[0, 0], [10, 0], [10, 10]]],
    )
    T = KiCadPlotterTransform2D(offset_x_nm=100, offset_y_nm=200)
    out = apply_transform_to_op(op, T)
    assert out.payload["polygons"] == [[[100, 200], [110, 200], [110, 210]]]
    assert (out.payload["x"], out.payload["y"]) == (100, 200)


def test_apply_flash_pad_trapez_transforms_corners():
    op = KiCadPlotterOp.flash_pad_trapez(
        x=0, y=0,
        corners=[[0, 0], [10, 0], [10, 10], [0, 10]],
        orient_deg=0.0,
    )
    T = KiCadPlotterTransform2D(offset_x_nm=100, offset_y_nm=200)
    out = apply_transform_to_op(op, T)
    assert out.payload["corners"] == [[100, 200], [110, 200], [110, 210], [100, 210]]


def test_apply_flash_reg_polygon():
    op = KiCadPlotterOp.flash_reg_polygon(
        x=10, y=20, diameter_nm=100, corner_count=6, orient_deg=0.0
    )
    T = KiCadPlotterTransform2D(offset_x_nm=1, offset_y_nm=2, rotation_deg=180.0)
    out = apply_transform_to_op(op, T)
    # rotate (10,20) by 180 → (-10, -20); + (1,2) → (-9, -18)
    assert (out.payload["x"], out.payload["y"]) == (-9, -18)
    assert out.payload["orient_deg"] == 180.0
    assert out.payload["corner_count"] == 6
    assert out.payload["diameter_nm"] == 100


# ---------------------------------------------------------------------------
# apply_transform_to_ops batch helper
# ---------------------------------------------------------------------------


def test_apply_transform_to_ops_returns_new_list():
    ops = [
        KiCadPlotterOp.pen_to(x=10, y=20),
        KiCadPlotterOp.circle(cx=0, cy=0, diameter_nm=100),
    ]
    T = KiCadPlotterTransform2D(offset_x_nm=1, offset_y_nm=2)
    out = apply_transform_to_ops(ops, T)
    assert len(out) == 2
    assert out[0].payload["x"] == 11
    assert out[1].payload["cx"] == 1


def test_apply_transform_to_ops_does_not_mutate_input():
    ops = [KiCadPlotterOp.pen_to(x=10, y=20)]
    T = KiCadPlotterTransform2D(offset_x_nm=100, offset_y_nm=200)
    apply_transform_to_ops(ops, T)
    assert ops[0].payload["x"] == 10
    assert ops[0].payload["y"] == 20


def test_apply_transform_to_ops_empty_list():
    assert apply_transform_to_ops([], KiCadPlotterTransform2D()) == []


# ---------------------------------------------------------------------------
# Identity is a no-op for all op kinds in the IR
# ---------------------------------------------------------------------------


def test_identity_transform_preserves_pen_to():
    op = KiCadPlotterOp.pen_to(x=100, y=200)
    out = apply_transform_to_op(op, KiCadPlotterTransform2D())
    assert out.payload == op.payload


def test_identity_transform_preserves_plot_poly():
    op = KiCadPlotterOp.plot_poly(points=[[0, 0], [10, 10]])
    out = apply_transform_to_op(op, KiCadPlotterTransform2D())
    assert out.payload == op.payload


def test_identity_transform_creates_independent_payload():
    op = KiCadPlotterOp.plot_poly(points=[[0, 0], [10, 10]])
    out = apply_transform_to_op(op, KiCadPlotterTransform2D())
    out.payload["points"].append([99, 99])
    assert op.payload["points"] == [[0, 0], [10, 10]]


# ---------------------------------------------------------------------------
# Unknown op kinds: forward-compat passthrough
# ---------------------------------------------------------------------------


def test_unknown_op_kind_passes_through():
    # IR allows raw-string kinds for forward-compat
    op = KiCadPlotterOp(kind="FutureOp", payload={"x": 100, "y": 200, "extra": "z"})
    T = KiCadPlotterTransform2D(offset_x_nm=10, offset_y_nm=20)
    out = apply_transform_to_op(op, T)
    # We don't know which keys are coords; preserve unchanged.
    assert out.payload == {"x": 100, "y": 200, "extra": "z"}
