"""
Empirical check: can we drop preserve_embedded_data_formatting?

Plan said the post-Phase-B emit handles embedded_files / image chunked data
correctly. This script validates that against real fixtures by:
  1. Reading a fixture with (embedded_files ...) and/or (image ...) data.
  2. Parsing it (parse_sexp) and re-emitting BOTH ways:
       a) format_kicad_sexp(s) alone — the post-Phase-B emit.
       b) preserve_embedded_data_formatting(orig, s) — current production path.
  3. Running kicad-cli upgrade on each output (and the original) — the oracle.
  4. Diffing the kicad-cli-normalized outputs against the oracle of the original.

If (a) and (b) both produce the same kicad-cli-normalized result as the
oracle of the original, the regex is unnecessary. If (a) is rejected /
diverges but (b) doesn't, the regex still earns its keep.

Usage:
    python embedded_data_emit_check.py <fixture> [<fixture> ...]
    # If no fixtures given, runs the default battery.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow running outside an installed env.
_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent.parent / "src" / "py"
sys.path.insert(0, str(_PKG))

from kicad_monkey.kicad_filter_core import (
    format_kicad_sexp,
    preserve_embedded_data_formatting,
)
from kicad_monkey.kicad_sexpr import parse_sexp


# ---------------------------------------------------------------------------
# kicad-cli resolution (matches oracle_diff.py shape)
# ---------------------------------------------------------------------------

def _resolve_cli() -> Path:
    if env := os.environ.get("KICAD_CLI"):
        return Path(env)
    corpus = Path(os.environ.get("WN_TEST_CORPUS", r"C:\eli\wn_test_corpus"))
    staged_root = corpus / "tools" / "kicad-cli"
    if staged_root.exists():
        candidates = sorted(
            (p for p in staged_root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for cand in candidates:
            cli = cand / "bin" / "kicad-cli.exe"
            if cli.exists():
                return cli
    fallback = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
    if fallback.exists():
        return fallback
    raise RuntimeError("No kicad-cli found; set KICAD_CLI")


CLI = _resolve_cli()


def cli_upgrade(input_path: Path, output_path: Path) -> tuple[int, str]:
    """Run kicad-cli {fp,sym,sch,pcb} upgrade --force on input -> output."""
    suffix = input_path.suffix
    if suffix == ".kicad_mod":
        # fp upgrade operates on a .pretty dir; stage parent.
        parent = input_path.parent
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / "stage.pretty"
            staged.mkdir()
            shutil.copy2(input_path, staged / input_path.name)
            cmd = [
                str(CLI), "fp", "upgrade", "--force", str(staged),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            out_file = staged / input_path.name
            if out_file.exists():
                shutil.copy2(out_file, output_path)
            return r.returncode, (r.stderr or r.stdout)
    elif suffix == ".kicad_sym":
        cmd = [str(CLI), "sym", "upgrade", "--force", str(input_path)]
        # in-place; copy then run
        shutil.copy2(input_path, output_path)
        cmd[-1] = str(output_path)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stderr or r.stdout)
    elif suffix == ".kicad_sch":
        cmd = [str(CLI), "sch", "upgrade", "--force", str(input_path)]
        shutil.copy2(input_path, output_path)
        cmd[-1] = str(output_path)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stderr or r.stdout)
    elif suffix == ".kicad_pcb":
        cmd = [str(CLI), "pcb", "upgrade", "--force", str(input_path)]
        shutil.copy2(input_path, output_path)
        cmd[-1] = str(output_path)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode, (r.stderr or r.stdout)
    raise ValueError(f"Unsupported suffix {suffix}")


def emit_with_regex(orig_text: str, sexp) -> str:
    return preserve_embedded_data_formatting(orig_text, sexp)


def emit_without_regex(orig_text: str, sexp) -> str:
    out = format_kicad_sexp(sexp)
    if not out.endswith("\n"):
        out += "\n"
    return out


# ---------------------------------------------------------------------------
# Compare logic
# ---------------------------------------------------------------------------

def _norm(text: str) -> list[str]:
    """Whitespace-tolerant line list (strip CR + trailing whitespace)."""
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]


def diff_lines(a: str, b: str, max_lines: int = 20) -> list[str]:
    import difflib
    da, db = _norm(a), _norm(b)
    diff = list(difflib.unified_diff(da, db, lineterm="", n=2))
    return diff[:max_lines]


def _embedded_data_bytes(text: str) -> bytes:
    """Extract concatenated base64 payload bytes (data only, no line breaks)
    from every (data ...) child of an (embedded_files ...) section. Used to
    compare semantic content independent of formatting."""
    import re
    out = []
    # crude but sufficient: grab all `(data ` blocks until matching close
    for m in re.finditer(r'\(data\b', text):
        depth = 0
        i = m.end()
        start = i
        while i < len(text):
            c = text[i]
            if c == '(':
                depth += 1
            elif c == ')':
                if depth == 0:
                    break
                depth -= 1
            i += 1
        chunk = text[start:i]
        # strip whitespace and pipe wrappers and quotes
        cleaned = chunk.replace('\n', '').replace('\r', '').replace('\t', '')
        cleaned = cleaned.replace('|', '').replace('"', '').strip()
        out.append(cleaned)
    return ''.join(out).encode('ascii', errors='replace')


def check_one(fixture: Path) -> dict:
    print(f"\n=== {fixture} ===")
    text = fixture.read_text(encoding="utf-8")
    has_emb = "embedded_files" in text
    has_img = "(image " in text
    print(f"  has embedded_files={has_emb}  has image={has_img}")

    sexp = parse_sexp(text)
    out_with = emit_with_regex(text, sexp)
    out_without = emit_without_regex(text, sexp)

    # Stage all three through kicad-cli upgrade.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        suffix = fixture.suffix

        # Stage all three under three sibling subdirs but with the SAME basename
        # so kicad-cli fp-upgrade doesn't rewrite the (footprint "name") field.
        for sub in ("orig", "with", "without"):
            (td / sub).mkdir()
        orig_in = td / "orig" / fixture.name
        with_in = td / "with" / fixture.name
        without_in = td / "without" / fixture.name
        orig_out = td / f"orig.canon{suffix}"
        with_out = td / f"with.canon{suffix}"
        without_out = td / f"without.canon{suffix}"

        orig_in.write_bytes(text.encode("utf-8"))
        with_in.write_bytes(out_with.encode("utf-8"))
        without_in.write_bytes(out_without.encode("utf-8"))

        rc_orig, msg_orig = cli_upgrade(orig_in, orig_out)
        rc_with, msg_with = cli_upgrade(with_in, with_out)
        rc_without, msg_without = cli_upgrade(without_in, without_out)

        result = {
            "fixture": str(fixture),
            "rc_orig": rc_orig,
            "rc_with": rc_with,
            "rc_without": rc_without,
            "msg_orig": msg_orig.strip()[:300],
            "msg_with": msg_with.strip()[:300],
            "msg_without": msg_without.strip()[:300],
        }

        ot = orig_out.read_text(encoding="utf-8", errors="replace") if orig_out.exists() else ""
        wt = with_out.read_text(encoding="utf-8", errors="replace") if with_out.exists() else ""
        ut = without_out.read_text(encoding="utf-8", errors="replace") if without_out.exists() else ""

        if rc_orig == 0 and rc_without == 0:
            result["orig_eq_without"] = (ot == ut)
        if rc_orig == 0 and rc_with == 0:
            result["orig_eq_with"] = (ot == wt)
        if rc_with == 0 and rc_without == 0:
            result["with_eq_without"] = (wt == ut)
        if rc_orig == 0 and rc_with == 0 and rc_without == 0:

            # Compare the actual embedded payload bytes (whitespace-independent).
            ob = _embedded_data_bytes(ot)
            wb = _embedded_data_bytes(wt)
            ub = _embedded_data_bytes(ut)
            result["payload_orig_eq_with"] = (ob == wb)
            result["payload_orig_eq_without"] = (ob == ub)
            result["payload_with_eq_without"] = (wb == ub)
            result["payload_size_orig"] = len(ob)
            result["payload_size_without"] = len(ub)

            if not result["orig_eq_without"]:
                result["diff_orig_vs_without"] = diff_lines(ot, ut, max_lines=40)
            if not result["with_eq_without"]:
                result["diff_with_vs_without"] = diff_lines(wt, ut, max_lines=40)

    def _rc_label(rc):
        if rc == 0:
            return "ok"
        if rc == 0xC0000005:
            return "SEGFAULT"
        return f"rc={rc}"

    print(f"  rc_orig={_rc_label(result['rc_orig'])}  rc_with={_rc_label(result['rc_with'])}  rc_without={_rc_label(result['rc_without'])}")
    if "orig_eq_without" in result:
        print(f"  text-eq (canon, w/o-regex vs orig): {result['orig_eq_without']}")
    if "orig_eq_with" in result:
        print(f"  text-eq (canon, w/regex  vs orig): {result['orig_eq_with']}")
    if result["rc_orig"] == 0 and result["rc_with"] == 0 and result["rc_without"] == 0:
        print(
            f"  text-eq:  with-vs-without={result['with_eq_without']}"
        )
        print(
            f"  payload-eq:       with-vs-orig={result['payload_orig_eq_with']}  "
            f"without-vs-orig={result['payload_orig_eq_without']}  "
            f"with-vs-without={result['payload_with_eq_without']}  "
            f"(orig {result['payload_size_orig']} bytes, "
            f"without {result['payload_size_without']} bytes)"
        )
        if "diff_with_vs_without" in result and result["diff_with_vs_without"]:
            print("  diff with-vs-without (first lines):")
            for ln in result["diff_with_vs_without"]:
                print(f"    {ln}")
    return result


def main():
    if len(sys.argv) > 1:
        fixtures = [Path(a) for a in sys.argv[1:]]
    else:
        corpus = Path(os.environ.get("WN_TEST_CORPUS", r"C:\eli\wn_test_corpus"))
        wren = corpus / "kicad" / "common" / "vme-wren" / "input" / "wren.pretty"
        fixtures = [
            wren / "SODFL1608X65N.kicad_mod",
            wren / "OSC_KYOCERA_KV7050B-C3.kicad_mod",
            wren / "SAMTEC_MTLW-102-07-L-S-250.kicad_mod",
        ]
    results = [check_one(f) for f in fixtures]

    # Summary
    print("\n=== SUMMARY ===")
    n_with_segfault = sum(1 for r in results if r["rc_with"] == 0xC0000005)
    n_without_ok = sum(1 for r in results if r["rc_without"] == 0)
    n_without_match_orig = sum(1 for r in results if r.get("orig_eq_without"))
    print(f"  fixtures examined: {len(results)}")
    print(f"  with-regex SEGFAULTs in kicad-cli: {n_with_segfault}")
    print(f"  without-regex accepted by kicad-cli: {n_without_ok}/{len(results)}")
    print(f"  without-regex byte-eq to original after canon: {n_without_match_orig}")
    for r in results:
        name = Path(r["fixture"]).name
        bits = []
        if r["rc_orig"] != 0:
            bits.append(f"orig FAIL ({r['msg_orig'][:60]})")
        if r["rc_with"] == 0xC0000005:
            bits.append("with-regex SEGFAULT")
        elif r["rc_with"] != 0:
            bits.append(f"with-regex rc={r['rc_with']}")
        if r["rc_without"] != 0:
            bits.append(f"without-regex rc={r['rc_without']}")
        if r.get("orig_eq_without"):
            bits.append("without==orig")
        if r.get("payload_with_eq_without"):
            bits.append("payload bytes equal")
        print(f"  {name}: {', '.join(bits) or 'no findings'}")


if __name__ == "__main__":
    main()
