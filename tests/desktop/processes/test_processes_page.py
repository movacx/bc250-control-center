"""The Processes page: filters, sorting, the game card and its actions."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog

from bc250cc.infrastructure.process_inventory import ProcessRecord
from frontends.desktop.pages import processes as page_module
from frontends.desktop.pages.processes import ProcessesPage, build_entries

MB = 1024 * 1024


def _record(pid, app_key, app_name, *, kind="app", memory=100 * MB, cpu=1.0, gpu=None, vram=0,
            protected=False, paused=False, program="", steam_appid=""):
    return ProcessRecord(
        pid=pid, nombre=program or app_name.lower(), memoria=memory, comando=f"/usr/bin/{program or pid}",
        protegido=protected, razon="desktop session" if protected else "", create_time=1000.0 + pid,
        program=program or app_name.lower(), cpu_percent=cpu, gpu_percent=gpu, vram=vram, threads=3,
        paused=paused, app_key=app_key, app_name=app_name, icon="", kind=kind, steam_appid=steam_appid,
    )


def _processes():
    return [
        _record(1, "app:chrome", "Chrome", memory=300 * MB, cpu=4.0),
        _record(2, "app:chrome", "Chrome", memory=200 * MB, cpu=1.0, gpu=2.0, vram=80 * MB),
        _record(3, "app:spotify", "Spotify", memory=400 * MB, cpu=0.5),
        _record(4, "game:1091500", "Cyberpunk 2077", kind="game", memory=6000 * MB, cpu=30.0,
                gpu=95.0, vram=3000 * MB, steam_appid="1091500"),
        _record(5, "game:1091500", "Cyberpunk 2077", kind="game", memory=20 * MB, program="wineserver"),
        _record(6, "program:kwin_wayland", "KWin", kind="system", protected=True, memory=150 * MB),
        _record(7, "program:baloo_file", "Baloo", kind="background", memory=70 * MB, cpu=0.0),
        _record(8, "program:tiny", "Tiny", kind="background", memory=2 * MB, cpu=0.0),
    ]


class _Controller:
    def __init__(self):
        self.calls = []

    def inventario_procesos(self):
        return {"processes": _processes(), "memory": {"total": 16 << 30, "available": 8 << 30, "swap_used": 0},
                "gpu": {"vram_used": 300 * MB, "vram_total": 512 * MB}}

    def pausar_procesos(self, processes, pause):
        self.calls.append(("pause" if pause else "resume", sorted(p.pid for p in processes)))

    def cerrar_procesos(self, processes):
        self.calls.append(("terminate", sorted(p.pid for p in processes)))


class _Activity:
    def record(self, *args, **kwargs):
        return None


def _page(qtbot, monkeypatch):
    controller = _Controller()
    page = ProcessesPage(controller, activity_service=_Activity())
    qtbot.addWidget(page)
    page.resize(1300, 900)
    page.show()
    page._apply_snapshot({**controller.inventario_procesos(), "performance": {"cpu": 40.0, "gpu_busy": 96.0},
                          "refreshed_at": "12:00:00"})
    return page, controller


def _names(page):
    return [entry.name for entry in page._row_entries]


def test_rows_are_applications_with_all_their_processes():
    entries = build_entries(_processes(), grouped=True, view="all")
    chrome = next(entry for entry in entries if entry.name == "Chrome")
    assert len(chrome.processes) == 2 and chrome.memory == 500 * MB
    assert chrome.cpu == 5.0 and chrome.gpu == 2.0 and chrome.vram == 80 * MB
    ungrouped = build_entries(_processes(), grouped=False, view="all")
    assert len(ungrouped) == len(_processes())


def test_the_filters_separate_apps_background_and_system(qtbot, monkeypatch):
    page, _controller = _page(qtbot, monkeypatch)
    assert _names(page) == ["Cyberpunk 2077", "Chrome", "Spotify"], "apps and games, by memory"

    page.filter_buttons["system"].click()
    assert _names(page) == ["KWin"]
    assert page._row_entries[0].status()[0] == "Protected"
    page.filter_buttons["background"].click()
    assert _names(page) == ["Baloo"], "an idle 2 MB helper is left out"
    page.filter_buttons["all"].click()
    assert "Tiny" in _names(page)

    page.filter_buttons["apps"].click()
    page.search.setText("tiny")
    page._apply_text_filter()
    assert _names(page) == ["Tiny"], "a search looks everywhere"


def test_columns_sort_on_a_click_and_flip_on_the_second(qtbot, monkeypatch):
    page, _controller = _page(qtbot, monkeypatch)
    page._header_clicked(2)  # CPU
    assert _names(page) == ["Cyberpunk 2077", "Chrome", "Spotify"]
    page._header_clicked(2)
    assert _names(page) == ["Spotify", "Chrome", "Cyberpunk 2077"]
    assert page.table.horizontalHeaderItem(2).text().endswith("▴")
    page._header_clicked(1)  # name, A to Z first
    assert _names(page) == ["Chrome", "Cyberpunk 2077", "Spotify"]


def test_the_game_in_play_gets_its_card_and_can_be_paused(qtbot, monkeypatch):
    page, controller = _page(qtbot, monkeypatch)
    assert not page.game_card.isHidden()
    assert page.game_name.text() == "Cyberpunk 2077"
    assert "GPU 95 %" in page.game_metrics.text() and "Steam 1091500" in page.game_metrics.text()

    monkeypatch.setattr(page_module.ProcessTask, "start", lambda self: self.run())
    page.game_pause_button.click()

    assert controller.calls[0] == ("pause", [4, 5]), "the game and its Wine server"


def test_pause_and_end_send_only_what_may_be_ended(qtbot, monkeypatch):
    page, controller = _page(qtbot, monkeypatch)
    monkeypatch.setattr(page_module.ProcessTask, "start", lambda self: self.run())
    page.filter_buttons["all"].click()
    page.select_safe_visible()
    assert "KWin" not in {entry.name for entry in page._selected_entries()}

    page.pause_selected()
    assert controller.calls[-1][0] == "pause" and 6 not in controller.calls[-1][1]

    class Confirm:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(page_module, "ConfirmDialog", Confirm)
    page.filter_buttons["apps"].click()
    page.table.setCurrentCell(1, 1)  # nothing ticked: Delete ends the row under the cursor
    page.terminate_selected()
    assert controller.calls[-1] == ("terminate", [1, 2])


def test_a_paused_application_offers_resume(qtbot, monkeypatch):
    page, controller = _page(qtbot, monkeypatch)
    processes = _processes()
    for process in processes:
        if process.app_key == "app:spotify":
            process.paused = True
    page._apply_snapshot({"processes": processes, "refreshed_at": "12:00:03"})
    spotify = next(row for row, entry in enumerate(page._row_entries) if entry.name == "Spotify")
    page._row_clicked(spotify, 1)

    assert page._row_entries[spotify].status()[0] == "Paused"
    assert page.pause_button.text() == "Resume"


def test_a_group_never_adds_pss_and_rss_together():
    measured = ProcessRecord(pid=1, memoria=100 * MB, rss=150 * MB, pss=100 * MB, app_key="app:a", app_name="A")
    denied = ProcessRecord(pid=2, memoria=300 * MB, rss=300 * MB, pss=None, app_key="app:a", app_name="A")
    whole = build_entries([measured], grouped=True, view="all")[0]
    assert whole.memory_exact and whole.memory == 100 * MB and not whole.memory_tooltip()
    mixed = build_entries([measured, denied], grouped=True, view="all")[0]
    assert not mixed.memory_exact and mixed.memory == 450 * MB, "every process by RSS"
    assert mixed.memory_tooltip()


def test_gpu_memory_is_vram_and_gtt():
    record = ProcessRecord(pid=1, memoria=100 * MB, vram=200 * MB, gtt=1800 * MB, app_key="app:a", app_name="A")
    entry = build_entries([record], grouped=True, view="all")[0]
    assert entry.vram == 2000 * MB
    assert "GTT" in entry.gpu_memory_tooltip()


def test_the_application_name_follows_the_language(monkeypatch):
    record = ProcessRecord(pid=1, memoria=100 * MB, app_key="app:files", app_name="Files",
                           app_names={"es": "Archivos", "de": "Dateien"})
    monkeypatch.setattr(page_module, "current_language", lambda: "es-419")
    assert build_entries([record], grouped=True, view="all")[0].name == "Archivos"
    monkeypatch.setattr(page_module, "current_language", lambda: "fr")
    assert build_entries([record], grouped=True, view="all")[0].name == "Files"


def test_a_paused_game_warns_when_systemd_oomd_may_end_steam(qtbot, monkeypatch):
    page, controller = _page(qtbot, monkeypatch)
    assert page.game_note.isHidden()
    processes = _processes()
    for process in processes:
        if process.kind == "game":
            process.paused = True
    page._apply_snapshot({"processes": processes, "oomd": True, "performance": {}, "refreshed_at": "12:00:01"})
    assert not page.game_note.isHidden()
    page._apply_snapshot({"processes": processes, "oomd": False, "performance": {}, "refreshed_at": "12:00:02"})
    assert page.game_note.isHidden()
