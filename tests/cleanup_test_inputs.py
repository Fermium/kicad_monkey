"""Clean up test input folders - keep only .kicad_pcb, .kicad_pro, .kicad_sch files."""

from pathlib import Path
import shutil

INPUT_DIR = Path(__file__).parent / "test_cases" / "svg" / "board" / "input"

KEEP_EXTENSIONS = {'.kicad_pcb', '.kicad_pro', '.kicad_sch'}

def cleanup_folder(folder: Path):
    """Remove everything except KiCad project files."""
    print(f"Processing: {folder.name}")

    # Delete all subdirectories
    for subdir in list(folder.iterdir()):
        if subdir.is_dir():
            print(f"  Deleting dir: {subdir.name}")
            shutil.rmtree(subdir)

    # Delete files with wrong extensions
    for file in list(folder.iterdir()):
        if file.is_file() and file.suffix not in KEEP_EXTENSIONS:
            print(f"  Deleting file: {file.name}")
            file.unlink()

    # List remaining
    remaining = [f.name for f in folder.iterdir() if f.is_file()]
    print(f"  Kept: {remaining}")


def main():
    if not INPUT_DIR.exists():
        print(f"Input directory not found: {INPUT_DIR}")
        return

    folders = sorted([f for f in INPUT_DIR.iterdir() if f.is_dir()])
    print(f"Found {len(folders)} test folders\n")

    for folder in folders:
        cleanup_folder(folder)

    print(f"\nCleanup complete! Processed {len(folders)} folders.")


if __name__ == "__main__":
    main()
