"""A package that fails its signature in rpm-ostree's cache is downloaded once more, never trusted."""
import subprocess
from pathlib import Path

COMMON = Path(__file__).resolve().parents[2] / "packaging/common/os-scripts/common/common.sh"


def run(tmp_path, failures):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "rpm-ostree").write_text(f"""#!/bin/bash
echo "$*" >> {tmp_path}/calls
case "$1" in
  status) echo '{{}}'; exit 0 ;;
  install)
    n=$(grep -c '^install' {tmp_path}/calls)
    if [ "$n" -le {failures} ]; then
      echo "error: importing RPMs: package llvm21-libs-21.1.8-5.fc44.x86_64 cannot be verified and repo updates is GPG enabled: /var/cache/rpm-ostree/repomd/updates-44-x86_64/packages/llvm21-libs.rpm could not be verified."
      exit 1
    fi ;;
esac
exit 0
""")
    (fake / "rpm-ostree").chmod(0o755)
    script = f"source {COMMON}; as_root() {{ echo \"root $*\" >> {tmp_path}/calls; [ \"$1\" = rm ] || \"$@\"; }}; rpm_ostree_layer umr"
    result = subprocess.run(["bash", "-c", script], env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)}, capture_output=True, text=True)
    return result.returncode, (tmp_path / "calls").read_text().splitlines()


def test_the_bad_copy_is_dropped_and_downloaded_again(tmp_path):
    status, calls = run(tmp_path, failures=1)
    assert status == 0
    assert "root rm -f -- /var/cache/rpm-ostree/repomd/updates-44-x86_64/packages/llvm21-libs.rpm" in calls
    assert "cleanup --repomd" in calls and calls.count("install --idempotent umr") == 2


def test_a_cut_download_and_a_busy_daemon_are_retried_too(tmp_path):
    """Before, the first failure ended the script under set -e, so neither retry ever ran."""
    status, calls = run(tmp_path, failures=1)
    assert status == 0 and calls.count("install --idempotent umr") == 2


def test_a_signature_that_keeps_failing_is_reported_not_retried_forever(tmp_path):
    status, calls = run(tmp_path, failures=9)
    assert status != 0
    assert calls.count("install --idempotent umr") == 2
