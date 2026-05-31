"""
KiCad variant overlay.

Annotates schematic, symbol, and footprint IR records with a
``variant_state`` extras key (``"active"`` or ``"dimmed"``) so SVG rendering can
visually de-emphasise items that participate in a build variant
exclusion (DNP / exclude-from-bom / exclude-from-sim / exclude-from-pos).

The core piece is a small policy :class:`KiCadVariantOverlayPolicy` that says
*which* exclusion axes trigger dimming, plus three helpers:

  * :func:`compute_record_variant_state` -- pure classification, no copy
  * :func:`annotate_record_variant_state` -- returns a copy with
    ``extras["variant_state"]`` set
  * :func:`apply_variant_overlay` -- whole-document pass

Source of the per-record flags:

  * ``symbol_instance`` records carry ``dnp``, ``in_bom``,
    ``exclude_from_sim``, ``in_pos_files`` in their ``extras``. Note
    that KiCad models *inclusion* for BOM and POS, so "excluded from
    BOM" maps to ``in_bom == False``.
  * ``footprint`` records carry the raw ``attr`` token list in
    their ``extras``. KiCad PCB attribute tokens of interest are
    ``dnp``, ``exclude_from_bom`` and ``exclude_from_pos``. (PCB
    footprints have no exclude-from-sim concept.)

Records of any other kind (wires, labels, sheets, drawing-sheet
borders, ...) are always classified as ``"active"`` -- variant flags
are an instance-level concept, not a sheet-geometry one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .kicad_plotter_ir import KiCadPlotterDocument, KiCadPlotterRecord


# =============================================================================
# Public constants
# =============================================================================


VARIANT_STATE_KEY = "variant_state"
VARIANT_STATE_ACTIVE = "active"
VARIANT_STATE_DIMMED = "dimmed"


# =============================================================================
# Policy
# =============================================================================


@dataclass(frozen=True)
class KiCadVariantOverlayPolicy:
    """
    Which exclusion axes trigger ``variant_state == "dimmed"``.

    Each flag defaults to a sensible "assembly-style" value: DNP
    components are dimmed, BOM-only / SIM-only / POS-only exclusions
    are not. Use one of the named factories below for common profiles.
    """

    dim_dnp: bool = True
    dim_exclude_from_bom: bool = False
    dim_exclude_from_sim: bool = False
    dim_exclude_from_pos: bool = False

    @classmethod
    def assembly_view(cls) -> "KiCadVariantOverlayPolicy":
        """Dim DNP and POS-excluded items (typical fab/assembly view)."""
        return cls(
            dim_dnp=True,
            dim_exclude_from_bom=False,
            dim_exclude_from_sim=False,
            dim_exclude_from_pos=True,
        )

    @classmethod
    def bom_view(cls) -> "KiCadVariantOverlayPolicy":
        """Dim DNP and BOM-excluded items."""
        return cls(
            dim_dnp=True,
            dim_exclude_from_bom=True,
            dim_exclude_from_sim=False,
            dim_exclude_from_pos=False,
        )

    @classmethod
    def all_axes(cls) -> "KiCadVariantOverlayPolicy":
        """Dim items excluded along any of the four axes."""
        return cls(
            dim_dnp=True,
            dim_exclude_from_bom=True,
            dim_exclude_from_sim=True,
            dim_exclude_from_pos=True,
        )


# =============================================================================
# Per-kind classifiers
# =============================================================================


def _symbol_instance_dimmed(
    extras: Mapping[str, Any],
    policy: KiCadVariantOverlayPolicy,
) -> bool:
    """Apply ``policy`` to ``symbol_instance`` extras."""
    if policy.dim_dnp and bool(extras.get("dnp", False)):
        return True
    # KiCad stores INCLUSION for BOM / POS — not-in == excluded.
    if policy.dim_exclude_from_bom and not bool(extras.get("in_bom", True)):
        return True
    if policy.dim_exclude_from_sim and bool(extras.get("exclude_from_sim", False)):
        return True
    if policy.dim_exclude_from_pos and not bool(extras.get("in_pos_files", True)):
        return True
    return False


def _footprint_dimmed(
    extras: Mapping[str, Any],
    policy: KiCadVariantOverlayPolicy,
) -> bool:
    """Apply ``policy`` to ``footprint`` extras (``attr`` token list)."""
    raw_attrs = extras.get("attr") or []
    attr_set = {str(token).lower() for token in raw_attrs}
    if policy.dim_dnp and "dnp" in attr_set:
        return True
    if policy.dim_exclude_from_bom and "exclude_from_bom" in attr_set:
        return True
    if policy.dim_exclude_from_pos and "exclude_from_pos" in attr_set:
        return True
    # Footprints don't carry exclude_from_sim (sim is a SCH-only concept).
    return False


# =============================================================================
# Public API
# =============================================================================


def compute_record_variant_state(
    record: KiCadPlotterRecord,
    *,
    policy: KiCadVariantOverlayPolicy,
) -> str:
    """
    Classify ``record`` against ``policy``.

    Returns ``VARIANT_STATE_DIMMED`` if the record's ``extras`` match
    any axis enabled in ``policy``, else ``VARIANT_STATE_ACTIVE``.
    Records whose ``kind`` isn't a variant-bearing instance always
    classify as active.
    """
    extras = record.extras or {}
    if record.kind == "symbol_instance":
        if _symbol_instance_dimmed(extras, policy):
            return VARIANT_STATE_DIMMED
    elif record.kind == "footprint":
        if _footprint_dimmed(extras, policy):
            return VARIANT_STATE_DIMMED
    return VARIANT_STATE_ACTIVE


def annotate_record_variant_state(
    record: KiCadPlotterRecord,
    *,
    policy: KiCadVariantOverlayPolicy,
) -> KiCadPlotterRecord:
    """
    Return a copy of ``record`` with ``extras["variant_state"]`` set.

    Records are frozen; this rebuilds the record via
    :func:`dataclasses.replace` with a shallow-copied ``extras`` dict
    so the original record is left untouched.
    """
    state = compute_record_variant_state(record, policy=policy)
    new_extras = dict(record.extras or {})
    new_extras[VARIANT_STATE_KEY] = state
    return replace(record, extras=new_extras)


def apply_variant_overlay(
    doc: KiCadPlotterDocument,
    *,
    policy: KiCadVariantOverlayPolicy,
) -> KiCadPlotterDocument:
    """Annotate every record in ``doc`` with its computed variant state."""
    new_records = [
        annotate_record_variant_state(rec, policy=policy)
        for rec in doc.records
    ]
    return replace(doc, records=new_records)


__all__ = [
    "KiCadVariantOverlayPolicy",
    "VARIANT_STATE_ACTIVE",
    "VARIANT_STATE_DIMMED",
    "VARIANT_STATE_KEY",
    "annotate_record_variant_state",
    "apply_variant_overlay",
    "compute_record_variant_state",
]
