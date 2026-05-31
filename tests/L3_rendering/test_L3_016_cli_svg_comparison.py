"""L3 downstream schematic SVG comparison against kicad-cli."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from kicad_cli_resolver import resolve_kicad_cli


def test_cli_svg_comparison_smoke_writes_text_image_and_overlay_artifacts(tmp_path: Path) -> None:
    from generate_cli_svg_comparison import (
        SVG_PAN_ZOOM_VENDOR_CANDIDATES,
        generate_comparison,
    )
    from kicad_monkey.testing.corpus import get_kicad_corpus_root

    if resolve_kicad_cli() is None:
        pytest.skip("kicad-cli not found - skipping downstream SVG comparison smoke")
    if not any(path.exists() and path.stat().st_size > 10_000 for path in SVG_PAN_ZOOM_VENDOR_CANDIDATES):
        pytest.skip("svg-pan-zoom vendor asset not found - skipping downstream SVG comparison smoke")

    try:
        kicad_root = get_kicad_corpus_root()
    except Exception as exc:
        pytest.skip(f"KiCad corpus unavailable: {exc}")

    report_path = generate_comparison(
        kicad_root=kicad_root,
        output_path=tmp_path / "cli_svg_compare.html",
        cases=["charge_indicator"],
        max_sheets_per_case=1,
        timeout_s=240,
    )
    assert report_path.exists()

    payload = json.loads((tmp_path / "cli_svg_compare.json").read_text(encoding="utf-8"))
    assert payload["aggregate"]["case_count"] == 1
    assert payload["aggregate"]["pair_count"] == 1

    pair = payload["cases"][0]["pairs"][0]
    assert Path(pair["kicad_cli_svg"]).exists()
    assert Path(pair["monkey_svg"]).exists()
    overlay_svg = Path(pair["overlay_svg"])
    assert overlay_svg.exists()
    overlay_text = overlay_svg.read_text(encoding="utf-8")
    assert 'xmlns:xlink="http://www.w3.org/1999/xlink"' in overlay_text
    ET.fromstring(overlay_text)
    assert pair["metrics"]["bounds_passed"] is True
    assert pair["metrics"]["text"]["reference_count"] > 0
    assert "max_distance_mm" in pair["metrics"]["text"]
    assert "max_position_delta_mm" in pair["metrics"]["images"]


def test_cli_svg_text_compare_collapses_duplicate_overdraw(tmp_path: Path) -> None:
    from generate_cli_svg_comparison import _compare_text

    ref = tmp_path / "ref.svg"
    gen = tmp_path / "gen.svg"
    ref.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text x="10" y="20" font-size="1.27" text-anchor="middle">R1</text>'
        '<text x="10" y="20" font-size="1.27" text-anchor="middle">R1</text>'
        "</svg>",
        encoding="utf-8",
    )
    gen.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text x="10" y="20" font-size="1.27" text-anchor="middle">R1</text>'
        "</svg>",
        encoding="utf-8",
    )

    metrics = _compare_text(ref, gen)

    assert metrics["reference_raw_count"] == 2
    assert metrics["reference_duplicate_count"] == 1
    assert metrics["reference_only_count"] == 0
    assert metrics["generated_only_count"] == 0


def test_cli_svg_text_compare_treats_svg_precision_quantum_as_equivalent(tmp_path: Path) -> None:
    from generate_cli_svg_comparison import _compare_text, _semantic_axis_delta_mm

    ref = tmp_path / "ref.svg"
    gen = tmp_path / "gen.svg"
    ref.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text x="386.8419" y="273.1262" font-size="2.9125" text-anchor="middle">D1</text>'
        "</svg>",
        encoding="utf-8",
    )
    gen.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<text x="386.8426" y="273.1262" font-size="2.9125" text-anchor="middle">D1</text>'
        "</svg>",
        encoding="utf-8",
    )

    metrics = _compare_text(ref, gen)

    assert metrics["matched_count"] == 1
    assert metrics["max_distance_mm"] == 0.0
    assert metrics["max_raw_distance_mm"] == pytest.approx(0.0007)
    assert _semantic_axis_delta_mm(0.0009) == 0.0
    assert _semantic_axis_delta_mm(0.0011) == pytest.approx(0.0011)


def test_cli_svg_image_intrinsic_reads_bmp_payload() -> None:
    from generate_cli_svg_comparison import _image_intrinsic_px

    bmp = (
        b"BM"
        + (54).to_bytes(4, "little")
        + b"\x00\x00\x00\x00"
        + (54).to_bytes(4, "little")
        + (40).to_bytes(4, "little")
        + (512).to_bytes(4, "little", signed=True)
        + (256).to_bytes(4, "little", signed=True)
        + (1).to_bytes(2, "little")
        + (24).to_bytes(2, "little")
        + (0).to_bytes(24, "little")
    )
    href = "data:image/bmp;base64," + base64.b64encode(bmp).decode("ascii")

    assert _image_intrinsic_px(href) == (512, 256)


def test_cli_svg_pairing_uses_kicad_display_sheet_path(tmp_path: Path) -> None:
    from generate_cli_svg_comparison import MonkeySheet, _pair_cli_svgs

    root = tmp_path / "Project.kicad_sch"
    cli_root = tmp_path / "Project.svg"
    cli_dac = tmp_path / "Project-DAC, OE, Vref.svg"
    cli_bias = tmp_path / "Project-Bias power.svg"
    cli_nested = tmp_path / "Project-System Architecture-Inputs-DI_TypeB2.svg"

    monkey_sheets = [
        MonkeySheet(1, root, "Project", "Project", "/", "/root", 1, tmp_path / "root.svg"),
        MonkeySheet(
            2,
            Path("Bias_power.kicad_sch"),
            "Bias power",
            "Bias power",
            "/Bias power/",
            "/root/bias",
            3,
            tmp_path / "bias.svg",
        ),
        MonkeySheet(
            3,
            Path("DAC_Vref.kicad_sch"),
            "DAC, OE, Vref",
            "DAC, OE, Vref",
            "/DAC, OE, Vref/",
            "/root/dac",
            3,
            tmp_path / "dac.svg",
        ),
        MonkeySheet(
            4,
            Path("DI_TypeB.kicad_sch"),
            "DI_TypeB2",
            "System Architecture-Inputs-DI_TypeB2",
            "/System Architecture/Inputs/DI_TypeB2/",
            "/root/system/inputs/di2",
            6,
            tmp_path / "di2.svg",
        ),
    ]

    pairs, unpaired_cli, unpaired_monkey = _pair_cli_svgs(
        monkey_sheets=monkey_sheets,
        cli_svgs=[cli_root, cli_dac, cli_bias, cli_nested],
        root_schematic=root,
    )

    assert [pair[1] for pair in pairs] == [cli_root, cli_bias, cli_dac, cli_nested]
    assert unpaired_cli == []
    assert unpaired_monkey == []
