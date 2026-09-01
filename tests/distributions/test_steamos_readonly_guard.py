from __future__ import annotations

import os
import subprocess
from pathlib import Path

from bc250cc.infrastructure.steamos_shell import steamos_writable_root_wrapper

WRAPPER = Path(
    "packaging/common/os-scripts/common/with-steamos-writable-root.sh"
).resolve()


def test_runtime_resolves_the_packaged_steamos_guard():
    assert steamos_writable_root_wrapper().resolve() == WRAPPER


def _fake_environment(tmp_path: Path, state: str):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    state_file = tmp_path / "readonly.state"
    state_file.write_text(state + "\n", encoding="utf-8")
    readonly = fake_bin / "steamos-readonly"
    readonly.write_text(
        """#!/usr/bin/env bash
set -eu
case "${1:-}" in
  status) cat "$BC250_TEST_READONLY_STATE" ;;
  disable) printf 'disabled\\n' > "$BC250_TEST_READONLY_STATE" ;;
  enable) printf 'enabled\\n' > "$BC250_TEST_READONLY_STATE" ;;
  *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    readonly.chmod(0o755)
    sudo = fake_bin / "sudo"
    sudo.write_text(
        """#!/usr/bin/env bash
set -eu
exec "$@"
""",
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            "BC250_TEST_READONLY_STATE": str(state_file),
            "BC250_STEAMOS_WRITABLE_TEST_DIR": str(tmp_path),
        }
    )
    return env, state_file


def _run(tmp_path: Path, state: str, command: str):
    env, state_file = _fake_environment(tmp_path, state)
    result = subprocess.run(
        ["bash", str(WRAPPER), "bash", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, state_file.read_text(encoding="utf-8").strip()


def test_enabled_root_is_temporarily_unlocked_and_restored(tmp_path):
    observed = tmp_path / "observed"
    result, final_state = _run(
        tmp_path,
        "enabled",
        f'cat "$BC250_TEST_READONLY_STATE" > {observed}',
    )
    assert result.returncode == 0, result.stderr
    assert observed.read_text(encoding="utf-8").strip() == "disabled"
    assert final_state == "enabled"


def test_enabled_root_is_restored_even_when_inner_command_fails(tmp_path):
    result, final_state = _run(tmp_path, "enabled", "exit 23")
    assert result.returncode == 23
    assert final_state == "enabled"


def test_preexisting_writable_root_is_preserved(tmp_path):
    observed = tmp_path / "observed"
    result, final_state = _run(
        tmp_path,
        "disabled",
        f'cat "$BC250_TEST_READONLY_STATE" > {observed}',
    )
    assert result.returncode == 0, result.stderr
    assert observed.read_text(encoding="utf-8").strip() == "disabled"
    assert final_state == "disabled"


def test_unknown_readonly_state_fails_closed_before_host_write(tmp_path):
    marker = tmp_path / "must-not-run"
    result, final_state = _run(tmp_path, "mystery", f'touch {marker}')
    assert result.returncode == 70
    assert not marker.exists()
    assert final_state == "mystery"
    assert "refusing host filesystem changes" in result.stderr
