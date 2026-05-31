"""Shared schematic identity helpers."""

from __future__ import annotations

import re


_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_.:-]+")


def schematic_pin_group_id(
    *,
    symbol_uuid: str,
    pin_number: str,
    source_pin_uuid: str = "",
) -> str:
    """Return the SVG group ID for a placed schematic pin."""
    source_pin_uuid = str(source_pin_uuid or "")
    if source_pin_uuid:
        return source_pin_uuid

    symbol_uuid = str(symbol_uuid or "")
    pin_number = str(pin_number or "")
    if not symbol_uuid or not pin_number:
        return ""
    pin_token = _UNSAFE_ID_CHARS.sub("_", pin_number.strip()).strip("_") or "pin"
    return f"{symbol_uuid}__pin__{pin_token}"
