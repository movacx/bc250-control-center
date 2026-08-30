from pathlib import Path

from bc250cc.shared.version import __version__, application_version
from frontends.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_version_matches_authoritative_release_file_and_appstream():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    appstream = (
        ROOT / "packaging/common/io.github.movacx.bc250-control-center.metainfo.xml"
    ).read_text(encoding="utf-8")

    assert application_version() == version
    assert __version__ == version
    assert f'<release version="{version}"' in appstream


def test_headless_cli_reports_the_same_release_version(capsys):
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert __version__ in capsys.readouterr().out
