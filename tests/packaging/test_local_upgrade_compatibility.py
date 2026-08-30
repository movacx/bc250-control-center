import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _environment(home: Path) -> dict[str, str]:
    return dict(
        os.environ,
        HOME=str(home),
        PREFIX=str(home / ".local"),
        XDG_CONFIG_HOME=str(home / "xdg-config"),
        XDG_DATA_HOME=str(home / ".local" / "share"),
        XDG_STATE_HOME=str(home / "xdg-state"),
        XDG_CACHE_HOME=str(home / "xdg-cache"),
        BC250_SKIP_DEPENDENCY_INSTALL="1",
        BC250_SKIP_PRIVILEGED_HELPER="1",
    )


def test_upgrade_from_118_removes_mvc_but_preserves_user_state(tmp_path: Path):
    home = tmp_path / "home"
    env = _environment(home)
    app = home / ".local/share/bc250-control-center"
    config = home / "xdg-config/bc250-control-center"
    state = home / "xdg-state/bc250-control-center"
    (app / "mvc").mkdir(parents=True)
    (app / "mvc/old-118.py").write_text("legacy", encoding="utf-8")
    (app / "Data/history").mkdir(parents=True)
    (app / "Data/history/metrics.csv").write_text("preserve", encoding="utf-8")
    (app / "ResourceTools/tool").mkdir(parents=True)
    config.mkdir(parents=True)
    (config / "config.json").write_text('{"version": 1, "idioma": "es"}\n', encoding="utf-8")

    installed = _run(ROOT / "scripts/install-local.sh", env=env)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert not (app / "mvc").exists()
    assert (app / "src/bc250cc/__init__.py").is_file()
    assert (app / "Data/history/metrics.csv").read_text(encoding="utf-8") == "preserve"
    assert (app / "ResourceTools/tool").is_dir()
    assert (config / "config.json").is_file()
    backups = list((state / "migration-backups").glob("1.18-to-1.19-*/config.json"))
    assert len(backups) == 1

    removed = _run(app / "scripts/uninstall-local.sh", "--yes", "--keep-privileged", env=env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert not (home / ".local/bin/bc250-control-center").exists()
    assert not (app / "src").exists()
    assert (app / "Data/history/metrics.csv").is_file()
    assert (app / "ResourceTools/tool").is_dir()
    assert (config / "config.json").is_file()
    assert state.is_dir()


def test_explicit_purge_uses_xdg_paths_and_removes_verified_managed_data(tmp_path: Path):
    home = tmp_path / "home"
    env = _environment(home)
    app = home / ".local/share/bc250-control-center"
    config = home / "xdg-config/bc250-control-center"
    state = home / "xdg-state/bc250-control-center"
    cache = home / "xdg-cache/bc250-control-center"
    for directory in (app, config, state, cache):
        directory.mkdir(parents=True)
        (directory / "sentinel").write_text("managed", encoding="utf-8")
    fsr4 = home / ".local/share/bc250-fsr4"
    fsr4.mkdir(parents=True)
    (fsr4 / ".bc250-upstream-revision").write_text("reviewed", encoding="utf-8")

    removed = _run(
        ROOT / "scripts/uninstall-local.sh",
        "--yes",
        "--keep-privileged",
        "--purge-user-data",
        env=env,
    )
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert not app.exists()
    assert not config.exists()
    assert not state.exists()
    assert not cache.exists()
    assert not fsr4.exists()
