"""Generate synthetic board SVG oracle outputs using kicad-cli.

Usage:
    uv run python tools/kicad/tests/generate_synthetic_board_svg_oracles.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from kicad.tests.synthetic_board_svg_oracle import (
    SYNTHETIC_ORACLE_CASES,
    export_svg_with_kicad_cli,
    find_kicad_cli,
    resolve_case_board_path,
    semantic_snapshot,
)

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        log.error("kicad-cli not found")
        return 1

    out_root = Path(__file__).parent / "test_cases" / "svg" / "board" / "synthetic_oracle" / "reference_output"
    out_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, object]] = {}

    for case in SYNTHETIC_ORACLE_CASES:
        board_path = resolve_case_board_path(case)
        if not board_path.exists():
            log.warning("Skipping %s: missing input board %s", case.case_id, board_path)
            continue

        svg_path = out_root / f"{case.case_id}.svg"
        export_svg_with_kicad_cli(
            kicad_cli=kicad_cli,
            board_path=board_path,
            layers=case.layers,
            output_path=svg_path,
        )

        snapshot = semantic_snapshot(svg_path.read_text())
        manifest[case.case_id] = {
            "board_relpath": case.board_relpath,
            "layers": list(case.layers),
            "metrics": list(case.metrics),
            "minimums": {name: value for name, value in case.minimums},
            "snapshot": snapshot,
        }
        log.info("Generated %s (%s)", svg_path.name, ",".join(case.layers))

    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.info("Wrote manifest: %s", manifest_path)
    log.info("Generated synthetic oracle SVGs: %d", len(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
