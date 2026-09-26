"""Exporting the GPU profiles to Decky says so, like the CPU and Fans pages.

Nothing on the GPU page changes after an export, so a result written only to
the console looked like a click that was ignored.
"""

from __future__ import annotations

from types import SimpleNamespace

from frontends.desktop.pages import gpu_governor_integration as integration


class _Page:
    def __init__(self):
        self.notices = []
        self.console = []
        self.exported = []
        self.controller = SimpleNamespace(exportar_perfiles_gpu_decky=self._export)

    def _export(self, payload):
        self.exported.append(payload)
        return "Decky GPU profiles published."

    def _run_backend_action(self, operation, on_success, error_title, *, controls=()):
        on_success(operation())
        return True

    def _append_console(self, message):
        self.console.append(message)

    def _show_info(self, title, message, *, tone="blue", **_kwargs):
        self.notices.append((title, message, tone))


def test_a_successful_export_is_reported_by_a_green_toast():
    page = _Page()
    profile = SimpleNamespace(key="balanced", name="Balanced", minimum=1000, maximum=2000)
    view = SimpleNamespace(profiles=lambda: [profile], _export_decky_button=None)

    integration._export_profiles_to_decky(page, view)

    assert page.exported == [[{"key": "balanced", "name": "Balanced", "min": 1000, "max": 2000}]]
    assert page.notices == [("Export to Decky", "Profiles exported to Decky Quick Access.", "green")]
    assert page.console  # the console line stays


def test_other_gpu_operations_keep_reporting_only_in_the_console():
    page = _Page()
    view = SimpleNamespace()
    integration._run(page, view, lambda: "range applied", "summary", "failed")
    assert page.notices == [] and page.console == ["range applied"]
