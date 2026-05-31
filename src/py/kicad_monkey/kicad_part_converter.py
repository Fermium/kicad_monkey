"""
Modular KiCad conversion functions for single parts.
Extracted from lib_cruncher__migrate_kicad.py to support per-part conversion.
"""
import importlib
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, cast

from .kicad_environment import KiCadEnvironment
from .kicad_filters import KiCadFilterPipeline

log = logging.getLogger(__name__)


_KICAD_SYMBOL_NAME_RE = re.compile(r'\(\s*symbol\s+"((?:[^"\\]|\\.)*)"')
_KICAD_FOOTPRINT_NAME_RE = re.compile(r'\(\s*(?:footprint|module)\s+(?:"((?:[^"\\]|\\.)*)"|([^\s()]+))')


class _UnavailablePartA0:
    pass


def _default_flags_to_parameter(flags: Any) -> str:
    return ",".join(str(flag) for flag in (flags or ()))


try:
    _part_a0_module = importlib.import_module("data_models.part_a0")
    PartA0: type[Any] = cast(type[Any], getattr(_part_a0_module, "PartA0"))
    _flags_to_parameter_impl: Callable[[Any], str] = cast(
        Callable[[Any], str],
        getattr(_part_a0_module, "flags_to_parameter"),
    )
except ModuleNotFoundError:
    PartA0 = _UnavailablePartA0

    _flags_to_parameter_impl = _default_flags_to_parameter


def _flags_to_parameter(flags: Any) -> str:
    return _flags_to_parameter_impl(flags)


class PartKiCadConverter:
    """Handles conversion of individual parts from Altium to KiCad format."""

    def __init__(
        self,
        *,
        library_root: str | Path | None = None,
        symbol_root: str | Path | None = None,
        footprint_root: str | Path | None = None,
        kicad_symbol_root: str | Path | None = None,
        kicad_environment: KiCadEnvironment | None = None,
        filter_pipeline: KiCadFilterPipeline | None = None,
    ):
        """Initialize converter with KiCad CLI path and library root context."""
        if library_root is None:
            raise ValueError("library_root is required; kicad_monkey does not read private app settings")
        self.library_root = Path(library_root).resolve()
        self.symbol_root = Path(symbol_root or self.library_root / "symbols").resolve()
        self.footprint_root = Path(footprint_root or self.library_root / "footprints").resolve()
        self.kicad_symbol_root = Path(kicad_symbol_root or self.symbol_root / "kicad").resolve()
        self.kicad_environment = kicad_environment or KiCadEnvironment()
        installation = self.kicad_environment.highest_installation(ignore_beta=True)
        if installation is None:
            raise RuntimeError("Could not find a KiCad installation")
        self.kicad_cli_exe = installation.kicad_cli
        self.filter_pipeline = filter_pipeline or KiCadFilterPipeline()
        log.info(f"Using KiCad CLI: {self.kicad_cli_exe}")
        log.info(f"Using CAD library root: {self.library_root}")

    def _relative_to_library_root(self, path: Path) -> Path:
        """Return a path relative to the converter library root."""
        return path.resolve().relative_to(self.library_root)

    @staticmethod
    def _unescape_kicad_name(value: str) -> str:
        return value.replace(r"\\", "\\").replace(r"\"", '"').strip()

    @staticmethod
    def _first_kicad_name(path: Path, pattern: re.Pattern) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

        match = pattern.search(text)
        if not match:
            return ""

        for group in match.groups():
            if group:
                return PartKiCadConverter._unescape_kicad_name(group)
        return ""

    def _symbol_name_from_file(self, kicad_sym: Path) -> str:
        return self._first_kicad_name(kicad_sym, _KICAD_SYMBOL_NAME_RE)

    def _footprint_name_from_file(self, kicad_mod: Path) -> str:
        return self._first_kicad_name(kicad_mod, _KICAD_FOOTPRINT_NAME_RE)

    @staticmethod
    def _part_field(part: Any, field_name: str) -> str:
        """Read a UI CAD field from Part A0 or a mapping-like test double."""
        if isinstance(part, PartA0):
            if field_name == "Manufacturer Part Number":
                return part.mpn
            if field_name == "Library Path":
                return str(part.default_cad_option("altium", "symbol").get("library_path") or "")
            if field_name == "Footprint Path 1":
                return str(part.default_cad_option("altium", "footprint").get("library_path") or "")
            if field_name == "kicad-symbol":
                option = part.default_cad_option("kicad", "symbol")
                return str(option.get("symbol_ref") or option.get("name") or "")
            if field_name == "kicad-symbol-path":
                return str(part.default_cad_option("kicad", "symbol").get("library_path") or "")
            if field_name == "kicad-footprint":
                option = part.default_cad_option("kicad", "footprint")
                return str(option.get("footprint_ref") or option.get("name") or "")
            if field_name == "kicad-footprint-path":
                return str(part.default_cad_option("kicad", "footprint").get("library_path") or "")
            if field_name == "flags":
                return _flags_to_parameter(part.flags)

        getter = getattr(part, "get", None)
        if getter is not None:
            return str(getter(field_name, "") or "")
        return str(getattr(part, field_name, "") or "")

    @staticmethod
    def _set_part_field(part: Any, field_name: str, value: str, results: dict) -> None:
        results.setdefault("updated_fields", {})[field_name] = value
        if isinstance(part, PartA0):
            return
        try:
            part[field_name] = value
        except Exception:
            pass

    @classmethod
    def _part_has_flag(cls, part: Any, flag: str) -> bool:
        if isinstance(part, PartA0):
            return flag in set(part.flags)
        flags = cls._part_field(part, "flags")
        return flag in {item.strip().upper() for item in flags.split(",") if item.strip()}

    def _convert_symbol(self, altium_schlib: Path, force: bool = False) -> tuple[bool, Path | None]:
        """
        Convert a single Altium symbol to KiCad format.

        Args:
            altium_schlib: Path to Altium .SchLib file
            force: If True, delete existing KiCad symbol before conversion

        Returns:
            Tuple of (success: bool, kicad_sym_path: Optional[Path])
        """
        if not altium_schlib.exists():
            log.error(f"Altium symbol not found: {altium_schlib}")
            return False, None

        kicad_symbol_output = self.kicad_symbol_root
        kicad_symbol_output.mkdir(parents=True, exist_ok=True)

        kicad_sym = kicad_symbol_output / (altium_schlib.stem + ".kicad_sym")
        legacy_kicad_sym = altium_schlib.parent / (altium_schlib.stem + ".kicad_sym")

        # Handle force mode
        if force:
            if kicad_sym.exists():
                log.warning(f"Force mode: Removing existing symbol {kicad_sym}")
                kicad_sym.unlink()
            if legacy_kicad_sym.exists():
                log.warning(f"Force mode: Removing legacy symbol {legacy_kicad_sym}")
                legacy_kicad_sym.unlink()

        # Skip if already exists
        if kicad_sym.exists():
            log.info(f"Symbol already exists: {kicad_sym}")
            return True, kicad_sym

        # Migrate legacy output location if present (pre-v10 layout).
        if legacy_kicad_sym.exists():
            shutil.move(str(legacy_kicad_sym), str(kicad_sym))
            log.info(f"Migrated legacy symbol: {legacy_kicad_sym.name} -> {kicad_sym}")
            return True, kicad_sym

        # Convert symbol
        log.info(f"Converting symbol: {altium_schlib.name} -> {kicad_sym.name}")
        args = ["sym", "upgrade", "--output", str(kicad_sym), str(altium_schlib)]

        try:
            subprocess.run(
                [str(self.kicad_cli_exe)] + args,
                capture_output=True,
                text=True,
                check=True
            )
            log.info(f"[OK] Symbol converted: {kicad_sym.name}")
            return True, kicad_sym
        except subprocess.CalledProcessError as e:
            log.error(f"[FAIL] Symbol conversion failed: {altium_schlib.name}")
            log.error(f"  Return code: {e.returncode}")
            log.error(f"  stderr: {e.stderr}")
            return False, None

    def _convert_footprint(self, altium_pcblib: Path, force: bool = False) -> tuple[bool, Path | None]:
        """
        Convert a single Altium footprint to KiCad format.

        Args:
            altium_pcblib: Path to Altium .PcbLib file
            force: If True, delete existing KiCad footprint before conversion

        Returns:
            Tuple of (success: bool, kicad_mod_path: Optional[Path])
        """
        if not altium_pcblib.exists():
            log.error(f"Altium footprint not found: {altium_pcblib}")
            return False, None

        kicad_mod = self.footprint_root / (altium_pcblib.stem + ".kicad_mod")
        legacy_kicad_mod = altium_pcblib.parent / (altium_pcblib.stem + ".kicad_mod")
        pretty = altium_pcblib.parent / (altium_pcblib.stem + ".pretty")
        kicad_mod.parent.mkdir(parents=True, exist_ok=True)

        # Handle force mode
        if force:
            if kicad_mod.exists():
                log.warning(f"Force mode: Removing existing footprint {kicad_mod}")
                kicad_mod.unlink()
            if legacy_kicad_mod != kicad_mod and legacy_kicad_mod.exists():
                log.warning(f"Force mode: Removing legacy footprint {legacy_kicad_mod}")
                legacy_kicad_mod.unlink()
            if pretty.exists():
                log.warning(f"Force mode: Removing existing .pretty directory {pretty}")
                shutil.rmtree(pretty)

        # Skip if already exists
        if kicad_mod.exists():
            log.info(f"Footprint already exists: {kicad_mod}")
            return True, kicad_mod

        # Migrate legacy nested output location if present.
        if legacy_kicad_mod != kicad_mod and legacy_kicad_mod.exists():
            shutil.move(str(legacy_kicad_mod), str(kicad_mod))
            log.info(f"Migrated legacy footprint: {legacy_kicad_mod} -> {kicad_mod}")
            return True, kicad_mod

        # Convert footprint
        log.info(f"Converting footprint: {altium_pcblib.name} -> {kicad_mod.name}")
        args = ["fp", "upgrade", "--output", str(pretty), str(altium_pcblib)]

        try:
            # Remove .pretty directory if it exists
            if pretty.exists():
                shutil.rmtree(pretty)

            subprocess.run(
                [str(self.kicad_cli_exe)] + args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True
            )

            # Move .kicad_mod file from .pretty directory to parent
            if pretty.exists():
                for file_path in pretty.iterdir():
                    if file_path.is_file() and file_path.suffix == ".kicad_mod":
                        shutil.copy2(file_path, kicad_mod)
                        log.info(f"Copied {file_path.name} to {kicad_mod.name}")
                        break
                shutil.rmtree(pretty)

            if kicad_mod.exists():
                log.info(f"[OK] Footprint converted: {kicad_mod.name}")
                return True, kicad_mod
            else:
                log.error("[FAIL] Footprint conversion failed: No .kicad_mod created")
                return False, None

        except subprocess.CalledProcessError as e:
            log.error(f"[FAIL] Footprint conversion failed: {altium_pcblib.name}")
            log.error(f"  Return code: {e.returncode}")
            log.error(f"  stderr: {e.stderr}")
            return False, None

    def _filter_symbol(self, kicad_sym: Path) -> bool:
        """
        Apply filters to a KiCad symbol file.

        Args:
            kicad_sym: Path to .kicad_sym file

        Returns:
            True if filtering succeeded
        """
        if not kicad_sym.exists():
            log.error(f"KiCad symbol not found for filtering: {kicad_sym}")
            return False

        try:
            log.info(f"Filtering symbol: {kicad_sym.name}")
            self.filter_pipeline.filter_symbol(kicad_sym, kicad_sym)
            log.info(f"[OK] Symbol filtered: {kicad_sym.name}")
            return True
        except Exception as e:
            log.error(f"[FAIL] Symbol filtering failed: {kicad_sym.name}")
            log.error(f"  Error: {str(e)}")
            return False

    def _filter_footprint(self, kicad_mod: Path) -> bool:
        """
        Apply filters to a KiCad footprint file.

        Args:
            kicad_mod: Path to .kicad_mod file

        Returns:
            True if filtering succeeded
        """
        if not kicad_mod.exists():
            log.error(f"KiCad footprint not found for filtering: {kicad_mod}")
            return False

        try:
            log.info(f"Filtering footprint: {kicad_mod.name}")
            self.filter_pipeline.filter_footprint(kicad_mod, kicad_mod)
            log.info(f"[OK] Footprint filtered: {kicad_mod.name}")
            return True
        except Exception as e:
            log.error(f"[FAIL] Footprint filtering failed: {kicad_mod.name}")
            log.error(f"  Error: {str(e)}")
            return False

    def convert_part(
        self,
        part: Any,
        force: bool = False,
        run_filters: bool = True,
        *,
        force_symbol: bool | None = None,
        force_footprint: bool | None = None,
    ) -> dict:
        """
        Convert a single part from Altium to KiCad format.

        This is the main entry point for part conversion. It:
        1. Converts the symbol (if Altium symbol exists)
        2. Converts the footprint (if Altium footprint exists)
        3. Applies filters to both
        4. Updates part fields with KiCad paths

        Args:
            part: Part A0 object, or a mapping-like part test double
            force: If True, reconvert even if KiCad files exist
            run_filters: If True, run filters after conversion
            force_symbol: Optional symbol-specific force override
            force_footprint: Optional footprint-specific force override

        Returns:
            dict with conversion results:
            {
                'symbol_converted': bool,
                'symbol_filtered': bool,
                'footprint_converted': bool,
                'footprint_filtered': bool,
                'symbol_path': Optional[Path],
                'footprint_path': Optional[Path],
                'errors': List[str]
            }
        """
        results = {
            'symbol_converted': False,
            'symbol_filtered': False,
            'footprint_converted': False,
            'footprint_filtered': False,
            'symbol_path': None,
            'footprint_path': None,
            'updated_fields': {},
            'errors': []
        }

        mpn = self._part_field(part, 'Manufacturer Part Number') or 'Unknown'
        log.info("=" * 80)
        log.info(f"Converting part: {mpn}")
        log.info("=" * 80)
        symbol_force = force if force_symbol is None else force_symbol
        footprint_force = force if force_footprint is None else force_footprint

        # Convert Symbol
        symbol_lib_path = self._part_field(part, 'Library Path').strip()
        if symbol_lib_path:
            altium_schlib = self.library_root / symbol_lib_path
            success, kicad_sym_path = self._convert_symbol(altium_schlib, force=symbol_force)

            if success and kicad_sym_path:
                results['symbol_converted'] = True
                results['symbol_path'] = kicad_sym_path

                # Update part fields with KiCad symbol path relative to this library root.
                relative_path = self._relative_to_library_root(kicad_sym_path)
                self._set_part_field(part, 'kicad-symbol-path', str(relative_path.as_posix()), results)

                # Prefer the KiCad symbol name inside the file; it can differ from the filename.
                self._set_part_field(
                    part,
                    'kicad-symbol',
                    self._symbol_name_from_file(kicad_sym_path) or kicad_sym_path.stem,
                    results,
                )

                # Apply filter
                if run_filters:
                    if self._filter_symbol(kicad_sym_path):
                        results['symbol_filtered'] = True
                    else:
                        results['errors'].append(f"Symbol filtering failed: {kicad_sym_path.name}")
            else:
                results['errors'].append(f"Symbol conversion failed: {symbol_lib_path}")
        else:
            log.info("No Altium symbol path defined, skipping symbol conversion")

        # Convert Footprint
        footprint_lib_path = self._part_field(part, 'Footprint Path 1').strip()
        if footprint_lib_path:
            altium_pcblib = self.library_root / footprint_lib_path
            success, kicad_mod_path = self._convert_footprint(altium_pcblib, force=footprint_force)

            if success and kicad_mod_path:
                results['footprint_converted'] = True
                results['footprint_path'] = kicad_mod_path

                # Update part fields with KiCad footprint path relative to this library root.
                relative_path = self._relative_to_library_root(kicad_mod_path)
                self._set_part_field(part, 'kicad-footprint-path', str(relative_path.as_posix()), results)

                # Prefer the KiCad footprint name inside the file; it can differ from the filename.
                self._set_part_field(
                    part,
                    'kicad-footprint',
                    self._footprint_name_from_file(kicad_mod_path) or kicad_mod_path.stem,
                    results,
                )

                # Apply filter
                if run_filters:
                    if self._filter_footprint(kicad_mod_path):
                        results['footprint_filtered'] = True
                    else:
                        results['errors'].append(f"Footprint filtering failed: {kicad_mod_path.name}")
            else:
                results['errors'].append(f"Footprint conversion failed: {footprint_lib_path}")
        else:
            log.info("No Altium footprint path defined, skipping footprint conversion")

        # Summary
        log.info("=" * 80)
        if results['errors']:
            log.warning(f"Conversion completed with {len(results['errors'])} error(s)")
            for error in results['errors']:
                log.error(f"  • {error}")
        else:
            log.info("[OK] Conversion completed successfully")
        log.info("=" * 80)

        return results

    def check_and_convert_if_missing(self, part: Any) -> dict:
        """
        Check if KiCad files exist for a part, and convert from Altium if they don't.

        This is used by the part checking workflow to ensure KiCad files exist.

        Args:
            part: Part A0 object, or a mapping-like part test double

        Returns:
            dict with conversion results (same format as convert_part)
        """
        # Skip if part has NO_KICAD flag - it's not supposed to have KiCad files
        if self._part_has_flag(part, "NO_KICAD"):
            log.info("Part has NO_KICAD flag - skipping KiCad conversion check")
            return {
                'symbol_converted': False,
                'symbol_filtered': False,
                'footprint_converted': False,
                'footprint_filtered': False,
                'symbol_path': None,
                'footprint_path': None,
                'errors': []
            }

        needs_conversion = False

        # Check if KiCad symbol exists on disk
        kicad_symbol_path = self._part_field(part, 'kicad-symbol-path').strip()
        if kicad_symbol_path:
            symbol_full_path = self.library_root / kicad_symbol_path
            if not symbol_full_path.exists():
                log.warning(f"KiCad symbol path in part but file missing: {kicad_symbol_path}")
                needs_conversion = True

        # Check if KiCad footprint exists on disk
        kicad_footprint_path = self._part_field(part, 'kicad-footprint-path').strip()
        if kicad_footprint_path:
            footprint_full_path = self.library_root / kicad_footprint_path
            if not footprint_full_path.exists():
                log.warning(f"KiCad footprint path in part but file missing: {kicad_footprint_path}")
                needs_conversion = True

        # If KiCad paths are empty but Altium paths exist, also convert
        if not kicad_symbol_path and self._part_field(part, 'Library Path').strip():
            log.info("No KiCad symbol path defined, will convert from Altium")
            needs_conversion = True

        if not kicad_footprint_path and self._part_field(part, 'Footprint Path 1').strip():
            log.info("No KiCad footprint path defined, will convert from Altium")
            needs_conversion = True

        if needs_conversion:
            log.info("Converting part to KiCad...")
            return self.convert_part(part, force=False, run_filters=True)
        else:
            log.debug("KiCad files already exist for this part")
            return {
                'symbol_converted': False,
                'symbol_filtered': False,
                'footprint_converted': False,
                'footprint_filtered': False,
                'symbol_path': None,
                'footprint_path': None,
                'errors': []
            }
