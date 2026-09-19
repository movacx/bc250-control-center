from PyQt6.QtWidgets import QDialog

import frontends.desktop.pages.dashboard as dashboard_module
from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.core.state import DashboardState
from frontends.desktop.i18n import set_language, tr
from frontends.desktop.pages.dashboard import SUPPORT_URL, DashboardPage
from frontends.desktop.pages.fans import FansPage
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


class _ActionTarget:
    def __init__(self):
        self.calls = []
        self.current_state = {}

    def prepare_dependencies(self, **options):
        self.calls.append(("prepare_dependencies", options))

    def prepare_pwm_driver(self, **options):
        self.calls.append(("prepare_pwm_driver", options))

    def execute_dependency_action(self, **options):
        self.calls.append(("execute_dependency_action", options))


class _AutomaticPreparationDialog:
    action = "prepare"
    governor = "auto"

    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


class _OberonPreparationDialog(_AutomaticPreparationDialog):
    governor = "oberon-governor"


class _DiagnosticsPreparationDialog(_AutomaticPreparationDialog):
    action = "steamos_diagnostics"
    governor = "cyan-skillfish-governor-smu"


class _CompatibilityPreparationDialog(_AutomaticPreparationDialog):
    action = "steamos_compat"
    governor = "cyan-skillfish-governor-smu"


class _RemovalPreparationDialog(_AutomaticPreparationDialog):
    action = "remove"
    governor = "oberon-governor"


class _QuickAccessPreparationDialog(_AutomaticPreparationDialog):
    action = "quick_access_install_decky"
    governor = ""


class _MitigationsPreparationDialog(_AutomaticPreparationDialog):
    action = "bazzite_mitigations_disable"
    governor = ""


def _window_stub():
    gpu = _ActionTarget()
    fans = _ActionTarget()
    navigation = []
    settings = []
    window = type(
        "DashboardWindowStub",
        (),
        {
            "gpu_page": gpu,
            "fans_page": fans,
            "_state_cache": type(
                "StateCacheStub",
                (),
                {"tools": lambda self: {"incompatible_gpu_governors": [{"identifier": "oberon"}]}},
            )(),
            "navigate": lambda self, target: navigation.append(target),
            "_open_settings_dialog": lambda self, section: settings.append(section),
        },
    )()
    return window, gpu, fans, navigation, settings


def test_dashboard_dependency_preparation_runs_in_place():
    window, gpu, fans, navigation, _settings = _window_stub()

    ControlCenterWindow._dashboard_action(window, "prepare_dependencies")

    assert gpu.calls == [("prepare_dependencies", {"dialog_parent": window})]
    assert gpu.current_state["tools"]["incompatible_gpu_governors"][0]["identifier"] == "oberon"
    assert fans.calls == []
    assert navigation == []


def test_dashboard_pwm_preparation_runs_in_place():
    window, gpu, fans, navigation, _settings = _window_stub()

    ControlCenterWindow._dashboard_action(window, "prepare_pwm")

    assert fans.calls == [("prepare_pwm_driver", {"dialog_parent": window})]
    assert gpu.calls == []
    assert navigation == []


def test_dashboard_selected_components_use_the_shared_dependency_safety_route():
    window, gpu, _fans, navigation, _settings = _window_stub()

    ControlCenterWindow._dashboard_dependency_action(
        window,
        {
            "action": "prepare",
            "governor": "auto",
            "selected_components": {"runtime", "umr", "cu_manager"},
        },
    )

    assert gpu.calls == [
        (
            "execute_dependency_action",
            {
                "action": "prepare",
                "preference": "auto",
                "selected_components": {"runtime", "umr", "cu_manager"},
                "dialog_parent": window,
            },
        )
    ]
    assert navigation == []


def test_other_dashboard_actions_keep_their_existing_routes():
    window, _gpu, _fans, navigation, settings = _window_stub()

    ControlCenterWindow._dashboard_action(window, "apply_profile")
    ControlCenterWindow._dashboard_action(window, "open_logs")

    assert navigation == ["cpu"]
    assert settings == ["reports"]


def test_dashboard_cpu_frequency_uses_ghz():
    assert DashboardPage._format_ghz(3487) == "3.49 GHz"


def test_dashboard_keeps_cpu_and_gpu_voltage_channels_separate():
    class Cache:
        def performance(self):
            return {
                "cpu_voltage": 1206,
                "gpu_voltage": 799,
                "memory_frequency_mhz": 450,
                "gtt_used": 249_376_768,
                "gtt_total": 5_587_288_064,
                "dpm_force_level": "auto",
                "dpm_state": "performance",
            }

        def gpu(self):
            return {
                "apu_telemetry": {
                    "status": "invalid",
                    "layout_mismatch_suspected": True,
                }
            }

        def fans(self):
            return {}

        def cu_cache(self):
            return {}

        def cpu_boot_tuning(self):
            return {}

        def events(self, _limit):
            return []

        def pump_fan_fallback(self):
            return 0, "Not detected"

        def tools(self):
            return {}

    state = DashboardState.from_controller(object(), cache=Cache())

    assert state.cpu_voltage_mv == 1206
    assert state.gpu_voltage_mv == 799
    assert state.gpu_memory_frequency_mhz == 450
    assert state.gtt_summary == "238 MB / 5.2 GB"
    assert state.dpm_summary == "auto"
    assert state.gpu_telemetry_invalid is True
    assert state.gpu_metrics_layout_mismatch is True


def test_dashboard_does_not_present_the_default_install_target_as_detected():
    class Cache:
        def performance(self):
            return {}

        def gpu(self):
            return {}

        def fans(self):
            return {}

        def cu_cache(self):
            return {}

        def cpu_boot_tuning(self):
            return {}

        def events(self, _limit):
            return []

        def pump_fan_fallback(self):
            return 0, "Not detected"

        def tools(self):
            return {
                # Cyan remains the recommended preparation target on a clean
                # system, but neither supported governor is installed.
                "governor_backend": "cyan-skillfish-governor-smu",
                "governor_detected_backend": "",
                "supported_gpu_governors": {
                    "cyan-skillfish-governor-smu": {"detected": False},
                    "oberon-governor": {"detected": False},
                },
            }

    state = DashboardState.from_controller(object(), cache=Cache())

    assert state.governor_backend == ""
    assert state.preparation_tools["governor_backend"] == "cyan-skillfish-governor-smu"


def test_dashboard_contact_and_support_buttons_have_icons(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)

    assert page.contact_button.icon().isNull() is False
    assert page.support_button.icon().isNull() is False
    assert SUPPORT_URL == "https://ko-fi.com/movacx"


def test_dashboard_preparation_sidebar_emits_real_existing_workflows(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    actions = []
    dependency_actions = []
    page.action_requested.connect(actions.append)
    page.dependency_action_requested.connect(dependency_actions.append)

    page.readiness.prepare_button.click()

    assert actions == []
    assert dependency_actions == [
        {
            "action": "prepare",
            "governor": "auto",
            "selected_components": {
                "runtime",
                "governor",
                "cpu_oc",
                "core_unlock",
                "umr",
                "cu_manager",
                "fan_pwm",
            },
        }
    ]


def test_dashboard_compatibility_governors_keep_install_and_uninstall_actions(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    blocked = page.readiness.compatibility_filter.blockSignals(True)
    page.readiness.compatibility_filter.setCurrentIndex(
        page.readiness.compatibility_filter.findData("detected")
    )
    page.readiness.compatibility_filter.blockSignals(blocked)
    page.apply_state(
        DashboardState(
            governor_backend="oberon-governor",
            preparation_tools={
                "governor_backend": "oberon-governor",
                "supported_gpu_governors": {
                    "cyan-skillfish-governor-smu": {"detected": False},
                    "oberon-governor": {"detected": True},
                },
            },
        )
    )
    requests = []
    page.dependency_action_requested.connect(requests.append)

    cyan = page.readiness.cyan_card
    oberon = page.readiness.oberon_card
    assert cyan.primary_button is not None
    assert cyan.secondary_button is not None
    assert oberon.primary_button is not None
    assert oberon.secondary_button is not None
    assert cyan.primary_button.text() == tr("Install / update")
    assert cyan.secondary_button.text() == tr("Uninstall")
    assert cyan.secondary_button.isEnabled() is False
    assert oberon.secondary_button.isEnabled() is True

    oberon.secondary_button.click()

    assert requests[-1]["action"] == "remove"
    assert requests[-1]["governor"] == "oberon-governor"


def test_dashboard_driver_sidebar_emits_native_support_routes(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    requested = []
    page.driver_support_requested.connect(requested.append)

    page.readiness.network_driver_card.action_requested.emit({})
    page.readiness.printing_driver_card.action_requested.emit({})

    assert requested == ["connectivity", "printing"]


def test_dashboard_preparation_keeps_the_bazzite_swap_and_ttm_controls(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "bazzite",
                "memory_runtime": {
                    "ttm_limit_bytes": 8 * 1024**3,
                    "physical_ram_bytes": 9_884_384 * 1024,
                },
            }
        )
    )
    requests = []
    page.dependency_action_requested.connect(requests.append)

    assert page.readiness.memory_policy_combo.isEnabled()
    assert page.readiness.ttm_limit_combo.currentData() == 8
    assert [
        page.readiness.ttm_limit_combo.itemData(index)
        for index in range(page.readiness.ttm_limit_combo.count())
    ] == [0, -1, 8]
    page.readiness.memory_ttm_apply_button.click()

    assert requests[-1] == {
        "action": "memory_ttm",
        "governor": "",
        "selected_components": {
            "runtime",
            "governor",
            "cpu_oc",
            "core_unlock",
            "umr",
            "cu_manager",
            "fan_pwm",
        },
        "memory_policy": "preserve",
        "memory_ttm_gib": 8,
    }


def test_dashboard_stages_and_restores_bazzite_cpu_mitigations(qtbot):
    set_language("en")
    page = DashboardPage(object())
    qtbot.addWidget(page)
    requests = []
    page.dependency_action_requested.connect(requests.append)

    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "bazzite",
                "bazzite_mitigations": {
                    "available": True,
                    "active": False,
                    "configured": False,
                    "managed": False,
                    "reboot_required": False,
                },
            }
        )
    )

    assert page.readiness.mitigations_status.text() == "Enabled"
    assert not page.readiness.mitigations_panel.isHidden()
    components_layout = page.readiness.mitigations_panel.parentWidget().layout()
    assert components_layout.indexOf(page.readiness.mitigations_panel) < (
        components_layout.indexOf(page.readiness.components_host)
    )
    assert page.readiness.memory_controls.indexOf(
        page.readiness.mitigations_apply_button
    ) == -1
    assert page.readiness.mitigations_apply_button.text() == "Disable mitigations"
    assert page.readiness.mitigations_apply_button.isEnabled()
    page.readiness.mitigations_apply_button.click()
    assert requests[-1]["action"] == "bazzite_mitigations_disable"

    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "bazzite",
                "bazzite_mitigations": {
                    "available": True,
                    "active": False,
                    "configured": True,
                    "managed": True,
                    "reboot_required": True,
                },
            }
        )
    )

    assert page.readiness.mitigations_status.text() == "Reboot required"
    assert page.readiness.mitigations_apply_button.text() == "Restore mitigations"
    page.readiness.mitigations_apply_button.click()
    assert requests[-1]["action"] == "bazzite_mitigations_restore"


def test_dashboard_preserves_externally_configured_mitigations_off(qtbot):
    set_language("en")
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "bazzite",
                "bazzite_mitigations": {
                    "available": True,
                    "active": True,
                    "configured": True,
                    "managed": False,
                    "reboot_required": False,
                },
            }
        )
    )

    assert page.readiness.mitigations_status.text() == "Disabled"
    assert page.readiness.mitigations_apply_button.text() == "Managed externally"
    assert not page.readiness.mitigations_apply_button.isEnabled()
    assert "configured outside" in page.readiness.mitigations_apply_button.toolTip()


def test_dashboard_hides_cpu_mitigations_outside_bazzite(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "cachyos",
                "os_label": "CachyOS",
            }
        )
    )

    assert page.readiness.mitigations_panel.isHidden()


def test_dashboard_can_preview_bazzite_mitigations_inertly_on_cachyos(
    qtbot, monkeypatch
):
    monkeypatch.setenv("BC250_BAZZITE_UI_PREVIEW", "1")
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            preparation_tools={
                "os_family": "cachyos",
                "os_label": "CachyOS",
            }
        )
    )

    assert not page.readiness.mitigations_panel.isHidden()
    assert page.readiness.mitigations_status.isHidden()
    # The "Bazzite" pill that used to sit beside the button is gone: the panel
    # is only shown on a host that can act, so the badge repeated itself.
    assert not hasattr(page.readiness, "mitigations_scope")
    assert not page.readiness.mitigations_apply_button.isEnabled()


def test_dashboard_preparation_sidebar_reflects_each_readiness_probe(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    page.apply_state(
        DashboardState(
            dependencies_ready=True,
            governor_tool_ready=False,
            cpu_tools_ready=True,
            core_unlock_ready=False,
            umr_ready=True,
            cu_manager_ready=True,
            nct_ready=False,
        )
    )

    assert [row.property("installed") for row in page.readiness.rows] == [
        True,
        False,
        True,
        False,
        True,
        True,
        False,
    ]
    assert page.readiness.status._tone == "orange"


def test_dashboard_preparation_sidebar_preserves_umr_cu_dependency(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    umr = page.readiness.component_cards["umr"].checkbox
    manager = page.readiness.component_cards["cu_manager"].checkbox

    umr.setChecked(False)
    assert manager.isChecked() is False

    manager.setChecked(True)
    assert umr.isChecked() is True


def test_dashboard_preparation_tabs_are_real_stacked_sections(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)

    for index, button in enumerate(page.readiness.tab_buttons):
        button.click()
        assert page.readiness.stack.currentIndex() == index
        assert [item.isChecked() for item in page.readiness.tab_buttons] == [
            position == index for position in range(4)
        ]


def test_dashboard_support_button_opens_exact_kofi_page(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(
        dashboard_module,
        "open_external_url",
        lambda url: (opened.append(url) or True, ""),
    )
    page = DashboardPage(object())
    qtbot.addWidget(page)

    page.support_button.click()

    assert opened == ["https://ko-fi.com/movacx"]


def test_dashboard_refresh_localizes_dynamic_status_values(qtbot):
    try:
        set_language("es")
        page = DashboardPage(object())
        qtbot.addWidget(page)
        page.apply_state(DashboardState(
            gpu_state_available=True,
            governor_running=True,
            cu_state_available=True,
            active_cus=36,
            cu_mode="custom",
            fan_state_available=True,
            fan_mode="read only",
        ))

        assert page.gpu_card.status.text() == tr("running")
        assert page.gpu_card.details["cu"].detail.text() == tr("custom")
        assert page.fan_card.status.text() == tr("read only")
    finally:
        set_language("en")


def test_dashboard_never_marks_partial_bc250_topology_as_full(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)

    page.apply_state(DashboardState(cu_state_available=True, active_cus=36, total_cus=36))

    # 36 of 36 is a partial board reporting itself as complete; the readout
    # states both numbers instead of a reassuring badge.
    assert page.gpu_card.details["cu"].value.text() == "36 / 36"


class _AcceptedDialog:
    def __init__(self, *args, **kwargs):
        self.parent = kwargs.get("parent")

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_pwm_page_workflow_calls_the_controller_terminal_launcher(monkeypatch):
    monkeypatch.setattr("frontends.desktop.pages.fans.ConfirmDialog", _AcceptedDialog)
    calls = []
    parent = object()
    controller = type(
        "ControllerStub",
        (),
        {"preparar_nct6687_control_pwm": lambda self: calls.append("controller") or "terminal"},
    )()

    def run_action(_self, operation, on_success, error_title, **options):
        calls.append((error_title, options))
        on_success(operation())

    page = type(
        "FansPageStub",
        (),
        {
            "controller": controller,
            "_run_driver_action": run_action,
            "_record_event": lambda *args, **kwargs: None,
            "_show_info": lambda *args, **kwargs: None,
        },
    )()

    FansPage.prepare_pwm_driver(page, dialog_parent=parent)

    assert "controller" in calls
    assert calls[0] == ("PWM preparation failed", {"error_parent": parent})


def test_dependency_page_workflow_calls_the_controller_terminal_launcher(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _AutomaticPreparationDialog,
    )
    calls = []
    parent = object()
    controller = type(
        "ControllerStub",
        (),
        {
            "save_local_config": lambda self, payload: calls.append(("config", payload)),
            "instalar_dependencias_bc250": lambda self, *args: calls.append(
                ("controller", args)
            )
            or "terminal"
        },
    )()
    last_operation = type(
        "LastOperationStub",
        (),
        {"set_values": lambda self, *args: calls.append(("status", args))},
    )()

    def run_action(_self, operation, on_success, error_title, **options):
        calls.append((error_title, options))
        on_success(operation())

    page = type(
        "GpuPageStub",
        (),
        {
            "controller": controller,
            "settings_service": controller,
            "current_state": {"tools": {}},
            "last_operation_line": last_operation,
            "_append_console": lambda self, message: calls.append(("console", message)),
            "_run_backend_action": run_action,
        },
    )()

    GpuGovernorPage.prepare_dependencies(page, dialog_parent=parent)

    assert ("config", {"gpu_governor": "auto"}) in calls
    assert (
        "controller",
        (
            False,
            False,
            "auto",
            True,
            {"runtime", "governor", "cpu_oc", "core_unlock", "umr", "cu_manager", "fan_pwm"},
        ),
    ) in calls
    action_call = next(call for call in calls if call[0] == "Could not prepare dependencies")
    assert action_call[1]["error_parent"] is parent
    assert action_call[1]["controls"] == ()


def test_dependency_workflow_with_a_conflict_uses_the_selected_backend_without_crashing(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _OberonPreparationDialog,
    )
    monkeypatch.setattr("frontends.desktop.pages.gpu_governor.ConfirmDialog", _AcceptedDialog)
    calls = []
    controller = type(
        "ControllerStub",
        (),
        {
            "save_local_config": lambda self, payload: calls.append(("config", payload)),
            "instalar_governor": lambda self, *args: calls.append(args)
            or "terminal"
        },
    )()
    page = type(
        "GpuPageStub",
        (),
        {
            "controller": controller,
            "settings_service": controller,
            "current_state": {
                "governor_backend": "oberon-governor",
                "tools": {
                    "governor_backend": "oberon-governor",
                    "supported_gpu_governors": {
                        "cyan-skillfish-governor-smu": {
                            "identifier": "cyan-skillfish-governor-smu",
                            "active": True,
                            "enabled": True,
                        },
                        "oberon-governor": {
                            "identifier": "oberon-governor",
                            "active": False,
                            "enabled": False,
                        },
                    },
                    "incompatible_gpu_governors": [
                        {"identifier": "cyan-skillfish-governor-smu"}
                    ],
                },
            },
            "last_operation_line": type(
                "LastOperationStub", (), {"set_values": lambda self, *args: None}
            )(),
            "_append_console": lambda self, message: None,
            "_run_backend_action": lambda self, operation, on_success, *args, **kwargs: (
                on_success(operation()) or True
            ),
        },
    )()

    GpuGovernorPage.prepare_dependencies(page)

    assert calls == [
        ("config", {"gpu_governor": "oberon-governor"}),
        (True, True, "oberon-governor"),
    ]


def _dependency_route_page(calls, **controller_actions):
    controller_values = {
        "save_local_config": lambda _self, payload: calls.append(("config", payload)),
        **controller_actions,
    }
    controller = type("ControllerStub", (), controller_values)()
    status = type(
        "LastOperationStub",
        (),
        {"set_values": lambda _self, *values: calls.append(("status", values))},
    )()

    def run_action(_self, operation, on_success, error_title, **options):
        calls.append(("dispatch", error_title, options))
        on_success(operation())

    return type(
        "GpuPageStub",
        (),
        {
            "controller": controller,
            "settings_service": controller,
            "current_state": {"tools": {}},
            "last_operation_line": status,
            "_append_console": lambda _self, message: calls.append(("console", message)),
            "_run_backend_action": run_action,
        },
    )()


def test_dependency_diagnostics_route_dispatches_only_the_read_only_workflow(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _DiagnosticsPreparationDialog,
    )
    calls = []
    page = _dependency_route_page(
        calls,
        diagnostico_steamos=lambda _self: calls.append("diagnostics") or "terminal",
    )

    GpuGovernorPage.prepare_dependencies(page)

    assert "diagnostics" in calls
    assert not any(call[0] == "config" for call in calls if isinstance(call, tuple))
    dispatch = next(call for call in calls if isinstance(call, tuple) and call[0] == "dispatch")
    assert dispatch[1] == "Could not open SteamOS diagnostics"


def test_dependency_compatibility_route_skips_extra_confirmation_when_kernel_is_ready(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _CompatibilityPreparationDialog,
    )
    calls = []
    page = _dependency_route_page(
        calls,
        preparar_compatibilidad_steamos=lambda _self: calls.append("compatibility") or "terminal",
    )
    page.current_state["tools"] = {
        "gfx1013_compute": {"steamos_kernel_ready": True, "kernel": "test-kernel"}
    }

    GpuGovernorPage.prepare_dependencies(page)

    assert "compatibility" in calls
    dispatch = next(call for call in calls if isinstance(call, tuple) and call[0] == "dispatch")
    assert dispatch[1] == "Could not prepare SteamOS compatibility"


def test_dependency_quick_access_route_never_uses_generic_preparation(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _QuickAccessPreparationDialog,
    )
    monkeypatch.setattr("frontends.desktop.pages.gpu_governor.ConfirmDialog", _AcceptedDialog)
    calls = []
    page = _dependency_route_page(
        calls,
        preparar_quick_access_steamos=lambda _self, **kwargs: calls.append(
            ("quick-access", kwargs)
        ) or "terminal",
    )
    page._prepare_steamos_quick_access = lambda **kwargs: (  # noqa: SLF001
        GpuGovernorPage._prepare_steamos_quick_access(page, **kwargs)
    )

    GpuGovernorPage.prepare_dependencies(page)

    assert ("quick-access", {"install_decky": True}) in calls
    assert not any(call[0] == "config" for call in calls if isinstance(call, tuple))
    dispatch = next(call for call in calls if isinstance(call, tuple) and call[0] == "dispatch")
    assert dispatch[1] == "Could not prepare Game Mode Quick Access"


def test_dependency_mitigations_route_uses_the_explicit_bazzite_transaction(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _MitigationsPreparationDialog,
    )
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.ConfirmDialog", _AcceptedDialog
    )
    calls = []
    page = _dependency_route_page(
        calls,
        gestionar_mitigaciones_bazzite=lambda _self, action: calls.append(
            ("mitigations", action)
        ) or "terminal",
    )
    page._prepare_bazzite_mitigations = lambda action, dialog_parent=None: (  # noqa: SLF001
        GpuGovernorPage._prepare_bazzite_mitigations(
            page, action, dialog_parent=dialog_parent
        )
    )

    GpuGovernorPage.prepare_dependencies(page)

    assert ("mitigations", "disable") in calls
    dispatch = next(
        call for call in calls if isinstance(call, tuple) and call[0] == "dispatch"
    )
    assert dispatch[1] == "Could not update CPU security mitigations"


def test_dependency_removal_persists_auto_only_after_confirmation(monkeypatch):
    monkeypatch.setattr(
        "frontends.desktop.pages.gpu_governor.DependencyPreparationDialog",
        _RemovalPreparationDialog,
    )
    monkeypatch.setattr("frontends.desktop.pages.gpu_governor.ConfirmDialog", _AcceptedDialog)
    calls = []
    page = _dependency_route_page(
        calls,
        desinstalar_governor=lambda _self, governor: calls.append(("remove", governor)) or "terminal",
    )

    GpuGovernorPage.prepare_dependencies(page)

    assert ("config", {"gpu_governor": "auto"}) in calls
    assert ("remove", "oberon-governor") in calls
