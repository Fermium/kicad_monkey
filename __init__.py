"""KiCad File Format Module -- src layout bootstrap."""

from pathlib import Path as _Path

_SRC_PACKAGE_ROOT = _Path(__file__).resolve().parent / "src" / "py" / "kicad_monkey"
_src_str = str(_SRC_PACKAGE_ROOT.resolve())
if _SRC_PACKAGE_ROOT.exists() and _src_str not in __path__:
    __path__.insert(0, _src_str)

_real_init = _SRC_PACKAGE_ROOT / "__init__.py"
if _real_init.exists():
    _code = _real_init.read_text(encoding="utf-8")
    exec(compile(_code, str(_real_init), "exec"), globals())
