"""R-7f9500f0: the Cyan install died on a root-only config.toml.

The installer runs as the desktop user and reads the TOML several times (its
hash, the missing switches, the validation, the runtime check), and so does the
GPU page. With /etc/cyan-skillfish-governor-smu/config.toml readable by root
only, the first read failed with "Permission denied", ``set -e`` stopped the
script and the binary was never installed. The installer now gives the file and
its folder back the read access upstream ships them with, before any read.
"""

import re
import stat
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "packaging/common/os-scripts/common/install-cyan-upstream-release.sh"
)


def _function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", SCRIPT.read_text(), re.M | re.S)
    assert match, name
    return match.group(0)


def _run(config: Path) -> None:
    script = "\n".join((
        "set -Eeuo pipefail",
        f"CONFIG={config}",
        "info() { :; }",
        'as_root() { "$@"; }',
        _function("restore_config_read_access"),
        "restore_config_read_access",
    ))
    subprocess.run(["bash", "-c", script], check=True)


# The test owns its files, so "readable by root only" is played by mode 000:
# the owner bits are then the ones that fail the check, as "other" does for a
# desktop user facing a root-owned 0600 file.


def test_a_config_nobody_else_can_read_gets_read_access_back(tmp_path):
    folder = tmp_path / "cyan-skillfish-governor-smu"
    folder.mkdir()
    config = folder / "config.toml"
    config.write_text("[gpu]\n")
    config.chmod(0o000)
    _run(config)
    mode = stat.S_IMODE(config.stat().st_mode)
    assert mode & 0o044 == 0o044
    assert mode & 0o222 == 0, "read access only, nothing becomes writable"


def test_a_folder_nobody_else_can_enter_gets_read_access_back(tmp_path):
    folder = tmp_path / "cyan-skillfish-governor-smu"
    folder.mkdir()
    (folder / "config.toml").write_text("[gpu]\n")
    folder.chmod(0o000)
    try:
        _run(folder / "config.toml")
        assert stat.S_IMODE(folder.stat().st_mode) & 0o055 == 0o055
    finally:
        folder.chmod(0o755)


def test_the_repair_runs_before_anything_reads_the_config():
    text = SCRIPT.read_text()
    call = text.index("\nrestore_config_read_access\n")
    for reader in ("\ncomplete_missing_switches\n", "\nvalidate_compatibility_switches\n",
                   "\nelif release_runs_here; then\n"):
        assert call < text.index(reader), reader
