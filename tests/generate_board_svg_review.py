"""Generate a pan/zoom review page for KiCad board SVG references."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from generate_cli_svg_comparison import (
    _PANZOOM_CSS,
    _PANZOOM_JS,
    _default_kicad_root,
    _html,
    _inline_script_block,
    _panzoom_figure,
    _rel_href,
    _svg_pan_zoom_script,
)
from synthetic_board_svg_oracle import export_svg_with_kicad_cli, find_kicad_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_KICAD_MONKEY_SRC = REPO_ROOT / "src" / "py"
if LOCAL_KICAD_MONKEY_SRC.exists() and str(LOCAL_KICAD_MONKEY_SRC) not in sys.path:
    sys.path.insert(0, str(LOCAL_KICAD_MONKEY_SRC))


TEST_LAYERS = [
    "F.Cu",
    "B.Cu",
    "In1.Cu",
    "In2.Cu",
    "F.SilkS",
    "B.SilkS",
    "F.Fab",
    "B.Fab",
    "F.Mask",
    "B.Mask",
    "F.Paste",
    "B.Paste",
    "F.CrtYd",
    "B.CrtYd",
    "Edge.Cuts",
    "User.Drawings",
    "User.Comments",
    "All Layers",
]

ALL_LAYERS_LIST = [
    "F.Cu",
    "B.Cu",
    "F.SilkS",
    "B.SilkS",
    "F.Fab",
    "B.Fab",
    "F.Mask",
    "B.Mask",
    "F.CrtYd",
    "B.CrtYd",
    "Edge.Cuts",
    "User.Drawings",
    "User.Comments",
]

LAYER_TOKEN_TO_NAME = {layer.replace(".", "_").replace(" ", "_"): layer for layer in TEST_LAYERS}


@dataclass(frozen=True)
class BoardReviewPair:
    case_id: str
    board_name: str
    layer: str
    reference_svg: Path
    monkey_svg: Path
    metrics: dict[str, Any]


@dataclass(frozen=True)
class BoardReviewGroup:
    case_id: str
    board_name: str
    pairs: list[BoardReviewPair]


LAYER_SORT_INDEX = {layer: index for index, layer in enumerate(TEST_LAYERS)}


def _reset_generated_assets(path: Path, *, review_dir: Path) -> None:
    resolved_path = path.resolve()
    resolved_review = review_dir.resolve()
    try:
        resolved_path.relative_to(resolved_review)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to clear assets outside review dir: {path}") from exc
    if resolved_path.exists():
        shutil.rmtree(resolved_path)
    path.mkdir(parents=True, exist_ok=True)


def _shape_counts(svg: str) -> dict[str, int]:
    return {
        "paths": svg.count("<path"),
        "circles": svg.count("<circle"),
        "polygons": svg.count("<polygon"),
        "rects": svg.count("<rect"),
        "lines": svg.count("<line"),
        "texts": svg.count("<text"),
        "images": svg.count("<image"),
    }


def _layer_from_reference_name(path: Path, board_name: str) -> str | None:
    prefix = f"{board_name}__"
    if not path.stem.startswith(prefix):
        return None
    token = path.stem[len(prefix) :]
    return LAYER_TOKEN_TO_NAME.get(token)


def _board_for_reference(input_dir: Path, case_id: str, ref_path: Path) -> Path | None:
    for board_path in sorted((input_dir / case_id).glob("*.kicad_pcb")):
        if ref_path.stem.startswith(f"{board_path.stem}__"):
            return board_path
    return None


def _layers_to_render(layer: str) -> list[str]:
    if layer == "All Layers":
        return list(ALL_LAYERS_LIST)
    layers = [layer]
    if layer != "Edge.Cuts":
        layers.append("Edge.Cuts")
    return layers


def _reference_output_path(ref_path: Path, *, dest_root: Path, case_id: str) -> Path:
    dest_dir = dest_root / case_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / ref_path.name


def _copy_reference(ref_path: Path, *, dest_root: Path, case_id: str) -> Path:
    dest = _reference_output_path(ref_path, dest_root=dest_root, case_id=case_id)
    shutil.copy2(ref_path, dest)
    return dest


def _render_monkey_svg(board_path: Path, layer: str, out_path: Path) -> str:
    from kicad_monkey import KiCadPcb

    pcb = KiCadPcb.from_file(board_path)
    svg = pcb.to_svg(layers=_layers_to_render(layer))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return svg


def _build_pairs(
    *,
    kicad_root: Path,
    assets_dir: Path,
    cases: set[str] | None,
    max_pairs: int | None,
    live_cli: bool = False,
) -> list[BoardReviewPair]:
    input_dir = kicad_root / "board_svg" / "input"
    reference_dir = kicad_root / "board_svg" / "reference_output"
    reference_assets = assets_dir / "reference"
    monkey_assets = assets_dir / "monkey"
    kicad_cli = find_kicad_cli() if live_cli else None
    if live_cli and kicad_cli is None:
        raise RuntimeError("No PCB-capable kicad-cli found for live board SVG review")

    pairs: list[BoardReviewPair] = []
    for ref_path in sorted(reference_dir.glob("*/*.svg")):
        case_id = ref_path.parent.name
        if cases and case_id not in cases:
            continue
        board_path = _board_for_reference(input_dir, case_id, ref_path)
        if board_path is None:
            continue
        board_name = board_path.stem
        layer = _layer_from_reference_name(ref_path, board_name)
        if layer is None:
            continue

        if live_cli:
            copied_ref = _reference_output_path(
                ref_path,
                dest_root=reference_assets,
                case_id=case_id,
            )
            export_svg_with_kicad_cli(
                kicad_cli=kicad_cli,
                board_path=board_path,
                layers=_layers_to_render(layer),
                output_path=copied_ref,
            )
        else:
            copied_ref = _copy_reference(ref_path, dest_root=reference_assets, case_id=case_id)
        monkey_svg_path = monkey_assets / case_id / ref_path.name
        monkey_svg = _render_monkey_svg(board_path, layer, monkey_svg_path)
        ref_svg = copied_ref.read_text(encoding="utf-8")
        ref_counts = _shape_counts(ref_svg)
        monkey_counts = _shape_counts(monkey_svg)
        metrics = {
            "reference": ref_counts,
            "monkey": monkey_counts,
            "delta": {
                key: monkey_counts.get(key, 0) - ref_counts.get(key, 0)
                for key in sorted(set(ref_counts) | set(monkey_counts))
            },
        }
        pairs.append(
            BoardReviewPair(
                case_id=case_id,
                board_name=board_name,
                layer=layer,
                reference_svg=copied_ref,
                monkey_svg=monkey_svg_path,
                metrics=metrics,
            )
        )
        if max_pairs is not None and len(pairs) >= max_pairs:
            break
    return pairs


def _group_pairs(pairs: list[BoardReviewPair]) -> list[BoardReviewGroup]:
    grouped: dict[tuple[str, str], list[BoardReviewPair]] = {}
    for pair in pairs:
        grouped.setdefault((pair.case_id, pair.board_name), []).append(pair)

    groups: list[BoardReviewGroup] = []
    for (case_id, board_name), group_pairs in sorted(grouped.items()):
        groups.append(
            BoardReviewGroup(
                case_id=case_id,
                board_name=board_name,
                pairs=sorted(
                    group_pairs,
                    key=lambda pair: (LAYER_SORT_INDEX.get(pair.layer, 999), pair.layer),
                ),
            )
        )
    return groups


def _render_metric_table(pair: BoardReviewPair) -> str:
    rows = []
    keys = sorted(set(pair.metrics["reference"]) | set(pair.metrics["monkey"]))
    for key in keys:
        rows.append(
            "<tr>"
            f"<td>{_html(key)}</td>"
            f"<td>{pair.metrics['reference'].get(key, 0)}</td>"
            f"<td>{pair.metrics['monkey'].get(key, 0)}</td>"
            f"<td>{pair.metrics['delta'].get(key, 0)}</td>"
            "</tr>"
        )
    return (
        "<table class=\"mini\"><thead><tr><th>Shape</th><th>KiCad</th>"
        "<th>kicad_monkey</th><th>Delta</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_html(
    *,
    kicad_root: Path,
    output_path: Path,
    pairs: list[BoardReviewPair],
    live_cli: bool,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    options: list[str] = []
    rows: list[str] = []
    cards: list[str] = []
    groups = _group_pairs(pairs)

    for index, group in enumerate(groups):
        token = f"{group.case_id}::{group.board_name}"
        label = f"{group.case_id} / {group.board_name} ({len(group.pairs)} layers)"
        selected = " selected" if index == 0 else ""
        options.append(f'<option value="{_html(token)}"{selected}>{_html(label)}</option>')
        layer_names = ", ".join(pair.layer for pair in group.pairs)
        rows.append(
            "<tr>"
            f"<td>{_html(group.case_id)}</td>"
            f"<td>{_html(group.board_name)}</td>"
            f"<td>{len(group.pairs)}</td>"
            f"<td>{_html(layer_names)}</td>"
            "</tr>"
        )
        layer_cards: list[str] = []
        for pair in group.pairs:
            ref_href = _rel_href(pair.reference_svg, from_dir=output_path.parent)
            monkey_href = _rel_href(pair.monkey_svg, from_dir=output_path.parent)
            layer_cards.append(
                "<div class=\"layer-card\">"
                f"<h3>{_html(pair.layer)}</h3>"
                f"<div class=\"links\"><a href=\"{_html(ref_href)}\" target=\"_blank\" rel=\"noreferrer\">KiCad CLI SVG</a>"
                f"<a href=\"{_html(monkey_href)}\" target=\"_blank\" rel=\"noreferrer\">kicad_monkey SVG</a></div>"
                f"{_render_metric_table(pair)}"
                "<div class=\"viewers board-layer-viewers\">"
                f"{_panzoom_figure('KiCad CLI reference', ref_href)}"
                f"{_panzoom_figure('kicad_monkey', monkey_href)}"
                "</div>"
                "</div>"
            )
        hidden = "" if index == 0 else " hidden"
        cards.append(
            f'<section class="board-card" data-board-card="{_html(token)}"{hidden}>'
            f"<h2>{_html(group.case_id)}</h2>"
            f"<p class=\"meta\"><code>{_html(group.board_name)}</code> "
            f"{len(group.pairs)} rendered layer views.</p>"
            f"{''.join(layer_cards)}"
            "</section>"
        )

    selector_js = """
(() => {
  window.addEventListener('DOMContentLoaded', () => {
    const select = document.getElementById('board-select');
    const cards = Array.from(document.querySelectorAll('[data-board-card]'));
    function showSelected() {
      const value = select.value;
      cards.forEach((card) => { card.hidden = card.dataset.boardCard !== value; });
      if (window.kicadReviewLoadVisibleSvgs) {
        window.kicadReviewLoadVisibleSvgs();
      }
    }
    select.addEventListener('change', showSelected);
    showSelected();
  });
})();
"""
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>KiCad Board SVG Review</title>",
            "<style>",
            _PANZOOM_CSS,
            ".board-card[hidden] { display: none; }",
            ".board-card { margin-top: 12px; }",
            ".board-index { margin: 12px 0; }",
            ".board-index > summary { cursor: pointer; font-weight: 600; }",
            ".board-index table { margin-bottom: 0; }",
            ".layer-card { border-top: 1px solid #d9e2ec; padding: 12px 0 18px; }",
            ".layer-card:first-of-type { border-top: 0; }",
            ".layer-card > h3 { margin: 0; padding: 0 16px 6px; font-size: 16px; }",
            ".board-layer-viewers { height: 800px; min-height: 800px; overflow: hidden; }",
            "@media (max-width: 720px) { .board-layer-viewers { height: 640px; min-height: 640px; } }",
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>KiCad Board SVG Review</h1>",
            (
                f"<p class=\"meta\">Generated {_html(generated)} from "
                f"<code>{_html(kicad_root)}</code>. Boards: {len(groups)}; layer pairs: {len(pairs)}. "
                f"Reference source: {'live kicad-cli' if live_cli else 'stored corpus reference'}.</p>"
            ),
            "<div class=\"review-controls\">",
            "<label for=\"board-select\">Board</label>",
            f"<select id=\"board-select\">{''.join(options)}</select>",
            "</div>",
            "</header>",
            "<main>",
            "<details class=\"board-index\"><summary>Board/layer index</summary>"
            "<table><thead><tr><th>Case</th><th>Board</th><th>Layer count</th>"
            "<th>Layers</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></details>",
            *cards,
            "</main>",
            _inline_script_block(_svg_pan_zoom_script()),
            _inline_script_block(f"{_PANZOOM_JS}\n{selector_js}"),
            "</body>",
            "</html>",
        ]
    ) + "\n"


def generate_board_review(
    *,
    kicad_root: Path,
    output_path: Path | None = None,
    cases: list[str] | None = None,
    max_pairs: int | None = None,
    live_cli: bool = False,
) -> Path:
    review_dir = kicad_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_path or (review_dir / "board_svg_review.html")
    assets_dir = review_dir / output_path.stem
    _reset_generated_assets(assets_dir, review_dir=review_dir)

    pairs = _build_pairs(
        kicad_root=kicad_root,
        assets_dir=assets_dir,
        cases=set(cases or []) or None,
        max_pairs=max_pairs,
        live_cli=live_cli,
    )
    if not pairs:
        raise RuntimeError("No board SVG review pairs found")

    output_path.write_text(
        _render_html(
            kicad_root=kicad_root,
            output_path=output_path,
            pairs=pairs,
            live_cli=live_cli,
        ),
        encoding="utf-8",
    )
    groups = _group_pairs(pairs)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_source": "live_kicad_cli" if live_cli else "stored_corpus_reference",
        "board_count": len(groups),
        "pair_count": len(pairs),
        "boards": [
            {
                "case_id": group.case_id,
                "board_name": group.board_name,
                "layers": [pair.layer for pair in group.pairs],
            }
            for group in groups
        ],
        "pairs": [
            {
                "case_id": pair.case_id,
                "board_name": pair.board_name,
                "layer": pair.layer,
                "reference_svg": str(pair.reference_svg),
                "monkey_svg": str(pair.monkey_svg),
                "metrics": pair.metrics,
            }
            for pair in pairs
        ],
    }
    (review_dir / "board_svg_review.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-root", type=Path, default=_default_kicad_root())
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path. Defaults to <kicad-root>/review/board_svg_review.html.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Restrict to a board_svg case folder. May be repeated.",
    )
    parser.add_argument("--max-pairs", type=int, default=None)
    parser.add_argument(
        "--live-cli",
        action="store_true",
        help="Regenerate reference SVGs with a PCB-capable kicad-cli instead of copying stored references.",
    )
    args = parser.parse_args()
    path = generate_board_review(
        kicad_root=args.kicad_root,
        output_path=args.output,
        cases=args.cases,
        max_pairs=args.max_pairs,
        live_cli=args.live_cli,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
