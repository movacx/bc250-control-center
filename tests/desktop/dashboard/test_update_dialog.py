"""The update window, from the release notes to "restart to use it"."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel
from bc250cc.infrastructure.self_update import ReleaseAsset, ReleaseInfo
from bc250cc.infrastructure.terminal_repository import TerminalLaunchResult
from frontends.desktop.components import update_dialog as module
from frontends.desktop.components.update_dialog import UpdateDialog, install_progress
from frontends.desktop.i18n import tr

ASSET = ReleaseAsset("bc250-control-center-1.20.0-1-any.pkg.tar.zst", 3, "https://x", "a" * 64)
RELEASE = ReleaseInfo(
    "1.20.0", "v1.20.0", "BC250 Control Center 1.20.0", "2026-09-25T10:00:00Z",
    "## Highlights\n\n- Sensors list.", "https://github.com/x", (ASSET,),
)


class _Watch(QObject):
    finished = pyqtSignal(object, int)


class _Controller:
    def __init__(self, tmp_path: Path):
        self.calls = []
        self.launch = TerminalLaunchResult(
            terminal="konsole", title="update", pid=None,
            status_file=str(tmp_path / "status.txt"), log_file=str(tmp_path / "workflow.log"),
        )
        Path(self.launch.log_file).write_text("", encoding="utf-8")

    def instalar_actualizacion(self, plan, package):
        self.calls.append((plan.kind, plan.manager, package))
        return self.launch


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    host = QWidget()
    host.controller = _Controller(tmp_path)
    host.workflow_watch = _Watch()
    host.console = None
    qtbot.addWidget(host)
    monkeypatch.setattr(module, "fetch_latest_release", lambda: RELEASE)

    def fake_download(asset, directory=None, *, progress=None, cancelled=None, opener=None):
        path = tmp_path / asset.name
        path.write_bytes(b"abc")
        if progress:
            progress(3, 3)
        return path

    monkeypatch.setattr(module, "download_asset", fake_download)
    monkeypatch.setattr(module, "plan_update", lambda release, source, **_kw: module.UpdatePlan(
        "package", asset=ASSET, manager="pacman", summary=ASSET.name,
    ))
    return host


def test_the_notes_come_first_with_the_package_this_system_gets(qtbot, window):
    dialog = UpdateDialog(window, installed="1.19.3", source=InstallSource(UpdateChannel.PACKAGE, manager="pacman"))
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.primary.isEnabled(), timeout=5000)
    assert dialog.title.text() == "BC250 Control Center 1.20.0"
    assert "1.19.3" in dialog.versions.text() and "2026-09-25" in dialog.versions.text()
    assert "Sensors list." in dialog.notes.toPlainText()
    assert ASSET.name in dialog.package_line.text()
    assert dialog.primary.text() == tr("Update now")


def test_update_runs_download_verify_install_and_offers_the_restart(qtbot, window, tmp_path):
    dialog = UpdateDialog(window, installed="1.19.3")
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.primary.isEnabled(), timeout=5000)
    dialog.primary.click()
    controller = window.controller
    qtbot.waitUntil(lambda: bool(controller.calls), timeout=5000)
    assert controller.calls[0][:2] == ("package", "pacman")
    assert dialog.stages["download"].state == "done"
    assert dialog.stages["verify"].state == "done"
    qtbot.waitUntil(lambda: dialog._launch is not None, timeout=5000)

    # The package manager's own phases move the bar forward.
    before = dialog.rail.value
    Path(controller.launch.log_file).write_text(
        "loading packages...\nchecking for file conflicts\n(1/1) upgrading bc250-control-center\n",
        encoding="utf-8",
    )
    dialog._follow_install()
    assert dialog.rail.value > before
    assert "upgrading" in dialog.stages["install"].detail.text()

    window.workflow_watch.finished.emit(controller.launch, 0)
    assert dialog.stages["install"].state == "done"
    assert dialog.stages["finish"].state == "done"
    assert dialog.primary.text() == tr("Restart BC250 Control Center")
    asked = []
    dialog.restart_requested.connect(lambda: asked.append(True))
    dialog.primary.click()
    assert asked == [True]


def test_a_failed_install_says_so_and_keeps_the_bar_where_it_stopped(qtbot, window):
    dialog = UpdateDialog(window, installed="1.19.3")
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.primary.isEnabled(), timeout=5000)
    dialog.primary.click()
    qtbot.waitUntil(lambda: dialog._launch is not None, timeout=5000)
    value = dialog.rail.value
    window.workflow_watch.finished.emit(window.controller.launch, 1)
    assert dialog.stages["install"].state == "failed"
    assert dialog.rail.value >= value
    assert not dialog.release_button.isHidden()


def test_install_progress_only_moves_forward():
    assert install_progress("pacman", ["checking keys"], 0.0) == pytest.approx(0.15)
    assert install_progress("pacman", ["checking keys"], 0.5) == 0.5
    assert install_progress("apt", ["Setting up bc250-control-center"], 0.0) == pytest.approx(0.8)
    assert install_progress("unknown", ["anything"], 0.3) == 0.3


def test_release_notes_get_quiet_headings_lists_and_safe_links():
    from frontends.desktop.components.update_dialog import release_notes_html

    rendered = release_notes_html(
        "## Highlights\n\n- New **sensors** list with `min/max`.\n  continued line\n"
        "- See [the guide](https://example.org/guide).\n\n## Notes\n\n1. First\n2. <script>x</script>\n\nPlain words."
    )
    # Headings are bold paragraphs at text size, the first one without a top gap.
    assert rendered.startswith('<p style="font-weight:700; margin-top:0px;')
    assert "margin-top:12px" in rendered and "<h3>" not in rendered
    assert "<ul>" in rendered and "<ol>" in rendered
    assert "<b>sensors</b>" in rendered and "<code>min/max</code>" in rendered
    assert "continued line</li>" in rendered
    assert '<a href="https://example.org/guide">the guide</a>' in rendered
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert rendered.endswith("<p>Plain words.</p>")


def test_the_status_line_follows_the_step_at_work(qtbot, window):
    dialog = UpdateDialog(window, installed="1.19.3", source=InstallSource(UpdateChannel.PACKAGE, "bc250-control-center", "pacman"))
    qtbot.addWidget(dialog)
    dialog.stages["download"].set_state("done", "3 B")
    dialog.stages["install"].set_state("running", "checking keys")

    assert dialog.status_line.toolTip() == f"{tr('Install')} · checking keys"
    assert dialog._step_lines[0].property("done") is True
    assert not dialog._step_lines[2].property("done")
    dialog.stages["install"].set_state("failed", "exit 1")
    assert dialog.status_line.property("state") == "failed"
