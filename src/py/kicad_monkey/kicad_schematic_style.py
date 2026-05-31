"""KiCad schematic plot-style defaults shared by IR emitters."""

from __future__ import annotations

from typing import Any

DEFAULT_SCHEMATIC_FONT_FACE = "Arial"
DEFAULT_MIN_PLOT_PEN_WIDTH_NM = 84_700
DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM = 152400
DEFAULT_SYMBOL_BODY_STROKE_WIDTH_NM = DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM
DEFAULT_SYMBOL_POLYLINE_STROKE_WIDTH_NM = DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM
DEFAULT_KICAD_DRAWING_SHEET_VERSION_TEXT = "KiCad E.D.A. 10.0.0-912-gf11d3da677-dirty"
DEFAULT_PIN_SYMBOL_RADIUS_NM = 635000

# KiCad default schematic color theme values from
# common/settings/builtin_color_themes.h. Store alpha-bearing hex so recorder
# dumps and declarative IR compare without losing opacity.
LAYER_BUS = "#000084FF"
LAYER_BUS_JUNCTION = "#000084FF"
LAYER_DEVICE = "#840000FF"
LAYER_DEVICE_BACKGROUND = "#FFFFC2FF"
LAYER_DNP_MARKER = "#DC090DD9"
LAYER_FIELDS = "#840084FF"
LAYER_GLOBLABEL = "#840000FF"
LAYER_HIERLABEL = "#725600FF"
LAYER_JUNCTION = "#009600FF"
LAYER_LOCLABEL = "#0F0F0FFF"
LAYER_NOCONNECT = "#000084FF"
LAYER_NOTES = "#0000C2FF"
LAYER_PIN = "#840000FF"
LAYER_PINNAM = "#006464FF"
LAYER_PINNUM = "#A90000FF"
LAYER_REFERENCEPART = "#006464FF"
LAYER_SCHEMATIC_DRAWINGSHEET = "#840000FF"
LAYER_SCHEMATIC_BACKGROUND = "#F5F4EFFF"
LAYER_SHEET = "#840000FF"
LAYER_SHEET_BACKGROUND = "#FFFFFF00"
LAYER_SHEETFIELDS = "#840084FF"
LAYER_SHEETFILENAME = "#725600FF"
LAYER_SHEETLABEL = "#006464FF"
LAYER_SHEETNAME = "#006464FF"
LAYER_VALUEPART = "#006464FF"
LAYER_WIRE = "#009600FF"


def _round_pen_width_nm(value: float) -> int:
    return int(((value / 100.0) + 0.5)) * 100


def apply_default_text_style(
    kwargs: dict[str, Any],
    layer_color: str,
    *,
    clamp_pen_width: bool = True,
) -> dict[str, Any]:
    """Return text kwargs with KiCad CLI default face/color/auto-width filled in."""
    out = dict(kwargs)
    out.setdefault("color", layer_color)
    if not out.get("font_face"):
        out["font_face"] = DEFAULT_SCHEMATIC_FONT_FACE
    if int(out.get("pen_width_nm") or 0) <= 0:
        size_x = int(out.get("size_x_nm") or 0)
        size_y = int(out.get("size_y_nm") or 0)
        if bool(out.get("bold")):
            text_size = min(abs(size_x), abs(size_y))
            if text_size > 0:
                out["pen_width_nm"] = _round_pen_width_nm(text_size / 5.0)
            else:
                out["pen_width_nm"] = DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM
        else:
            out["pen_width_nm"] = DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM
    size_x = int(out.get("size_x_nm") or 0)
    size_y = int(out.get("size_y_nm") or 0)
    text_size = min(abs(size_x), abs(size_y))
    if clamp_pen_width and text_size > 0:
        out["pen_width_nm"] = min(
            int(out.get("pen_width_nm") or 0),
            int((text_size * 0.25) + 0.5),
        )
    return out


def symbol_property_layer_color(key: str) -> str:
    if key == "Reference":
        return LAYER_REFERENCEPART
    if key == "Value":
        return LAYER_VALUEPART
    return LAYER_FIELDS


def sheet_property_layer_color(key: str) -> str:
    if key in {"Sheetname", "Sheet name"}:
        return LAYER_SHEETNAME
    if key in {"Sheetfile", "Sheet file"}:
        return LAYER_SHEETFILENAME
    return LAYER_SHEETFIELDS


__all__ = [
    "DEFAULT_SCHEMATIC_FONT_FACE",
    "DEFAULT_MIN_PLOT_PEN_WIDTH_NM",
    "DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM",
    "DEFAULT_SYMBOL_BODY_STROKE_WIDTH_NM",
    "DEFAULT_SYMBOL_POLYLINE_STROKE_WIDTH_NM",
    "DEFAULT_KICAD_DRAWING_SHEET_VERSION_TEXT",
    "DEFAULT_PIN_SYMBOL_RADIUS_NM",
    "LAYER_BUS",
    "LAYER_BUS_JUNCTION",
    "LAYER_DEVICE",
    "LAYER_DEVICE_BACKGROUND",
    "LAYER_DNP_MARKER",
    "LAYER_FIELDS",
    "LAYER_GLOBLABEL",
    "LAYER_HIERLABEL",
    "LAYER_JUNCTION",
    "LAYER_LOCLABEL",
    "LAYER_NOCONNECT",
    "LAYER_NOTES",
    "LAYER_PIN",
    "LAYER_PINNAM",
    "LAYER_PINNUM",
    "LAYER_REFERENCEPART",
    "LAYER_SCHEMATIC_BACKGROUND",
    "LAYER_SCHEMATIC_DRAWINGSHEET",
    "LAYER_SHEET",
    "LAYER_SHEET_BACKGROUND",
    "LAYER_SHEETFIELDS",
    "LAYER_SHEETFILENAME",
    "LAYER_SHEETLABEL",
    "LAYER_SHEETNAME",
    "LAYER_VALUEPART",
    "LAYER_WIRE",
    "apply_default_text_style",
    "sheet_property_layer_color",
    "symbol_property_layer_color",
]
