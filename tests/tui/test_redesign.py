"""The shell of the terminal interface: palette, details, activity and one action at a time."""

import subprocess
import sys
import threading
from pathlib import Path

from frontends.tui.content import Choice, Heading, Note, Panel
from frontends.tui.layout import Glyphs, build_page
from frontends.tui.palette import choices_of, matches
from frontends.tui.screen import outcome_of

from .test_screen import make_screen, press

ROOT = Path(__file__).resolve().parents[2]
GLYPHS = Glyphs.for_terminal(unicode_ok=True)


def lines(layout):
    return ["".join(text for text, _tone in row.spans) for row in layout.rows]


def test_every_page_builds_without_qt(tmp_path):
    code = (
        "import sys\n"
        "class NoQt:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] == 'PyQt6': raise ImportError(name)\n"
        "sys.meta_path.insert(0, NoQt())\n"
        "from frontends.tui.pages import build_pages\n"
        "from tests.tui.fakes import FakeUI, make_context\n"
        "ctx = make_context()\n"
        "for page in build_pages().values():\n"
        "    data = page.load(ctx) if page.loads else None\n"
        "    for tab in [key for key, _label in page.tabs(ctx)] or ['']:\n"
        "        page.build(ctx, data, tab, FakeUI())\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                            env={"PYTHONPATH": f"{ROOT}/src:{ROOT}", "PATH": "/usr/bin", "HOME": str(tmp_path)}, check=False)
    assert result.returncode == 0, result.stderr


def test_headings_become_boxes_and_a_loose_button_stays_with_its_group():
    blocks = [Heading("One"), Note("a"), Panel("Two", [Note("b")]), Choice("Apply", lambda ui: None)]
    text = lines(build_page(blocks, 60, GLYPHS))
    assert text[0].startswith("╭─ One") and text[3].startswith("╭─ Two")
    assert "[ Apply ]" in text[5] and text[6].startswith("╰")


def test_groups_share_a_wide_screen_in_reading_order():
    layout = build_page([Panel(name, [Note("x")]) for name in ("A", "B", "C", "D")], 120, GLYPHS)
    first = lines(layout)[0]
    assert "A" in first and "C" in first and "B" not in first


def test_the_palette_ignores_accents_and_finds_actions_by_group():
    _window, screen = make_screen()
    entries = screen.command_entries()
    assert any(entry.page == "extras" and entry.choice is not None for entry in matches(entries, "kernel"))
    assert matches(entries, "GOVERNOR")
    assert not any(entry.page == "remote" and entry.choice for entry in entries)  # credentials live there
    assert [c.label for c, _g in choices_of([Panel("P", [Choice("Desinstalación", lambda ui: None)])])] == ["Desinstalación"]


def test_the_palette_opens_a_section():
    window, screen = make_screen()
    window.queue = [ord(c) for c in "fans"] + [10]
    press(screen, ord(":"))
    assert screen.page_key == "fans"


def test_details_take_a_wide_screen_and_a_box_on_a_narrow_one():
    window, screen = make_screen(height=40, width=150)
    screen.goto("extras")
    screen._focus("content")
    screen.draw()
    assert "Upstream CPU idle" in window.text()
    window, screen = make_screen(height=24, width=80)
    screen.goto("extras")
    screen._focus("content")
    screen.draw()
    assert "remains available" not in window.text()  # one clipped line, the rest behind "i"
    window.queue = [27]
    press(screen, ord("i"))


def test_one_action_at_a_time_and_the_list_remembers_it():
    _window, screen = make_screen()
    screen._foreground = None
    started, go_on = threading.Event(), threading.Event()
    second = []

    def work():
        started.set()
        go_on.wait(5)
        return "done"

    codes = iter([-1])

    def getch():
        if started.is_set() and not second:
            ok, _error = screen.run("Second", lambda: None)
            second.append(ok)
            go_on.set()
        return next(codes, 10)

    screen._getch = getch
    ok, result = screen.run("First", work)
    assert (ok, result) == (True, "done") and second == [False]
    assert [(job.label, job.outcome) for job in screen.activity] == [("First", "completed")]


def test_a_refusal_is_not_a_failure():
    from bc250cc.shared.errors import ActionNeeded
    from bc250cc.shared.operation_contract import OperationCancelled
    from frontends.tui.console import Console

    for error, expected in ((OperationCancelled(), "cancelled"), (ActionNeeded("Prepare first."), "stopped"),
                            (RuntimeError("x"), "failed")):
        console = Console("Action", 10, 60)
        console.finish(False, error)
        assert outcome_of(console) == expected


def test_a_game_row_runs_its_own_action_and_memory_asks_before_the_chosen_policy():
    from frontends.tui.pages.extras import AdditionalSettingsPage

    from .fakes import FakeService, FakeUI, make_context

    service = FakeService()
    service.estado_herramientas_bc250 = lambda: {
        "helixsr": {"installed": True, "current": True, "network_ready": True, "version": "2.0",
                    "games": [{"appid": "7", "kind": "game", "name": "Game", "state": "available"}]},
        "system_setup": {"helper_available": True, "memory": {"policies": ["swap-16"], "swap_targets": {"/home": {}}}}}
    ctx, ui = make_context(service), FakeUI()
    ctx.state("system")["os"] = ("arch", "Arch Linux")
    page = AdditionalSettingsPage()
    data = page.load(ctx)
    service.calls.clear()
    rows = build_page(page.build(ctx, data, "upscaling", ui), 100, GLYPHS).choices
    next(row for row in rows if row.label.startswith("Game · HelixSR")).handler(ui)
    assert service.calls == [("gestionar_helixsr", ("game_install:7",), {})]

    def choice(label):
        return next(row for row in build_page(page.build(ctx, data, "memory", ui), 100, GLYPHS).choices if row.label == label)

    assert not choice("Apply Swap").enabled
    ui.choices = ["swap-16"]
    choice("Swap").handler(ui)
    ui.choices = ["/home"]
    choice("Swapfile location").handler(ui)
    service.calls.clear()
    ui.confirm_answer = False
    choice("Apply Swap").handler(ui)
    assert not service.calls
    ui.confirm_answer = True
    choice("Apply Swap").handler(ui)
    assert service.calls == [("preparar_memoria", ("swap-16", 0), {"takeover_zram": False, "target_mount": "/home"})]


def test_a_saved_cpu_profile_out_of_range_falls_back_to_the_shipped_one():
    from frontends.tui.pages.cpu import PROFILES, valid_profile

    assert valid_profile({"frequency": 9000, "vid": 1050, "temperature": 90}, PROFILES[0]) == PROFILES[0]
    assert valid_profile({"frequency": 3600, "vid": 1050, "temperature": 85, "name": "Mine"}, PROFILES[0])["frequency"] == 3600
