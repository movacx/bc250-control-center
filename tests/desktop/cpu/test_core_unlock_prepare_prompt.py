"""A missing or outdated unlock tool offers Prepare dependencies, not a dead end.

Updating Control Center moves the reviewed revision of the core unlock tool;
the owner's clone stays at the old one. The dialog used to only say "use
Prepare dependencies". It now tells an older copy (a new version to fetch)
from a missing one, and its button starts the preparation.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages import cpu_smu
from frontends.desktop.pages.cpu_smu import CpuSmuPage


def _page(monkeypatch, *, present: bool, answer=QDialog.DialogCode.Accepted):
    shown, prepared, started = [], [], []

    class Dialog:
        def __init__(self, title, message, *, confirm_text="", eyebrow="", **_):
            shown.append({"title": title, "message": message, "button": confirm_text, "eyebrow": eyebrow})

        def exec(self):
            return answer

    monkeypatch.setattr(cpu_smu, "ConfirmDialog", Dialog)
    signal = type("Signal", (), {"emit": lambda self: prepared.append(True)})()
    page = type("Page", (), {
        "_request_core_unlock": CpuSmuPage._request_core_unlock,
        "_offer_core_unlock_preparation": CpuSmuPage._offer_core_unlock_preparation,
        "prepare_dependencies_requested": signal,
        "process": None,
        "current_state": {
            "core_unlock_repository_ready": False,
            "core_unlock_repository_present": present,
            "core_unlock_helper_ready": True,
        },
        "_build_and_start_process": lambda self, *args: started.append(args),
    })()
    return page, shown, prepared, started


def test_an_older_copy_reads_as_a_new_version_and_prepares_it(monkeypatch):
    page, shown, prepared, started = _page(monkeypatch, present=True)
    page._request_core_unlock()
    assert shown == [{
        "title": cpu_smu.CORE_UNLOCK_UPDATE_TITLE,
        "message": cpu_smu.CORE_UNLOCK_UPDATE_MESSAGE,
        "button": "Prepare dependencies",
        "eyebrow": "UPDATE AVAILABLE",
    }]
    assert prepared == [True]
    assert started == []  # nothing runs against the old copy


def test_a_missing_tool_says_so_and_prepares_it(monkeypatch):
    page, shown, prepared, _started = _page(monkeypatch, present=False)
    page._request_core_unlock()
    assert shown[0]["title"] == "Official CPU core unlock tool is not prepared"
    assert shown[0]["eyebrow"] == cpu_smu.CORE_UNLOCK_MISSING_EYEBROW
    assert shown[0]["button"] == "Prepare dependencies"
    assert prepared == [True]


def test_closing_the_dialog_prepares_nothing(monkeypatch):
    page, shown, prepared, started = _page(
        monkeypatch, present=True, answer=QDialog.DialogCode.Rejected
    )
    page._request_core_unlock()
    assert len(shown) == 1 and prepared == [] and started == []


def test_every_new_string_is_translated():
    import json
    from pathlib import Path

    strings = (
        cpu_smu.CORE_UNLOCK_UPDATE_TITLE,
        cpu_smu.CORE_UNLOCK_UPDATE_MESSAGE,
        cpu_smu.CORE_UNLOCK_MISSING_EYEBROW,
    )
    locales = Path(cpu_smu.__file__).resolve().parents[1] / "i18n" / "locales"
    for path in sorted(locales.glob("*.json")):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        assert all(catalog.get(text) for text in strings), path.name
        if path.stem != "en":
            # The message names the button the owner has to press.
            assert catalog["Prepare dependencies"] in catalog[cpu_smu.CORE_UNLOCK_UPDATE_MESSAGE], path.name
