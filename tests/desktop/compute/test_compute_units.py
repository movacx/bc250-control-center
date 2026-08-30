import json
import os
import stat
import time
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QPushButton

import frontends.desktop.pages.compute_units as compute_units_module
import bc250cc.infrastructure.cu_repository as cu_repository_module
from bc250cc.infrastructure.cu_repository import CURepository
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, set_language, tr
from frontends.desktop.pages.compute_units import ComputeUnitsPage

FULL_40_CU_DASHBOARD = """
UMR        : /usr/bin/umr
UMR inst   : 1 (auto)
ASIC       : cyan_skillfish.gfx1013
amdgpu     : bc250_cc_write_mode=not exposed, active_cu_number=24
Service    : enabled
Boot sync  : current table saved
| Row     | WGP0 | WGP1 | WGP2 | WGP3 | WGP4 | SPI  | CC         | CUs    |
| SE0.SH0 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 0xffe00000 |  10/10 |
| SE0.SH1 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 0xffe00000 |  10/10 |
| SE1.SH0 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 0xffe00000 |  10/10 |
| SE1.SH1 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 0xffe00000 |  10/10 |
CUs active & routed  : 40/40
"""


@pytest.mark.parametrize("language", ("en", "es", "de", "pl"))
def test_compute_units_compact_layout_contains_wide_table_without_page_overflow(qtbot, language):
    try:
        set_language(language)
        page = ComputeUnitsPage(object())
        qtbot.addWidget(page)
        page.resize(360, 800)
        page.show()
        qtbot.wait(10)

        assert page.scroll.horizontalScrollBar().maximum() == 0
        assert page.topology_scroll.horizontalScrollBar().maximum() > 0
        assert page.content.width() == page.scroll.viewport().width()
    finally:
        set_language("en")


FACTORY_24_CU_DASHBOARD = """
UMR        : /usr/bin/umr
ASIC       : cyan_skillfish.gfx1013
Service    : not installed
| Row     | WGP0 | WGP1 | WGP2 | WGP3 | WGP4 | SPI  | CC         | CUs    |
| SE0.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xffe00000 |   6/10 |
| SE0.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xffe00000 |   6/10 |
| SE1.SH0 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xffe00000 |   6/10 |
| SE1.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xffe00000 |   6/10 |
CUs active & routed  : 24/40
"""

CUSTOM_36_CU_DASHBOARD = FULL_40_CU_DASHBOARD.replace(
    "| SE1.SH1 |  D+  |  D+  |  D+  |  S+  |  S+  | 0x1f | 0xffe00000 |  10/10 |",
    "| SE1.SH1 |  D+  |  D+  |  D+  |  --  |  --  | 0x07 | 0xffe00000 |   6/10 |",
).replace("CUs active & routed  : 40/40", "CUs active & routed  : 36/40")


@pytest.mark.parametrize(
    ("dashboard", "active_cus", "masks", "mode_key"),
    (
        (FULL_40_CU_DASHBOARD, 40, [0x1F] * 4, "full"),
        (FACTORY_24_CU_DASHBOARD, 24, [0x07] * 4, "factory"),
    ),
)
def test_compute_units_parser_accepts_valid_upstream_dashboards(
    dashboard,
    active_cus,
    masks,
    mode_key,
):
    state = CURepository().parsear_dashboard_cu(dashboard)

    assert state["available"] is True
    assert state["parse_error"] == ""
    assert state["active_cus"] == active_cus
    assert state["masks"] == masks
    assert state["mode_key"] == mode_key


def test_compute_units_parser_rejects_duplicate_topology_rows():
    duplicate = FULL_40_CU_DASHBOARD.replace("SE1.SH1", "SE1.SH0")
    state = CURepository().parsear_dashboard_cu(duplicate)

    assert state["available"] is False
    assert "duplicate rows" in state["parse_error"]


def test_compute_units_parser_rejects_total_that_disagrees_with_rows():
    inconsistent = FACTORY_24_CU_DASHBOARD.replace(
        "CUs active & routed  : 24/40",
        "CUs active & routed  : 40/40",
    )

    state = CURepository().parsear_dashboard_cu(inconsistent)

    assert state["available"] is False
    assert "inconsistent" in state["parse_error"]


def test_compute_units_parser_rejects_duplicate_final_totals():
    duplicate = FULL_40_CU_DASHBOARD + "\n  CUs active & routed  : 40/40\n"

    state = CURepository().parsear_dashboard_cu(duplicate)

    assert state["available"] is False
    assert "duplicate" in state["parse_error"]


def _quick_access_runtime_snapshot(raw, *, observed_at=1_000):
    state = CURepository().parsear_dashboard_cu(raw)
    return {
        "schema": 1,
        "producer": "bc250-quick-access-helper",
        "helper_protocol": 9,
        "boot_id": "01234567-89ab-cdef-0123-456789abcdef",
        "observed_at_unix_ms": observed_at,
        "raw_dashboard": raw,
        "cu_masks": list(state["masks"]),
        "cu_driver_masks": list(state["driver_masks"]),
        "cu_tokens": [list(row["tokens"]) for row in state["rows"]],
        "cu_active_cus": state["active_cus"],
        "cu_total_cus": 40,
        "cu_saved_masks": list(state["masks"]),
        "cu_service_installed": True,
        "cu_service_enabled": True,
        "cu_service_active": True,
        "cu_boot_saved": True,
    }


def _runtime_reader(repository, path, *, mtime=100.0):
    repository._quick_access_cu_runtime_metadata = lambda: (path, SimpleNamespace(st_mtime=mtime))
    repository._quick_access_cu_runtime_boot_id = lambda: "01234567-89ab-cdef-0123-456789abcdef"
    repository._opened_quick_access_runtime_file_is_safe = lambda _metadata, _expected: True


def test_quick_access_runtime_snapshot_is_reparsed_and_marked_live(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    snapshot.write_text(json.dumps(_quick_access_runtime_snapshot(FULL_40_CU_DASHBOARD)), encoding="utf-8")
    repository = CURepository()
    _runtime_reader(repository, snapshot)

    result = repository._leer_dashboard_cu_quick_access_runtime()

    assert result is not None
    state, mtime = result
    assert mtime == 100.0
    assert state["source_kind"] == "quick_access"
    assert state["fresh"] is False
    assert state["active_cus"] == 40
    assert state["masks"] == [0x1F] * 4
    assert state["driver_masks"] == [0x07] * 4
    assert state["boot_sync_key"] == "saved"


def test_quick_access_runtime_snapshot_rejects_json_that_disagrees_with_raw_rows(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    payload = _quick_access_runtime_snapshot(FULL_40_CU_DASHBOARD)
    payload["cu_masks"] = [0x07] * 4
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    repository = CURepository()
    _runtime_reader(repository, snapshot)

    assert repository._leer_dashboard_cu_quick_access_runtime() is None


def test_quick_access_runtime_snapshot_rejects_another_boot(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    payload = _quick_access_runtime_snapshot(FULL_40_CU_DASHBOARD)
    payload["boot_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    repository = CURepository()
    _runtime_reader(repository, snapshot)

    assert repository._leer_dashboard_cu_quick_access_runtime() is None


def test_quick_access_runtime_snapshot_rejects_future_observation_time(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    payload = _quick_access_runtime_snapshot(
        CUSTOM_36_CU_DASHBOARD,
        observed_at=time.time_ns() // 1_000_000 + 120_000,
    )
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    repository = CURepository()
    _runtime_reader(repository, snapshot)

    assert repository._leer_dashboard_cu_quick_access_runtime() is None


def test_quick_access_runtime_requires_exact_root_owned_permissions(tmp_path):
    repository = CURepository()
    secure_dir = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
    secure_file = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0)
    writable_file = SimpleNamespace(st_mode=stat.S_IFREG | 0o664, st_uid=0)

    assert repository._root_owned_mode(tmp_path, secure_dir, directory=True) is True
    assert repository._root_owned_mode(tmp_path / "state", secure_file) is True
    assert repository._root_owned_mode(tmp_path / "state", writable_file) is False


def test_newer_quick_access_snapshot_wins_over_desktop_cache(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    snapshot.write_text(json.dumps(_quick_access_runtime_snapshot(CUSTOM_36_CU_DASHBOARD)), encoding="utf-8")
    cache = tmp_path / "cu_dashboard_live.txt"
    cache.write_text(FACTORY_24_CU_DASHBOARD, encoding="utf-8")
    repository = CURepository()
    repository._dashboard_cu_cache_path = lambda: cache
    _runtime_reader(repository, snapshot, mtime=200.0)
    repository._reconcile_cached_service_state = lambda value: value
    repository.estado_herramientas_bc250 = lambda: {"cu_privileged_backend_ready": True}
    # The local cache mtime is deliberately older than the live QAM reading.
    os.utime(cache, (100.0, 100.0))

    state = repository.obtener_estado_cu_cache()

    assert state["source_kind"] == "quick_access"
    assert state["active_cus"] == 36
    assert state["amdgpu_active_cus"] == "24"


def test_newer_desktop_cache_wins_over_older_quick_access_snapshot(tmp_path):
    snapshot = tmp_path / "cu-live-state.json"
    snapshot.write_text(json.dumps(_quick_access_runtime_snapshot(FULL_40_CU_DASHBOARD)), encoding="utf-8")
    cache = tmp_path / "cu_dashboard_live.txt"
    cache.write_text(FACTORY_24_CU_DASHBOARD, encoding="utf-8")
    repository = CURepository()
    repository._dashboard_cu_cache_path = lambda: cache
    _runtime_reader(repository, snapshot, mtime=100.0)
    repository._reconcile_cached_service_state = lambda value: value
    repository.estado_herramientas_bc250 = lambda: {"cu_privileged_backend_ready": True}
    os.utime(cache, (200.0, 200.0))

    state = repository.obtener_estado_cu_cache()

    assert state["source_kind"] == "authorized_cache"
    assert state["active_cus"] == 24


def test_compute_units_fallback_never_enables_hardware_actions(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)

    page._apply_state(CURepository()._estado_cu_base())

    assert page._has_authorized_state() is False
    assert page.apply_live_button.isEnabled() is False
    assert page.save_boot_button.isEnabled() is False
    assert page.apply_saved_button.isEnabled() is False


def test_saved_table_survives_missing_service_reconciliation(monkeypatch):
    repository = CURepository()
    monkeypatch.setattr(
        cu_repository_module,
        "detect_init_manager",
        lambda: SimpleNamespace(
            kind="systemd",
            persistence_supported=True,
            persistence_detail="systemd",
            display_name="systemd",
        ),
    )
    repository._ejecutar = lambda *args, **kwargs: (1, "not-found", "")
    state = {"boot_sync": "Current table saved", "boot_sync_key": "saved"}

    result = repository._reconcile_cached_service_state(state)

    assert result["boot_sync_key"] == "saved"
    assert result["service_installed"] is False
    assert result["service_enabled"] is False


def test_compute_units_exposes_live_refresh_and_passive_updates_preserve_wgp_edits(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    initial = CURepository().parsear_dashboard_cu(FACTORY_24_CU_DASHBOARD)
    initial["privileged_backend_ready"] = True
    page._apply_state(initial)
    page.topology_table.set_masks([0x0F, 0x07, 0x07, 0x07])

    next_state = CURepository().parsear_dashboard_cu(FULL_40_CU_DASHBOARD)
    next_state.update(source_kind="quick_access", fresh=True, privileged_backend_ready=True)
    page._apply_state(next_state, preserve_edits=True)

    assert page.live_refresh_button.text() == "Refresh live topology"
    assert page.current_state["active_cus"] == 40
    assert page.topology_table.current_masks() == [0x0F, 0x07, 0x07, 0x07]
    assert not hasattr(page, "status_card")
    assert any(button.text() == "Raw status" for button in page.activity_card.findChildren(QPushButton))


def test_compute_units_validated_state_keeps_writes_locked_without_trusted_backend(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    state = CURepository().parsear_dashboard_cu(FULL_40_CU_DASHBOARD)

    page._apply_state(state)

    assert page._has_authorized_state() is True
    assert page.save_boot_button.isEnabled() is False
    assert page.apply_live_button.isEnabled() is False

    page._selection_changed([0x1F, 0x1F, 0x1F, 0x07])

    assert page.apply_live_button.isEnabled() is False


def test_compute_units_trusted_backend_enables_review_flow(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    state = CURepository().parsear_dashboard_cu(FULL_40_CU_DASHBOARD)
    state["privileged_backend_ready"] = True

    page._apply_state(state)

    assert page._has_authorized_state() is True
    assert page.save_boot_button.isEnabled() is True


def test_installed_service_keeps_apply_now_available_for_a_changed_table(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    state = CURepository().parsear_dashboard_cu(FULL_40_CU_DASHBOARD)
    state["privileged_backend_ready"] = True

    page._apply_state(state)
    page._selection_changed([0x1F, 0x1F, 0x1F, 0x07])

    assert state["service_installed"] is True
    assert page.apply_live_button.isEnabled() is True
    assert page.discard_button.isEnabled() is True


def test_authoritative_cu_result_survives_page_deactivation_and_reactivation(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    forty = CURepository().parsear_dashboard_cu(FULL_40_CU_DASHBOARD)
    thirty_six = dict(forty)
    thirty_six.update(
        masks=[0x1F, 0x1F, 0x1F, 0x07],
        active_cus=36,
        routed_wgps=18,
        mode="Custom 36 CUs",
    )
    page._apply_state(forty)
    page._apply_state(thirty_six)
    page._refresher.adopt_authoritative(thirty_six, already_rendered=True)

    page._refresher.set_active(False)
    page._refresher.set_active(True)

    assert page._refresher.replay_latest() is False
    assert page.current_state["active_cus"] == 36
    assert page.topology_table.current_masks() == [0x1F, 0x1F, 0x1F, 0x07]


def test_unsaved_table_allows_save_but_blocks_service_and_apply_saved(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    state = CURepository().parsear_dashboard_cu(FACTORY_24_CU_DASHBOARD)
    state["privileged_backend_ready"] = True

    page._apply_state(state)

    assert state["boot_sync_key"] == "not_saved"
    assert page.save_boot_button.isEnabled() is True
    assert page.install_service_button.isEnabled() is False
    assert page.apply_saved_button.isEnabled() is False


def test_compute_units_clean_install_loads_cache_without_running_external_status(qtbot):
    controller = type(
        "Controller",
        (),
        {"estado_herramientas_bc250": lambda self: {"cu_manager_exists": True}},
    )()
    page = ComputeUnitsPage(controller)
    qtbot.addWidget(page)
    passive_refreshes = []
    authorized_refreshes = []
    page.refresh = lambda: passive_refreshes.append(True)
    page.refresh_authorized = lambda: authorized_refreshes.append(True)

    def run_now(_key, operation, success, _failure, *args):
        success(operation())
        return True

    page._background.start = run_now
    page._auto_sync_attempted = False
    page._auto_initialize_live_state()

    assert passive_refreshes == [True]
    assert authorized_refreshes == []
    assert page._auto_sync_attempted is True


def test_compute_units_existing_verified_state_never_reauthorizes_on_entry(qtbot):
    controller = type(
        "Controller",
        (),
        {"estado_herramientas_bc250": lambda self: {"cu_manager_exists": True}},
    )()
    page = ComputeUnitsPage(controller)
    qtbot.addWidget(page)
    page.current_state = CURepository().parsear_dashboard_cu(FACTORY_24_CU_DASHBOARD)
    authorized_refreshes = []
    page.refresh_authorized = lambda: authorized_refreshes.append(True)

    page._auto_initialize_live_state()

    assert authorized_refreshes == []


def test_cancelled_cu_authorization_is_not_reported_as_a_hardware_failure(qtbot):
    controller = type(
        "Controller",
        (),
        {"obtener_estado_cu": lambda self: (_ for _ in ()).throw(RuntimeError("CU_AUTHORIZATION_CANCELLED"))},
    )()
    page = ComputeUnitsPage(controller)
    qtbot.addWidget(page)
    page.current_state["privileged_backend_ready"] = True
    errors = []
    page._show_error = lambda *args: errors.append(args)

    page.refresh_authorized()
    qtbot.waitUntil(lambda: page._worker is None, timeout=2000)

    assert errors == []
    assert page.current_state.get("fresh") is not True
    assert any(action[0] == "Live refresh canceled" for action in page._session_actions)


def test_unlock_sync_explains_when_protected_backend_is_missing(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page.current_state.update(
        privileged_backend_ready=False,
        privileged_backend_reason="The staged CU backend is missing. Run Prepare dependencies.",
    )
    errors = []
    passive_refreshes = []
    page._show_error = lambda *args: errors.append(args)
    page.refresh = lambda: passive_refreshes.append(True)

    page.refresh_authorized()

    assert passive_refreshes == []
    assert errors == [
        (
            "Compute Units operation failed",
            "The staged CU backend is missing. Run Prepare dependencies.",
        )
    ]


def test_prepare_cu_tools_requests_only_manager_and_its_dependencies(qtbot, monkeypatch):
    calls = []
    controller = type(
        "Controller",
        (),
        {
            "instalar_dependencias_bc250": lambda self, **kwargs: calls.append(kwargs)
            or True,
        },
    )()
    page = ComputeUnitsPage(controller)
    qtbot.addWidget(page)

    class AcceptedDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return compute_units_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(compute_units_module, "ConfirmDialog", AcceptedDialog)

    def run_immediately(_label, operation, **_kwargs):
        operation()

    page._run_task = run_immediately
    page.prepare_tools()

    assert calls == [{"components": {"cu_manager"}}]


@pytest.mark.parametrize(
    "message",
    (
        "Error executing command as another user: Request dismissed",
        "Authentication cancelled",
        "Not authorized",
        "GDBus.Error:org.freedesktop.PolicyKit1.Error.Cancelled",
    ),
)
def test_cu_repository_recognizes_localized_polkit_cancellation(message):
    assert CURepository._autorizacion_cancelada(message) is True


def test_canceled_authorization_copy_is_localized_in_every_language():
    sources = (
        "Live refresh canceled",
        "Administrator authorization was canceled. The last verified CU state remains unchanged.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language


def test_dependency_completion_reprobes_tools_and_runs_authorized_status(qtbot, tmp_path):
    controller = type(
        "Controller",
        (),
        {
            "estado_herramientas_bc250": lambda self: {
                "cu_privileged_backend_ready": True,
                "cu_privileged_backend_reason": "Verified protected backend",
            },
        },
    )()
    page = ComputeUnitsPage(controller)
    qtbot.addWidget(page)
    status = tmp_path / "terminal.status"
    status.write_text("0\n", encoding="utf-8")
    refreshes = []
    authorized_refreshes = []
    page.refresh = lambda: refreshes.append(True)
    page.refresh_authorized = lambda: authorized_refreshes.append(True)

    page._watch_dependency_preparation(SimpleNamespace(status_file=str(status)))
    qtbot.waitUntil(lambda: bool(authorized_refreshes), timeout=2000)

    assert refreshes == []
    assert authorized_refreshes == [True]
    assert page.current_state["privileged_backend_ready"] is True


def test_factory_repair_removes_stale_service_before_restoring_stock():
    calls = []

    class Repository(CURepository):
        def _ejecutar_cu_accion_pkexec(self, args):
            calls.append(tuple(args))
            if "stock-dispatch" in args:
                return FACTORY_24_CU_DASHBOARD
            return "service removed"

    state = Repository().ejecutar_accion_cu_grafica("factory_repair")

    assert calls == [
        ("--yes", "uninstall-service"),
        ("--yes", "stock-dispatch"),
    ]
    assert state["available"] is True
    assert state["active_cus"] == 24


def test_steamos_authorized_status_refresh_replaces_the_passive_cache():
    repository = CURepository()
    cached = []
    repository.estado_herramientas_bc250 = lambda: {
        "cu_privileged_backend_ready": True,
    }
    repository._usar_steamos_cu_helper = lambda: True
    repository._ejecutar_steamos_game_helper = (
        lambda *_args, **_kwargs: FACTORY_24_CU_DASHBOARD
    )
    repository._guardar_dashboard_cu_cache = cached.append

    result = repository._ejecutar_cu_accion_pkexec(["status"])

    assert result == FACTORY_24_CU_DASHBOARD
    assert cached == [FACTORY_24_CU_DASHBOARD]


def test_steamos_incomplete_status_never_replaces_the_last_verified_cache():
    repository = CURepository()
    cached = []
    repository.estado_herramientas_bc250 = lambda: {
        "cu_privileged_backend_ready": True,
    }
    repository._usar_steamos_cu_helper = lambda: True
    repository._ejecutar_steamos_game_helper = lambda *_args, **_kwargs: "Service: enabled"
    repository._guardar_dashboard_cu_cache = cached.append

    assert repository._ejecutar_cu_accion_pkexec(["status"]) == "Service: enabled"
    assert cached == []


@pytest.mark.parametrize(
    ("action", "expected_service", "expected_boot"),
    (
        ("save_boot", "Not installed", "saved"),
        ("install_service", "enabled", "saved"),
        ("remove_service", "Not installed", "not_saved"),
    ),
)
def test_cu_persistence_metadata_survives_cache_reload(
    tmp_path, action, expected_service, expected_boot
):
    repository = CURepository()
    cache = tmp_path / "cu_dashboard_live.txt"
    repository._dashboard_cu_cache_path = lambda: cache
    repository._guardar_dashboard_cu_cache(FACTORY_24_CU_DASHBOARD)

    repository._actualizar_persistencia_dashboard_cu_cache(action)
    state = repository.parsear_dashboard_cu(cache.read_text(), source="authorized cache")

    assert state["active_cus"] == 24
    assert state["service"] == expected_service
    assert state["boot_sync_key"] == expected_boot
    assert cache.stat().st_mode & 0o777 == 0o600


def test_dutch_missing_manager_error_offers_copyable_recovery_command(qtbot, monkeypatch):
    captured = {}

    class Dialog:
        def __init__(self, title, message, **kwargs):
            captured.update(title=title, message=message, **kwargs)

        def exec(self):
            return 0

    monkeypatch.setattr(compute_units_module, "InfoDialog", Dialog)
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page._show_error(
        "Compute Units operation failed",
        "env: '/usr/local/bin/bc250-cu-live-manager': Bestand of map bestaat niet",
    )

    assert captured["copy_text"] == (
        "sudo /bin/sh -c 'if [ -x /var/lib/bc250-control-center/bc250-cu-live-manager ]; then "
        "exec /var/lib/bc250-control-center/bc250-cu-live-manager --yes uninstall-service; "
        "else exec /usr/libexec/bc250-control-center/bc250-cu-live-manager --yes uninstall-service; fi'"
    )
    assert "Bestand of map bestaat niet" not in captured["message"]
    assert "stopped before changing the hardware" in captured["message"]
    assert "Restore factory" in captured["notice"]
