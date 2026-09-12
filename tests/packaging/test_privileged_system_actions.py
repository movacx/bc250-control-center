import runpy
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged" / "helpers"
POLICY = ROOT / "privileged" / "policies" / "io.github.movacx.bc250-control-center.policy"


def test_install_source_preflight_requires_every_packaged_desktop_helper():
    validator = (ROOT / "scripts/qa/validate-install-source.sh").read_text(encoding="utf-8")
    staged = (ROOT / "packaging/scripts/stage-package-root.sh").read_text(encoding="utf-8")

    for helper in (
        "bc250-service-helper",
        "bc250-maintenance-helper",
    ):
        assert validator.count(f"privileged/helpers/{helper}") >= 2
        assert helper in staged

    completed = subprocess.run(
        ["bash", str(ROOT / "scripts/qa/validate-install-source.sh"), str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_every_desktop_helper_has_an_explicit_polkit_action():
    root = ET.parse(POLICY).getroot()
    paths = {
        action.find("annotate").text
        for action in root.findall("action")
        if action.find("annotate") is not None
    }
    expected = {
        "/usr/libexec/bc250-control-center/bc250-cu-helper",
        "/usr/libexec/bc250-control-center/bc250-fan-pwm-helper",
        "/usr/libexec/bc250-control-center/bc250-governor-config-helper",
        "/usr/libexec/bc250-control-center/bc250-core-unlock-helper",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "/usr/libexec/bc250-control-center/bc250-system-setup-helper",
        "/usr/libexec/bc250-control-center/bc250-openrc-service-helper",
        "/usr/libexec/bc250-control-center/bc250-service-helper",
        "/usr/libexec/bc250-control-center/bc250-maintenance-helper",
    }

    assert expected <= paths

    for action in root.findall("action"):
        annotation = action.find("annotate")
        if annotation is None or annotation.text not in expected:
            continue
        defaults = action.find("defaults")
        assert defaults is not None
        assert defaults.findtext("allow_any") == "no"
        assert defaults.findtext("allow_active") in {"auth_admin", "auth_admin_keep"}


def test_service_helper_accepts_only_fixed_governor_restarts(monkeypatch):
    namespace = runpy.run_path(str(HELPERS / "bc250-service-helper"))
    monkeypatch.setitem(namespace["main"].__globals__, "_trusted_self", lambda: True)
    monkeypatch.setitem(namespace["main"].__globals__, "_restart_command", lambda service: [
        "/usr/bin/systemctl", "restart", f"{service}.service"
    ])
    monkeypatch.setattr(namespace["os"], "geteuid", lambda: 0)
    calls = []
    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda command, **_kwargs: calls.append(command) or SimpleNamespace(
            returncode=0, stdout="", stderr=""
        ),
    )

    assert namespace["main"](["restart", "cyan-skillfish-governor-smu"]) == 0
    assert calls == [[
        "/usr/bin/systemctl", "restart", "cyan-skillfish-governor-smu.service"
    ]]
    assert namespace["main"](["shell", "anything"]) == 70


def test_maintenance_helper_writes_only_the_fixed_drop_caches_target(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(HELPERS / "bc250-maintenance-helper"))
    target = tmp_path / "drop_caches"
    target.write_text("")
    globals_ = namespace["main"].__globals__
    monkeypatch.setitem(globals_, "_trusted_self", lambda: True)
    monkeypatch.setitem(globals_, "DROP_CACHES", target)
    monkeypatch.setattr(namespace["os"], "geteuid", lambda: 0)
    synced = []
    monkeypatch.setattr(namespace["os"], "sync", lambda: synced.append(True))

    assert namespace["main"](["drop-caches"]) == 0
    assert target.read_text() == "3\n"
    assert synced == [True]
    assert namespace["main"](["arbitrary-command"]) == 70
