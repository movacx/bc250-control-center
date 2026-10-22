"""The CPU page's Decky export says whether Decky can use the profiles yet."""

from __future__ import annotations

from types import SimpleNamespace

from frontends.desktop.pages import cpu_control_integration as integration


class _Background:
    def start(self, _name, operation, success, failure, finished=None):
        try:
            result = operation()
        except Exception as error:  # noqa: BLE001 - mirrors the real executor
            failure(str(error))
        else:
            success(result)
        if finished is not None:
            finished()


class _Button:
    def __init__(self):
        self.states = []

    def setEnabled(self, enabled):  # noqa: N802 (Qt)
        self.states.append(enabled)


def _export(inventory=None, profiles=(), button=None, fail=False):
    exported, notices = [], []

    def export(payload):
        if fail:
            raise RuntimeError("no password")
        exported.append(payload)

    controller = SimpleNamespace(exportar_perfiles_cpu_decky=export)
    if inventory is not None:
        controller.estado_quick_access_decky = lambda: inventory
    page = SimpleNamespace(
        controller=controller,
        _background=_Background(),
        _show_info=lambda title, message, *, tone: notices.append((title, message, tone)),
    )
    view = SimpleNamespace(profiles=lambda: list(profiles), _export_decky_button=button or _Button())
    integration.CpuControlController._export_profiles_to_decky(SimpleNamespace(page=page, view=view))
    return exported, notices


def test_an_export_without_the_plugin_says_it_is_not_installed_yet():
    _exported, notices = _export({"decky_detected": True, "plugin_present": False})

    [(title, message, tone)] = notices
    assert title == "Export to Decky" and tone == "blue"
    assert "the plugin is not installed yet" in message


def test_an_export_with_the_plugin_or_an_unreadable_inventory_says_exported():
    for inventory in ({"decky_detected": True, "plugin_present": True}, None):
        _exported, notices = _export(inventory)
        assert notices == [("Export to Decky", "Profiles exported to Decky Quick Access.", "green")]


def test_names_are_exported_untranslated(monkeypatch):
    monkeypatch.setattr(integration, "tr", lambda text, *_args, **_kwargs: f"<{text}>")
    profiles = [
        SimpleNamespace(key="board_average", name="Average board", frequency_mhz=3550, vid_mv=1050, temperature_c=90),
        SimpleNamespace(key="mid_point", name="Mío", frequency_mhz=3850, vid_mv=1150, temperature_c=75),
    ]

    exported, _notices = _export(profiles=profiles)

    assert [entry["name"] for entry in exported[0]] == ["Average board", "Mío"]


def test_each_cards_temperature_cap_is_exported_with_it():
    profiles = [
        SimpleNamespace(key="board_average", name="A", frequency_mhz=3550, vid_mv=1050, temperature_c=90),
        SimpleNamespace(key="safe_maximum", name="S", frequency_mhz=4000, vid_mv=1275, temperature_c=72),
    ]

    exported, _notices = _export(profiles=profiles)

    assert [(entry["key"], entry["temperature"]) for entry in exported[0]] == [
        ("board_average", 90), ("safe_maximum", 72),
    ]


def test_the_export_button_is_off_while_exporting_and_back_on_after():
    for fail in (False, True):
        button = _Button()

        _export(button=button, fail=fail)

        assert button.states == [False, True]
