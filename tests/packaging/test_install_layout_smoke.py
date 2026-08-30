import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_isolated_install_cli_and_uninstall_layout_cycle():
    completed = subprocess.run(
        ["bash", str(ROOT / "scripts" / "smoke-install-layout.sh")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "installed CLI execution and uninstall layout passed" in completed.stdout


def test_launchers_prefer_their_sibling_payload_before_stale_xdg_fallback():
    for name in (
        "bc250-control-center",
        "bc250-control-center-cli",
        "bc250-control-centerd",
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        sibling = source.index('$(dirname -- "$0")/../share/bc250-control-center')
        checkout = source.index('$(dirname -- "$0")/..')
        xdg = source.index('$XDG_DATA_BASE/bc250-control-center')
        assert sibling < xdg
        assert checkout < xdg
