"""Each distribution is offered what the desktop offers it, and nothing is authorized through polkit."""

import pytest

from frontends.tui.pages.dashboard import DashboardPage
from frontends.tui.pages.extras import AdditionalSettingsPage

from .fakes import FakeService, FakeUI, make_context
from .test_pages import render, text_of


def page_for(family, tab="compatibility", **tools):
    service = FakeService()
    service.estado_herramientas_bc250 = lambda: {"os_family": family, **tools}
    ctx, ui = make_context(service), FakeUI()
    ctx.state("system")["os"] = (family, family)
    return render(AdditionalSettingsPage(), ctx, ui, tab), service, ui


def labels(layout):
    return " | ".join(choice.label for choice in layout.choices)


def names_in(layout):
    return text_of(layout)


ACTIVE_ACPI = {"helper_available": True, "acpi": {"status": "active"}}


@pytest.mark.parametrize("family,status,shown", [
    ("arch", "", True), ("cachyos", "", True), ("bazzite", "", True), ("fedora", "", False), ("ubuntu", "", False),
    ("steamos", "", False), ("steamos", "active", True)])
def test_our_acpi_correction_is_offered_where_the_desktop_offers_it(family, status, shown):
    layout, _service, _ui = page_for(family, system_setup={"helper_available": True, "acpi": {"status": status}})
    assert ("CPU power management" in names_in(layout)) is shown


@pytest.mark.parametrize("family", ["arch", "cachyos", "manjaro", "fedora", "bazzite", "ubuntu", "debian", "alpine", "gentoo"])
def test_steamos_rows_never_appear_elsewhere(family):
    toolkit = {"installed": True}
    layout, _service, _ui = page_for(family, steamos_real_toolkit=toolkit)
    text = names_in(layout)
    assert "SteamOS" not in text and "rpf16rj" not in text and "keyboardspecialist" not in text


def test_steamos_gets_its_toolkit_and_not_our_copies_of_it():
    accessories = {"hdmi_ac3": {"state": "not-installed"}, "hdmi_cec": {"state": "not-installed"}, "thermalright": {"state": "not-installed"}}
    tools = {"steamos_real_toolkit": {"installed": True}, "vaapi_video": {"state": "not-installed", "supported": True},
             "directmesh": {"supported": True}, "accessories": accessories}
    layout, _service, _ui = page_for("steamos", **tools)
    text = names_in(layout)
    assert "rpf16rj" in text and "BC250 SteamOS diagnostics" in text
    assert "GFX1013 async compute" not in text and "MastaG" not in text
    drivers = names_in(page_for("steamos", "drivers", **tools)[0])
    assert "Printing" not in drivers and "Dolby" not in drivers and "HDMI-CEC" not in drivers and "Thermalright" in drivers
    # One of ours that is already installed stays manageable.
    tools["accessories"] = {"hdmi_ac3": {"state": "installed"}}
    assert "Dolby" in names_in(page_for("steamos", "drivers", **tools)[0])


GFX = "GFX1013 async compute ›"


def gfx_actions(family, state, **more):
    layout, service, ui = page_for(family, gfx1013_compute=state, **more)
    row = next((c for c in layout.choices if c.label.startswith("GFX1013")), None)
    if row is None:
        return None
    offered = []
    ui.choose = lambda _title, options: offered.extend(text for _key, text in options)
    ui.confirm = lambda message, danger=False: offered.append(message) and False
    row.handler(ui)
    return offered


def test_gfx1013_offers_the_one_route_of_this_kernel_and_install():
    radv = {"supported": True, "state": "not-installed"}
    assert "Build and install" in gfx_actions("arch", {"radv_async": radv})[0]
    on = {"supported": True, "state": "active", "installed": True, "enabled": True}
    assert gfx_actions("cachyos", {"radv_async": on}) == ["Switch off", "Test async compute", "Remove"]
    source = {"supported": True, "state": "rebuild-needed", "installed": True}
    assert gfx_actions("ubuntu", {"source": source}) == ["Rebuild for this kernel", "Remove the fix"]
    assert "Install / update" in gfx_actions("fedora", {"reason_key": "fedora-upstream-managed"})[0]
    assert gfx_actions("bazzite", {"reason_key": "bazzite-release-kernel-unsupported"}) == []
    assert gfx_actions("arch", {"radv_async": radv, "masta_async_compute_ready": True}) is None
    assert gfx_actions("debian", {"source": {"hide_offer": True}}) is None
    assert "Install from backports" in gfx_actions("debian", {"source": {"hide_offer": True}, "kernel_upgrade": {"offered": True}})[0]


def test_mastag_packages_follow_what_is_supported_and_installed():
    stack = {"supported": True, "kernel_installed": True, "mesa_installed": True, "kernel_active": True,
             "proton_installed": {"native": True}, "extras_installed": {"fixes": True}}
    layout, service, ui = page_for("cachyos", masta_bc250_stack=stack)
    assert "Full stack installed" in text_of(layout) and "Proton BC-250" in text_of(layout)
    row = next(c for c in layout.choices if c.label.startswith("Proton BC-250"))
    ui.choose = lambda _title, options: next(key for key, text in options if text.startswith("Remove"))
    row.handler(ui)
    assert ("preparar_cachyos_bc250", ("remove-proton-native",), {}) in service.calls
    assert "Not compatible" in text_of(page_for("manjaro", masta_bc250_stack={"supported": False})[0])
    assert "MastaG" not in text_of(page_for("fedora", masta_bc250_stack=stack)[0])


def test_mesa_and_decky_appear_only_when_this_system_offers_them():
    assert "Mesa too old" not in text_of(page_for("ubuntu")[0])
    assert "Mesa too old" in text_of(page_for("ubuntu", mesa_desktop={"offered": True, "route": "ppa"})[0])

    def prepare(family, quick):
        service = FakeService()
        service.estado_herramientas_bc250 = lambda: {"quick_access": quick}
        ctx, ui = make_context(service), FakeUI()
        ctx.state("system")["os"] = (family, family)
        return render(DashboardPage(), ctx, ui, "prepare")
    assert "Decky" not in text_of(prepare("gentoo", {}))
    assert "Install Decky + Quick Access (Beta)" in labels(prepare("bazzite", {"supported": True}))
    assert "Install / repair BC250 Quick Access" in labels(prepare("steamos", {"supported": True, "decky_detected": True}))
    chosen = labels(prepare("debian", {}))
    assert "[x] Base dependencies" in chosen and "[ ] UMR database" in chosen  # UMR may build LLVM there


def test_nothing_asked_from_the_terminal_interface_goes_through_polkit(monkeypatch, tmp_path):
    from bc250cc.infrastructure import polkit_session as auth
    from bc250cc.infrastructure.firmware.udisks import UDisksClient
    from bc250cc.infrastructure.self_update import _rpm_ostree_install

    monkeypatch.delenv(auth.WEB_SUDO_AUTH_ENV, raising=False)
    monkeypatch.setenv(auth.TERMINAL_AUTH_ENV, "1")
    token = auth.TERMINAL_AGENT_READY.set(True)
    seen = []

    def runner(command, **kwargs):
        from types import SimpleNamespace
        seen.append((command, kwargs["env"]))
        return SimpleNamespace(returncode=0, stdout='{"data": ["/media/x"]}', stderr="")
    try:
        UDisksClient(runner)._call("/p", "i", "Mount", "a{sv}", "0")
        assert "terminal_sudo.py" in " ".join(seen[-1][0]) and "pkexec" not in seen[-1][0]
        UDisksClient(runner).property("/p", "i", "Name")
        assert seen[-1][0][0] == "busctl"  # a reading needs nobody's permission
        script = _rpm_ostree_install("/tmp/x.rpm")
        assert "sudo rpm-ostree" in script and "LANGUAGE=C rpm-ostree" not in script
    finally:
        auth.TERMINAL_AGENT_READY.reset(token)


def test_no_service_names_pkexec_directly():
    """Everything privileged is built by pkexec_argv/pkexec_prefix, which is where sudo takes over."""
    import ast
    from pathlib import Path

    found = []
    for path in Path("src/bc250cc").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "pkexec" \
                    and len(node.elts) > 1:
                found.append(f"{path}:{node.lineno}")
    assert not found, found


def test_preparing_from_the_terminal_interface_needs_neither_polkit_nor_qt(tmp_path):
    """On a TTY-only system: the packages, the checks and the closing verification ask for sudo and curses."""
    import os
    import subprocess
    from pathlib import Path

    from bc250cc.application.preparation.component_engine import verification_shell

    root = Path("packaging/common/os-scripts")
    for family in ("arch", "bazzite", "fedora", "steamos", "debian", "alpine", "gentoo"):
        text = (root / family / "prepare-dependencies.sh").read_text()
        assert "verify_command pkexec" not in text and "import PyQt6" not in text and "bc250_fit_packages_to_interface" in text, family
    script = ('have() { :; }; source <(sed -n "/^# The terminal interface authorizes/,\\$p" ' + str(root / "common/common.sh") + '); '
              'p=(python python-pyqt6 qt6-svg polkit py3-qt6 libqt6svg6 dev-qt/qtbase sys-auth/polkit jq); '
              'bc250_fit_packages_to_interface p; echo "${p[*]}"')
    for auth, expected in (("1", "python jq"), ("0", "python python-pyqt6 qt6-svg polkit py3-qt6 libqt6svg6 dev-qt/qtbase sys-auth/polkit jq")):
        done = subprocess.run(["bash", "-c", script], env={**os.environ, "BC250_TERMINAL_AUTH": auth}, capture_output=True, text=True)
        assert done.stdout.strip() == expected, done.stderr
    for name in ("python3", "git", "lspci", "sudo"):
        (tmp_path / name).write_text('#!/bin/sh\ncase "$*" in *PyQt6*) exit 1;; esac\n')
        (tmp_path / name).chmod(0o755)
    checks = verification_shell(["runtime"], governor_binary="x", cpu_oc_script=Path("x"), core_unlock_script=Path("x"),
                                cu_manager_script=Path("x"))[:2]
    bash = "/bin/bash"
    for auth, status in (("1", 0), ("0", 34)):
        done = subprocess.run([bash, "-c", "; ".join(checks)], env={"PATH": str(tmp_path), "BC250_TERMINAL_AUTH": auth}, capture_output=True)
        assert done.returncode == status, done.stdout
