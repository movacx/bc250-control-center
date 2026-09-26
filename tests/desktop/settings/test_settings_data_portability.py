from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog

import frontends.desktop.pages.settings as settings_module
from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.pages.settings import SettingsPage


class Controller:
    def __init__(self):
        self.calls = []

    def config_paths(self):
        return {}

    def exportar_bundle_perfil(self, destination):
        self.calls.append(("export-profile", destination))
        return destination

    def previsualizar_bundle_perfil(self, source):
        self.calls.append(("preview-profile", source))
        return {
            "config_keys": ("language", "gpu_governor"),
            "profile_sections": ("cpu", "gpu"),
        }

    def importar_bundle_perfil(self, source):
        self.calls.append(("import-profile", source))
        return "/config/backups/profile-before-import.json"

    def exportar_metricas_runtime(self, destination, format_name):
        self.calls.append(("export-metrics", destination, format_name))
        return destination

    def recovery_inventory(self):
        self.calls.append(("recovery-inventory",))
        return {
            "snapshots": [
                {"id": "newest-invalid", "verified": False},
                {"id": "newest-verified", "verified": True},
            ]
        }

    def export_recovery_snapshot(self, snapshot_id, destination):
        self.calls.append(("export-recovery", snapshot_id, destination))
        return {"path": destination, "sha256": "a" * 64}

    def health_check(self):
        return {
            "overall": "healthy",
            "counts": {"healthy": 0, "warning": 0, "error": 0},
            "checks": [],
            "distribution": "Fixture",
            "kernel": "test",
        }


class SettingsService:
    def __init__(self, controller):
        self.controller = controller

    def export_profile_bundle(self, destination):
        return self.controller.exportar_bundle_perfil(destination)

    def preview_profile_bundle(self, source):
        return self.controller.previsualizar_bundle_perfil(source)

    def import_profile_bundle(self, source):
        return self.controller.importar_bundle_perfil(source)

    def export_runtime_metrics(self, destination, format_name):
        return self.controller.exportar_metricas_runtime(destination, format_name)


class ActivityService:
    def __init__(self, controller):
        self.controller = controller

    def clear(self):
        self.controller.calls.append(("clear-history",))
        return True


def _page(qtbot, tmp_path, monkeypatch):
    notices = []

    class Info:
        def __init__(self, title, message, *args, **kwargs):
            notices.append((title, message, kwargs.get("notice", "")))

        def exec(self):
            return 0

    class Confirm:
        def __init__(self, title, message, **kwargs):
            notices.append((title, message, kwargs.get("summary", ())))

        def exec(self):
            return QDialog.DialogCode.Accepted

    def immediate(_self, operation, success, failure, **_kwargs):
        try:
            success(operation())
        except Exception as error:  # pragma: no cover - validates failure wiring
            failure(str(error))

    def toast(_anchor, title, message="", **_kwargs):
        # A finished export is a toast now, not a dialog to close.
        notices.append((title, message, "toast"))

    monkeypatch.setattr(SettingsPage, "_start_task", immediate)
    monkeypatch.setattr(settings_module, "InfoDialog", Info)
    monkeypatch.setattr(settings_module, "show_toast", toast)
    monkeypatch.setattr(settings_module, "ConfirmDialog", Confirm)
    controller = Controller()
    ui_settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(
        controller,
        settings_service=SettingsService(controller),
        activity_service=ActivityService(controller),
        app_settings=ui_settings,
    )
    qtbot.addWidget(page)
    page._ensure_section("reports")
    return page, controller, notices


def test_reports_page_exposes_only_csv_metrics_export(
    qtbot, tmp_path, monkeypatch
):
    page, controller, notices = _page(qtbot, tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(tmp_path / "metrics"), ""),
    )

    page.metrics_csv_button.click()

    assert controller.calls == [
        ("export-metrics", str(tmp_path / "metrics.csv"), "csv"),
    ]
    assert [item[0] for item in notices] == ["Metrics export completed"]
    assert "health" not in page.section_order
    assert not hasattr(page, "profile_export_button")
    assert not hasattr(page, "metrics_jsonl_button")


def test_cancelled_file_dialog_performs_no_operation(qtbot, tmp_path, monkeypatch):
    page, controller, _notices = _page(qtbot, tmp_path, monkeypatch)
    monkeypatch.setattr(
        settings_module.QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: ("", ""),
    )
    monkeypatch.setattr(
        settings_module.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: ("", ""),
    )
    page.metrics_csv_button.click()
    assert controller.calls == []


def test_current_reports_copy_is_translated_in_every_language():
    sources = (
        "Review application activity and export recorded performance data.",
        "Metrics report",
        "Export recorded samples as a spreadsheet-ready CSV file.",
        "Recent activity",
        "Export metrics as CSV",
        "REPORTS",
        "Export metrics as {format}",
        "Metrics file (*.{extension})",
        "Metrics export completed",
        "Metrics export failed",
        "Recorded metrics were saved to {path}.",
        "The CSV contains recorded samples and can be opened in a spreadsheet.",
        "No incomplete export was kept.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language


def test_recovery_export_copy_is_translated_in_every_language():
    sources = (
        "Export latest",
        "Recovery export unavailable",
        "No verified recovery snapshot is available to export.",
        "Create and verify a snapshot before exporting evidence.",
        "Export portable recovery evidence",
        "BC250 recovery evidence (*.zip)",
        "Recovery evidence exported",
        "Verified recovery evidence was saved to {path}. SHA-256: {sha256}",
        "The archive contains no automatic restore executable and did not change the system.",
        "Recovery export failed",
        "No existing file or system setting was changed.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language


def test_repository_portability_facade_uses_transactional_user_files(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    configuration = ConfiguracionLocal()
    configuration.guardar_config_completa({"language": "es"})
    configuration.guardar_perfiles({"cpu": {"safe": True}})
    repository = SistemaRepository.__new__(SistemaRepository)
    repository.configuracion = configuration

    bundle = tmp_path / "portable.json"
    assert repository.exportar_bundle_perfil(bundle) == str(bundle)
    preview = repository.previsualizar_bundle_perfil(bundle)
    assert "language" in preview["config_keys"]
    assert "cpu" in preview["profile_sections"]

    configuration.guardar_config_completa({"language": "de"})
    backup = repository.importar_bundle_perfil(bundle)
    assert configuration.leer_config()["language"] == "es"
    assert "profile-before-import" in backup

    configuration.registrar_metrica_runtime({"gpu_temp": 55})
    metrics = tmp_path / "metrics.csv"
    assert repository.exportar_metricas_runtime(metrics, "csv") == str(metrics)
    assert "gpu_temp" in metrics.read_text(encoding="utf-8")
