from __future__ import annotations

from pathlib import Path

from kicad_monkey import KiCadEnvironment, KiCadFilterPipeline


def _fake_install(root: Path, version: str) -> Path:
    install = root / "Programs" / "KiCad" / version
    bin_dir = install / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "kicad-cli.exe").write_text("", encoding="utf-8")
    return install


def test_kicad_environment_finds_highest_non_beta_installation(tmp_path) -> None:
    local_app_data = tmp_path / "local-app-data"
    install_90 = _fake_install(local_app_data, "9.0")
    install_110 = _fake_install(local_app_data, "11.0")
    install_beta = _fake_install(local_app_data, "11.99")

    environment = KiCadEnvironment(
        env={"LOCALAPPDATA": str(local_app_data)},
        platform="win32",
    )

    installations = environment.find_installations()
    highest_stable = environment.highest_installation(installations, ignore_beta=True)
    highest_any = environment.highest_installation(installations, ignore_beta=False)

    assert {
        install_90,
        install_110,
        install_beta,
    } <= {installation.root for installation in installations}
    assert highest_stable is not None
    assert highest_stable.root == install_110
    assert highest_stable.kicad_cli == install_110 / "bin" / "kicad-cli.exe"
    assert highest_any is not None
    assert highest_any.root == install_beta


def test_kicad_environment_finds_versioned_config_paths(tmp_path) -> None:
    app_data = tmp_path / "roaming"
    config_root = app_data / "kicad"
    for name in ("8.0", "10.0", "11.0", "not-version"):
        (config_root / name).mkdir(parents=True)

    environment = KiCadEnvironment(
        env={"APPDATA": str(app_data)},
        platform="win32",
    )

    assert [path.name for path in environment.find_config_paths(min_major=10)] == [
        "10.0",
        "11.0",
    ]


def test_filter_pipeline_exposes_file_level_operations() -> None:
    pipeline = KiCadFilterPipeline()

    assert callable(pipeline.filter_footprint)
    assert callable(pipeline.filter_symbol)
    assert callable(pipeline.filter_schematic)
    assert callable(pipeline.filter_pcb)
