"""Every action of every page reaches the services only inside ``ui.run``: the console pane.

``ui.run`` is where workflows meet the embedded launcher, sudo and the Polkit
agent, so a service call outside it is the one way an action could fall back to
a terminal window or ask for a password where nobody sees it.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from frontends.tui.pages import build_pages
from frontends.tui.pages import firmware as firmware_page
from frontends.tui.pages import settings as settings_page

from .fakes import FakeService, FakeUI, make_context
from .test_pages import render

ROOT = Path(__file__).resolve().parents[2]


class Watched(FakeService):
    inside = False
    outside: list[str] = []

    def diagnostico_completo(self):
        assert Watched.inside
        return [("Kernel log", "text")]

    def __getattr__(self, name):
        call = super().__getattr__(name)

        def watched(*args, **kwargs):
            if not Watched.inside and not name.startswith(("estado_", "ultima_", "obtener_estado")):
                Watched.outside.append(name)
            return call(*args, **kwargs)
        return watched


class Console(FakeUI):
    """Says yes, picks the first option, and marks the time spent inside run()."""

    def choose(self, title, options):
        return options[0][0] if options else None

    def ask_text(self, label, default="", **_kwargs):
        return default or "x"

    def run(self, label, work):
        Watched.inside = True
        try:
            return super().run(label, work)
        finally:
            Watched.inside = False

    def shell(self, command):
        assert Watched.inside, "a command line outside the console"
        return ""

    def apply_theme(self, theme):
        pass

    def goto(self, key):
        pass


@pytest.fixture(autouse=True)
def nothing_real(monkeypatch):
    """This test answers yes to every confirmation, so nothing it reaches may be real.

    Pages that call an application facade directly (firmware, diagnostics,
    updates, reports) get stand-ins, and starting any process fails the test:
    an earlier version of it reached the real USB preparation.
    """
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError(f"a real process was started: {args[:1]}")

    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(subprocess, "run", refuse)
    for name in ("install_update", "report", "check_in_background"):
        monkeypatch.setattr(settings_page, name, lambda *a, **k: None)

    def prepare_update_usb(*args, **kwargs):
        assert Watched.inside, "USB preparation outside the console"
        return SimpleNamespace(files=1, bytes_written=0), []

    drive = SimpleNamespace(display_name="Test stick", size=8 * 2**30, eligible=True, blocker=lambda: "")
    board = SimpleNamespace(board="BC-250", vendor="AMD", version="P3.00", date="", is_bc250=True)
    monkeypatch.setattr(firmware_page, "firmware_snapshot", lambda: SimpleNamespace(
        board=board, installed=SimpleNamespace(variant="", evidence=""), drives=[drive]))
    monkeypatch.setattr(firmware_page, "prepare_update_usb", prepare_update_usb)
    monkeypatch.setattr("bc250cc.application.system.diagnostics.collect_diagnostics", lambda: "report")
    yield
    from frontends.tui.i18n import set_language

    set_language("en")  # the Language action picks the first option, "auto": the next tests read English


def test_every_action_of_every_page_calls_services_only_inside_the_console():
    Watched.outside = []
    ctx, ui = make_context(Watched()), Console()
    tried = 0
    for key, page in build_pages().items():
        for tab, _label in page.tabs(ctx) or [("", "")]:
            for choice in render(page, ctx, ui, tab).choices:
                if choice.handler is not None and choice.pad is None and choice.enabled:
                    choice.handler(ui)
                    tried += 1
    assert tried > 80
    assert not Watched.outside, f"service calls outside the console pane: {sorted(set(Watched.outside))}"


def test_the_interface_starts_no_process_of_its_own_except_on_the_console_pty():
    for path in (ROOT / "frontends" / "tui").rglob("*.py"):
        if path.name == "console.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not names & {"Popen", "run_command", "system", "endwin", "def_prog_mode"} - {"run"}, path
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        assert "subprocess" not in imports, path
