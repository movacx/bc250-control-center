import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.steamos_amdgpu import (
    AmdgpuDecision,
    build_steamos_amdgpu_diagnostic_command,
    build_steamos_compatibility_command,
    classify_amdgpu_status,
    parse_amdgpu_status,
)

FIXTURES = Path("tests/fixtures/steamos_amdgpu")

@pytest.mark.parametrize(
    ("name", "privileged", "efi", "decision"),
    (
        ("ready.txt", True, True, AmdgpuDecision.READY),
        ("reboot_pending.txt", True, True, AmdgpuDecision.REBOOT_PENDING),
        ("policy_incomplete.txt", True, True, AmdgpuDecision.REPAIR_POLICY),
        ("policy_incomplete.txt", False, False, AmdgpuDecision.PRIVILEGED_CHECK),
        ("conflicting.txt", True, True, AmdgpuDecision.REPAIR_POLICY),
        ("missing.txt", True, True, AmdgpuDecision.INSTALL),
        ("not_installed_summary.txt", True, True, AmdgpuDecision.INSTALL),
    ),
)
def test_status_fixtures_produce_explicit_decision(name, privileged, efi, decision):
    output = (FIXTURES / name).read_text(encoding="utf-8")
    cmdline = "amdgpu.sched_policy=2" if name == "ready.txt" else "quiet splash"
    assert classify_amdgpu_status(
        output,
        privileged=privileged,
        efi_readable=efi,
        running_release="6.18-test",
        running_cmdline=cmdline,
    ).decision is decision


@pytest.mark.parametrize(
    ("fixture", "module_verified", "policy_active", "policy_reboot", "conflict"),
    (
        ("ready.txt", True, True, False, False),
        ("policy_incomplete.txt", True, False, False, False),
        ("missing.txt", False, False, False, False),
        ("not_installed_summary.txt", False, True, False, True),
        ("conflicting.txt", True, True, True, True),
        ("conflicting_active_incomplete_summary.txt", True, True, False, True),
    ),
)
def test_status_fixtures_characterize_module_and_boot_policy_evidence(
    fixture, module_verified, policy_active, policy_reboot, conflict
):
    evidence = parse_amdgpu_status(
        (FIXTURES / fixture).read_text(encoding="utf-8"),
        running_release="6.18-test",
    )

    assert evidence.module_verified is module_verified
    assert evidence.policy_active_reported is policy_active
    assert evidence.policy_reboot_reported is policy_reboot
    assert evidence.policy_conflict is conflict

def test_untrusted_status_text_is_not_a_success_marker():
    state = classify_amdgpu_status(
        "$(touch /tmp/no)\nstate: installed",
        privileged=True,
        running_release="6.18-test",
        running_cmdline="quiet splash",
    )
    assert state.decision is AmdgpuDecision.INSTALL


def test_missing_live_kernel_evidence_never_selects_a_hardware_action():
    output = (FIXTURES / "ready.txt").read_text(encoding="utf-8")

    unknown_kernel = classify_amdgpu_status(
        output, privileged=True, running_cmdline="amdgpu.sched_policy=2"
    )
    unknown_cmdline = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test"
    )

    assert unknown_kernel.decision is AmdgpuDecision.KERNEL_STATUS_REQUIRED
    assert unknown_kernel.mutating_action == "kernel-status"
    assert unknown_cmdline.decision is AmdgpuDecision.LIVE_STATUS_REQUIRED
    assert unknown_cmdline.mutating_action == "live-cmdline-status"


def test_installed_summary_without_policy_evidence_requires_policy_repair():
    state = classify_amdgpu_status(
        "[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] state: installed\n",
        privileged=True,
        running_release="6.18-test",
        running_cmdline="quiet splash",
    )
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert not state.policy_verified
    assert not state.policy_active


def test_conflicting_policy_evidence_fails_closed_to_repair():
    output = (FIXTURES / "conflicting.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test", running_cmdline="quiet splash"
    )
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert not state.policy_verified
    assert not state.policy_active


def test_active_marker_with_incomplete_summary_fails_closed_to_repair():
    output = (FIXTURES / "conflicting_active_incomplete_summary.txt").read_text(encoding="utf-8")
    evidence = parse_amdgpu_status(output, running_release="6.18-test")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test", running_cmdline="quiet splash"
    )
    assert evidence.summary_conflict is False
    assert evidence.policy_conflict is True
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert state.policy_active is False


@pytest.mark.parametrize(
    "output",
    (
        "[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)\n",
        "[bc250-amdgpu] 6.18-test: installed, metrics and compute aware\n"
        "[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)\n"
        "[bc250-amdgpu] state: unknown\n",
    ),
)
def test_policy_marker_without_its_exact_summary_fails_closed_to_repair(output):
    evidence = parse_amdgpu_status(output, running_release="6.18-test")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test", running_cmdline="quiet splash"
    )
    assert evidence.policy_conflict is True
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert state.policy_active is False


def test_conflicting_module_evidence_fails_closed_to_full_install():
    output = (FIXTURES / "conflicting_module.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test"
    )
    assert state.decision is AmdgpuDecision.INSTALL
    assert state.module_verified is False


def test_stale_kernel_module_evidence_requires_a_kernel_matched_install():
    output = (FIXTURES / "stale_kernel.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test"
    )
    assert state.decision is AmdgpuDecision.INSTALL
    assert state.module_verified is False


def test_missing_summary_cannot_override_an_affirmative_module_line():
    output = (FIXTURES / "conflicting_missing_summary.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test"
    )
    assert state.decision is AmdgpuDecision.INSTALL
    assert state.module_verified is False


def test_upstream_not_installed_summary_cannot_override_an_affirmative_module_line():
    """Match the exact absence spelling emitted by reviewed patch-driver.sh."""
    output = (FIXTURES / "not_installed_summary.txt").read_text(encoding="utf-8")
    evidence = parse_amdgpu_status(output, running_release="6.18-test")
    state = classify_amdgpu_status(
        output, privileged=True, running_release="6.18-test"
    )
    assert evidence.module_verified is False
    assert state.decision is AmdgpuDecision.INSTALL
    assert state.module_verified is False


def test_live_cmdline_proves_current_activation_but_not_persistence():
    output = (FIXTURES / "policy_incomplete.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output,
        privileged=False,
        efi_readable=False,
        running_release="6.18-test",
        running_cmdline="quiet amdgpu.sched_policy=2 splash",
    )
    assert state.decision is AmdgpuDecision.PRIVILEGED_CHECK
    assert state.module_verified is True
    assert state.policy_active is True
    assert state.policy_verified is False
    assert state.mutating_action == "privileged-status"


def test_persisted_reboot_marker_plus_active_cmdline_is_a_conflict_not_ready():
    output = (FIXTURES / "reboot_pending.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output,
        privileged=True,
        running_release="6.18-test",
        running_cmdline="amdgpu.sched_policy=2",
    )
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert state.policy_active is False
    assert state.runtime_policy_conflict is True
    assert state.reboot_required_after_action is True


@pytest.mark.parametrize(
    "cmdline",
    (
        "quiet amdgpu.sched_policy=1 splash",
        "quiet splash",
        "amdgpu.sched_policy=2 amdgpu.sched_policy=2",
    ),
)
def test_active_status_requires_an_unambiguous_live_scheduler_policy(cmdline):
    output = (FIXTURES / "ready.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output,
        privileged=True,
        running_release="6.18-test",
        running_cmdline=cmdline,
    )
    assert state.decision is AmdgpuDecision.REPAIR_POLICY
    assert state.policy_verified is False
    assert state.policy_active is False
    assert state.runtime_policy_conflict is True


def test_active_status_and_exact_live_scheduler_policy_are_ready():
    output = (FIXTURES / "ready.txt").read_text(encoding="utf-8")
    state = classify_amdgpu_status(
        output,
        privileged=True,
        running_release="6.18-test",
        running_cmdline="quiet amdgpu.sched_policy=2 splash",
    )
    assert state.decision is AmdgpuDecision.READY
    assert state.policy_active is True
    assert state.runtime_policy_conflict is False


@pytest.mark.parametrize(
    ("initial_state", "decision", "actions", "final_state"),
    (
        ("ready", "READY: no changes are necessary.", [], "ready"),
        ("reboot", "REBOOT PENDING: no additional changes are necessary.", [], "reboot"),
        ("policy", "REPAIR POLICY ONLY", ["boot"], "reboot"),
        ("active-no-summary", "REPAIR POLICY ONLY", ["boot"], "reboot"),
        ("reboot-unknown", "REPAIR POLICY ONLY", ["boot"], "reboot"),
        ("conflict", "INSTALL MODULE AND POLICY", ["patch", "boot"], "reboot"),
        ("missing-summary", "INSTALL MODULE AND POLICY", ["patch", "boot"], "reboot"),
        ("not-installed-summary", "INSTALL MODULE AND POLICY", ["patch", "boot"], "reboot"),
        ("stale", "INSTALL MODULE AND POLICY", ["patch", "boot"], "reboot"),
        ("missing", "INSTALL MODULE AND POLICY", ["patch", "boot"], "reboot"),
    ),
)
def test_privileged_workflow_executes_only_the_selected_action(
    tmp_path, initial_state, decision, actions, final_state
):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    action_log = tmp_path / "actions"
    cmdline = tmp_path / "cmdline"
    state.write_text(initial_state, encoding="utf-8")
    cmdline.write_text(
        "amdgpu.sched_policy=2\n" if initial_state == "ready" else "quiet splash\n",
        encoding="utf-8",
    )
    patch_driver = tmp_path / "patch-driver.sh"
    boot_config = tmp_path / "boot-config.sh"
    patch_driver.write_text(
        '#!/usr/bin/bash\n'
        'if [ "${1:-}" = status ]; then\n'
        '  case "$(cat "$BC250_TEST_STATE")" in\n'
        '    ready) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: installed" ;;\n'
        '    reboot) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: installed" ;;\n'
        '    policy) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] state: incomplete" ;;\n'
        '    active-no-summary) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)" ;;\n'
        '    reboot-unknown) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: unknown" ;;\n'
        '    conflict) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] 6.18.mock: not installed"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: installed" ;;\n'
        '    missing-summary) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: missing" ;;\n'
        '    not-installed-summary) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: not-installed" ;;\n'
        '    stale) echo "[bc250-amdgpu] 6.16.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)"; echo "[bc250-amdgpu] state: installed" ;;\n'
        '    module) echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"; echo "[bc250-amdgpu] state: incomplete" ;;\n'
        '    *) echo "[bc250-amdgpu] state: missing" ;;\n'
        '  esac\n'
        'else echo patch >>"$BC250_TEST_ACTIONS"; echo module >"$BC250_TEST_STATE"; fi\n',
        encoding="utf-8",
    )
    boot_config.write_text(
        '#!/usr/bin/bash\n'
        'if [ "${1:-}" = configured ]; then\n'
        '  case "$(cat "$BC250_TEST_STATE")" in ready|reboot) exit 0 ;; *) exit 1 ;; esac\n'
        'fi\n'
        'echo boot >>"$BC250_TEST_ACTIONS"\necho reboot >"$BC250_TEST_STATE"\n',
        encoding="utf-8",
    )
    for name, body in {
        "sudo": '#!/usr/bin/bash\nexec "$@"\n',
        "uname": '#!/usr/bin/bash\necho 6.18.mock\n',
        "lspci": '#!/usr/bin/bash\necho "0000:01:00.0 0300: 1002:13fe"\n',
    }.items():
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    command = build_steamos_compatibility_command(
        script=patch_driver,
        boot_config=boot_config,
        checkout_command="true",
        install=True,
        cmdline_path=cmdline,
    )
    env = os.environ | {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BC250_TEST_STATE": str(state),
        "BC250_TEST_ACTIONS": str(action_log),
        "XDG_RUNTIME_DIR": str(tmp_path),
    }
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert decision in result.stdout
    observed = action_log.read_text(encoding="utf-8").splitlines() if action_log.exists() else []
    assert observed == actions
    assert state.read_text(encoding="utf-8").strip() == final_state
    assert not list(tmp_path.glob("bc250-amdgpu-status.*"))


def test_policy_repair_validates_persistence_without_requiring_active_boot(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    patch_driver = tmp_path / "patch-driver.sh"
    boot_config = tmp_path / "boot-config.sh"
    action_log = tmp_path / "actions"
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet splash\n", encoding="utf-8")
    patch_driver.write_text(
        '#!/usr/bin/bash\n'
        'if [ -f "$BC250_TEST_POLICY_FLAG" ]; then\n'
        '  echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"\n'
        '  echo "[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)"\n'
        '  if [ "${BC250_POST_STATUS_INVALID:-0}" = 1 ]; then\n'
        '    echo "[bc250-amdgpu] state: unknown"\n'
        '  else\n'
        '    echo "[bc250-amdgpu] state: installed"\n'
        '  fi\n'
        'else\n'
        '  echo "[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware"\n'
        '  echo "[bc250-amdgpu] scheduler policy: incomplete or unrecognized"\n'
        '  echo "[bc250-amdgpu] state: incomplete"\n'
        'fi\n',
        encoding="utf-8",
    )
    boot_config.write_text(
        '#!/usr/bin/bash\n'
        'if [ "${1:-}" = install ]; then echo boot >>"$BC250_TEST_ACTIONS"; : >"$BC250_TEST_POLICY_FLAG"; exit 0; fi\n'
        'if [ "${1:-}" = configured ]; then exit "${BC250_CONFIGURED_RC:-0}"; fi\n'
        'exit 2\n',
        encoding="utf-8",
    )
    for name, body in {
        "sudo": '#!/usr/bin/bash\nexec "$@"\n',
        "uname": '#!/usr/bin/bash\necho 6.18.mock\n',
        "lspci": '#!/usr/bin/bash\necho "0000:01:00.0 0300: 1002:13fe"\n',
    }.items():
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    command = build_steamos_compatibility_command(
        script=patch_driver,
        boot_config=boot_config,
        checkout_command="true",
        install=True,
        cmdline_path=cmdline,
    )
    base_env = os.environ | {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BC250_TEST_ACTIONS": str(action_log),
        "BC250_TEST_POLICY_FLAG": str(tmp_path / "policy-configured"),
        "XDG_RUNTIME_DIR": str(tmp_path),
    }

    success = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=base_env,
    )
    assert success.returncode == 0, success.stderr
    assert "REBOOT REQUIRED" in success.stdout
    assert "scheduler boot policy repaired" in success.stdout

    action_log.unlink()
    (tmp_path / "policy-configured").unlink()
    failure = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=base_env | {"BC250_CONFIGURED_RC": "1"},
    )
    assert failure.returncode == 38
    assert "boot-policy repair did not validate" in failure.stdout
    assert action_log.read_text(encoding="utf-8").splitlines() == ["boot"]
    assert not list(tmp_path.glob("bc250-amdgpu-status.*"))

    action_log.unlink()
    (tmp_path / "policy-configured").unlink()
    invalid_status = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=base_env | {"BC250_POST_STATUS_INVALID": "1"},
    )
    assert invalid_status.returncode == 38
    assert "did not produce verified final toolkit evidence" in invalid_status.stdout
    assert action_log.read_text(encoding="utf-8").splitlines() == ["boot"]
    assert not list(tmp_path.glob("bc250-amdgpu-status.*"))


@pytest.mark.parametrize(
    ("fixture", "returncode", "message"),
    (
        ("ready.txt", 0, "scheduler policy are active"),
        ("reboot_pending.txt", 0, "reboot is pending"),
        ("policy_incomplete.txt", 39, "scheduler policy persistence is incomplete"),
        ("conflicting.txt", 39, "scheduler policy persistence is incomplete"),
        ("conflicting_active_incomplete_summary.txt", 39, "scheduler policy persistence is incomplete"),
        ("active_without_summary.txt", 39, "scheduler policy persistence is incomplete"),
        ("reboot_unknown_summary.txt", 39, "scheduler policy persistence is incomplete"),
        ("conflicting_module.txt", 39, "override is not verified for the running kernel"),
        ("conflicting_missing_summary.txt", 39, "override is not verified for the running kernel"),
        ("not_installed_summary.txt", 39, "override is not verified for the running kernel"),
        ("stale_kernel.txt", 39, "override is not verified for the running kernel"),
        ("missing.txt", 39, "override is not verified for the running kernel"),
    ),
)
def test_read_only_diagnostic_classifies_active_pending_and_broken_states(
    tmp_path, fixture, returncode, message
):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    status = tmp_path / "status.txt"
    cmdline = tmp_path / "cmdline"
    status.write_text((FIXTURES / fixture).read_text(encoding="utf-8"), encoding="utf-8")
    cmdline.write_text(
        "amdgpu.sched_policy=2\n" if fixture == "ready.txt" else "quiet splash\n",
        encoding="utf-8",
    )
    patch_driver = tmp_path / "patch-driver.sh"
    patch_driver.write_text('#!/usr/bin/bash\ncat "$BC250_TEST_STATUS"\n', encoding="utf-8")
    for name, body in {
        "sudo": '#!/usr/bin/bash\nexec "$@"\n',
        "uname": '#!/usr/bin/bash\necho 6.18-test\n',
    }.items():
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    command = build_steamos_amdgpu_diagnostic_command(
        script=patch_driver, cmdline_path=cmdline
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "BC250_TEST_STATUS": str(status),
            "XDG_RUNTIME_DIR": str(tmp_path),
        },
    )

    assert result.returncode == returncode
    assert message in result.stdout
    assert not list(tmp_path.glob("bc250-amdgpu-diagnostic.*"))


def test_read_only_diagnostic_rejects_active_status_when_live_cmdline_disagrees(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    status = tmp_path / "status.txt"
    cmdline = tmp_path / "cmdline"
    status.write_text((FIXTURES / "ready.txt").read_text(encoding="utf-8"), encoding="utf-8")
    cmdline.write_text("quiet amdgpu.sched_policy=1\n", encoding="utf-8")
    patch_driver = tmp_path / "patch-driver.sh"
    patch_driver.write_text('#!/usr/bin/bash\ncat "$BC250_TEST_STATUS"\n', encoding="utf-8")
    for name, body in {
        "sudo": '#!/usr/bin/bash\nexec "$@"\n',
        "uname": '#!/usr/bin/bash\necho 6.18-test\n',
    }.items():
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    command = build_steamos_amdgpu_diagnostic_command(
        script=patch_driver, cmdline_path=cmdline
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "BC250_TEST_STATUS": str(status),
            "XDG_RUNTIME_DIR": str(tmp_path),
        },
    )
    assert result.returncode == 39
    assert "scheduler policy persistence is incomplete" in result.stdout


@pytest.mark.parametrize("mutate_after_attestation", (False, True))
def test_full_install_requires_the_attested_module_to_match_final_status(
    tmp_path, mutate_after_attestation
):
    """A full build cannot report success if the selected module changes later."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    actions = tmp_path / "actions"
    cmdline = tmp_path / "cmdline"
    module_root = tmp_path / "modules"
    module = module_root / "6.18.mock" / "updates" / "amdgpu.ko.zst"
    state.write_text("[bc250-amdgpu] state: missing\n", encoding="utf-8")
    cmdline.write_text("quiet splash\n", encoding="utf-8")
    patch_driver = tmp_path / "patch-driver.sh"
    boot_config = tmp_path / "boot-config.sh"
    patch_driver.write_text(
        '#!/usr/bin/bash\n'
        'if [ "${1:-}" = status ]; then cat "$BC250_TEST_STATE"; exit 0; fi\n'
        'echo patch >>"$BC250_TEST_ACTIONS"\n'
        'mkdir -p "$(dirname "$BC250_TEST_MODULE")"\n'
        'printf initial-module >"$BC250_TEST_MODULE"\n'
        'cat >"$BC250_TEST_STATE" <<\'EOF\'\n'
        '[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware\n'
        '[bc250-amdgpu] scheduler policy: configured; reboot needed (amdgpu.sched_policy=2)\n'
        '[bc250-amdgpu] state: installed\n'
        'EOF\n',
        encoding="utf-8",
    )
    boot_config.write_text(
        '#!/usr/bin/bash\n'
        'case "${1:-}" in\n'
        '  configured) exit 0 ;;\n'
        '  install) echo boot >>"$BC250_TEST_ACTIONS"; '
        'if [ "${BC250_TEST_MUTATE_MODULE:-0}" = 1 ]; then printf changed-module >"$BC250_TEST_MODULE"; fi; exit 0 ;;\n'
        'esac\n'
        'exit 2\n',
        encoding="utf-8",
    )
    for name, body in {
        "sudo": '#!/usr/bin/bash\nexec "$@"\n',
        "uname": '#!/usr/bin/bash\necho 6.18.mock\n',
        "lspci": '#!/usr/bin/bash\necho "0000:01:00.0 0300: 1002:13fe"\n',
        "modinfo": '#!/usr/bin/bash\necho "$BC250_TEST_MODULE"\n',
    }.items():
        path = bindir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    command = build_steamos_compatibility_command(
        script=patch_driver,
        boot_config=boot_config,
        checkout_command="true",
        install=True,
        telemetry_oc_overlay_command='echo overlay >>"$BC250_TEST_ACTIONS"',
        cmdline_path=cmdline,
        module_root=module_root,
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "BC250_TEST_STATE": str(state),
            "BC250_TEST_ACTIONS": str(actions),
            "BC250_TEST_MODULE": str(module),
            "BC250_TEST_MUTATE_MODULE": "1" if mutate_after_attestation else "0",
            "XDG_RUNTIME_DIR": str(tmp_path),
        },
    )

    assert actions.read_text(encoding="utf-8").splitlines() == ["overlay", "patch", "boot"]
    marker = module.parent / ".bc250-control-center-telemetry-oc-2400"
    assert marker.is_file()
    if mutate_after_attestation:
        assert result.returncode == 38
        assert "SteamOS fixes did not validate after installation" in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "Module and boot policy verified" in result.stdout
