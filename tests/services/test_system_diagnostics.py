"""The hardware evidence a problem report carries without asking for root."""

from __future__ import annotations

from pathlib import Path

from bc250cc.infrastructure import system_diagnostics as diag


def test_a_spam_of_one_kernel_message_collapses_to_one_line():
    lines = [f"[ {10 + n}.0] host kernel: amdgpu 0000:01:00.0: Unsupported clock type" for n in range(72)]
    lines.append("[ 1810.6] host kernel: amdgpu 0000:01:00.0: ring gfx_0.0.0 timeout")
    collapsed = diag._collapse_repeats(lines)
    assert collapsed == [lines[0], "  (previous line repeated 72 times)", lines[-1]]


def test_a_cut_log_keeps_its_last_lines():
    text = "[journalctl -k, filtered]\n" + "\n".join(f"line {n}" for n in range(2000))
    clipped = diag._clip_tail(text, 300)
    assert len(clipped) <= 300
    assert clipped.startswith("[journalctl -k, filtered]\n(… earlier lines cut)")
    assert clipped.endswith("line 1999")


def test_one_unreadable_section_does_not_hide_the_others():
    def broken():
        raise PermissionError("denied")

    text = diag.collect_diagnostics((("Broken", broken), ("Kernel", lambda: "Linux 7.1")))
    assert "== Broken ==\n(could not be read: PermissionError)" in text
    assert "== Kernel ==\nLinux 7.1" in text


def test_the_home_folder_never_leaves_the_machine():
    home = str(Path.home())
    text = diag.collect_diagnostics((("Files", lambda: f"{home}/homebrew/plugins"),))
    assert home not in text


def test_the_whole_report_fits_the_forms_answer():
    sections = tuple((f"S{n}", lambda: "x" * 10_000) for n in range(12))
    text = diag.collect_diagnostics(sections)
    assert len(text) <= diag.TOTAL_LIMIT


def test_a_missing_command_reads_as_blank(monkeypatch):
    monkeypatch.setattr(diag.shutil, "which", lambda _name: None)
    assert diag._run(["journalctl", "-k"]) == ""


def test_system_setup_helper_reports_the_reasons(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.system_setup.inventory",
        lambda: {"helper_available": True, "reason": "", "memory": {"supported": False, "reason": "immutable", "policies": ["preserve"], "zram": "active"}, "ttm": {"supported": False, "managed": False, "reason": "locked"}, "vram": {"supported": True, "reason": ""}},
    )
    text = diag._system_setup_helper()
    assert "helper_available: True" in text
    assert "memory.reason: immutable" in text
    assert "ttm.managed: False" in text
    assert "vram.supported: True" in text


def test_graphics_stack_includes_icd_environment_and_summary(monkeypatch):
    monkeypatch.setenv("VK_ICD_FILENAMES", "/tmp/radv.json")
    monkeypatch.setattr(diag.glob, "glob", lambda pattern: ["/usr/share/vulkan/icd.d/radeon.json"] if "icd.d" in pattern else [])
    monkeypatch.setattr(diag, "_read", lambda path, *args: '{"ICD": "RADV"}' if str(path).endswith(".json") else "")
    monkeypatch.setattr(diag, "_run", lambda argv, **kwargs: "Mesa 26 / RADV" if argv[0] == "vulkaninfo" else "")
    text = diag._graphics_stack()
    assert "VK_ICD_FILENAMES: /tmp/radv.json" in text
    assert "Mesa 26 / RADV" in text


def test_messages_that_differ_only_in_a_number_are_one_message():
    lines = [f"[ 9.{n}] host kernel: amdgpu: Failed to clear hpd(rx) source={n} on init" for n in range(3, 12)]
    lines.append("[ 1810.6] host kernel: amdgpu: ring gfx_0.0.0 timeout")
    grouped = diag._group_similar(lines)
    assert grouped == [lines[0] + "  (×9)", lines[-1]]


def test_the_boot_inventory_is_not_a_gpu_problem():
    noise = (
        "[ 4.1] host kernel: thermal_sys: Registered thermal governor 'step_wise'",
        "[ 9.5] host kernel: amdgpu 0000:01:00.0: Trusted Memory Zone (TMZ) feature disabled as experimental (default)",
        "[ 15.4] host kernel: warning: `kdeconnectd' uses wireless extensions",
        "[ 4.1] host kernel: NMI watchdog: Enabled. Permanently consumes one hw-PMU counter.",
    )
    real = (
        "[ 1810.6] host kernel: amdgpu 0000:01:00.0: ring gfx_0.0.0 timeout, signaled seq=1",
        "[ 10.7] host kernel: WARNING: drivers/gpu/drm/amd/display/dc/irq/irq_service.c:169",
        "[ 4.1] host kernel: x86/amd: Previous system reset reason [0x40010400]: system reset pin BP_SYS_RST_L was tripped",
    )
    assert not [line for line in noise if diag._GPU_LOG.search(line)]
    assert all(diag._GPU_LOG.search(line) for line in real)


def test_the_fan_chip_lines_survive_a_noisy_gpu_boot(monkeypatch):
    gpu_noise = [f"[ 10.{n:04d}] host kernel: amdgpu 0000:01:00.0: ring comp_1.{n}.0 uses VM inv eng {n} on hub 0"
                 for n in range(3000)]
    refused = "[ 5.18] host kernel: nct6687: force=1 refused: chip ID 0xffff is outside the Nuvoton NCT668x range"
    log = "\n".join([refused, *gpu_noise, "[ 10.75] host kernel: Modules linked in: nct6687(OE) amdgpu"])
    monkeypatch.setattr(diag, "_KERNEL_CACHE", {"0": (log, "journalctl -k")})
    text = diag._fan_log()
    assert refused in text and "Modules linked in" not in text


def test_the_kernel_log_falls_back_to_polkit_only_when_closed(monkeypatch):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv[0])
        return "polkit dmesg" if argv[0] == "pkexec" else ""

    monkeypatch.setattr(diag, "_run", run)
    assert diag._kernel_text("0") == ("polkit dmesg", "dmesg via polkit")
    assert calls == ["journalctl", "dmesg", "pkexec"]
    calls.clear()
    assert diag._kernel_text("-1") == ("", "journalctl -k")
    assert calls == ["journalctl"]


def test_raw_helper_run_reports_exit_code_and_stderr(monkeypatch, tmp_path):
    helper = tmp_path / "helper"
    helper.write_text("x")
    monkeypatch.setattr("bc250cc.infrastructure.system_setup.HELPER", helper)
    done = diag.subprocess.CompletedProcess([], 3, stdout="not json", stderr="boom")
    monkeypatch.setattr(diag.subprocess, "run", lambda *a, **k: done)
    text = "\n".join(diag._raw_helper_run())
    assert "exit code: 3" in text and "boom" in text and "not valid JSON" in text
    monkeypatch.setattr("bc250cc.infrastructure.system_setup.HELPER", tmp_path / "none")
    assert "missing" in "\n".join(diag._raw_helper_run())


def test_the_kernel_log_needs_a_password_only_when_nothing_reads_it(monkeypatch):
    monkeypatch.setattr(diag, "_run", lambda argv, **kwargs: "")
    assert diag.kernel_log_needs_password() is True
    monkeypatch.setattr(diag, "_run", lambda argv, **kwargs: "line" if argv[0] == "dmesg" else "")
    assert diag.kernel_log_needs_password() is False
    monkeypatch.setattr(diag, "_run", lambda argv, **kwargs: "line" if argv[0] == "journalctl" else "")
    assert diag.kernel_log_needs_password() is False


def test_the_password_check_never_raises(monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(diag, "_run", broken)
    assert diag.kernel_log_needs_password() is False
