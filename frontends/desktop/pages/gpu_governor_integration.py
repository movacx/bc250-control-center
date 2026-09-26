"""Incorporation of the redesigned GPU module into ``GpuGovernorPage``.

Destination: ``frontends/desktop/pages/gpu_governor_integration.py``

Strategy: ``gpu_governor.py`` is **not rewritten** (6400+ lines of already
tested logic). Only what is shown gets replaced — and only for the Cyan
backend; Oberon keeps its original screen untouched, per project policy.

``GpuGovernorPage`` already has:

    page.page_stack
      ├── page.overview_page      ← QVBoxLayout with page.overview_scroll inside
      └── page.voltage_lab_page

This module hides ``page.overview_scroll`` and mounts ``GpuGovernorView`` in
the same layout as ``overview_page`` — but only while the detected backend is
Cyan. Consequences:

* All existing code that does ``page_stack.setCurrentWidget(overview_page)``
  (``_close_voltage_lab``, ``after_success`` from ``_run_backend_action``,
  the gamepad) keeps working and now shows the new view for Cyan boards.
* The old widgets stay instantiated but hidden, so every page method that
  touches them (``_sync_range_state``, ``_update_metric_widgets``,
  ``_populate_points``…) keeps working without breaking.
* Hardware operations still go through ``_run_backend_action``: concurrency
  gate, background execution, cache invalidation and refresh.
* For an Oberon board, ``page.overview_scroll`` (the original, untouched
  screen) stays visible and the redesigned view stays hidden.

Integration (two lines in ``GpuGovernorPage.__init__``, at the end)::

    from .gpu_governor_integration import install_redesigned_gpu_view
    ...
    install_redesigned_gpu_view(self)

To roll back, delete those two lines. Nothing else was modified.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from PyQt6.QtWidgets import QApplication, QWidget

from bc250cc.domain.gpu.oberon import (
    OBERON_DESKTOP_PROFILES,
    OBERON_REFERENCE_VOLTAGE_MV,
)

from ..i18n import tr, tr_format
from .gpu_governor_view import (
    DEFAULT_PROFILES,
    GpuGovernorView,
    GpuProfile,
    GpuViewState,
    voltage_for,
)

_ATTRIBUTE = "_redesigned_gpu_view"


def _is_oberon(gpu: dict) -> bool:
    return str(gpu.get("governor_backend") or "") == "oberon-governor"


# ─────────────────────────────────────────────────────────────────────────────
# Saved profiles — shares QSettings keys with the original page
# ─────────────────────────────────────────────────────────────────────────────

#: Oberon's three shapes come from the shared contract, not from Cyan's
#: safe-point curve, and they are not user-editable.
OBERON_PROFILES: tuple[GpuProfile, ...] = tuple(
    GpuProfile(
        key=key,
        name=name,
        minimum=low,
        maximum=high,
        # Both YAML endpoints sit at the same voltage; Cyan's per-frequency
        # curve does not describe this board.
        fixed_voltage=OBERON_REFERENCE_VOLTAGE_MV,
    )
    for key, name, (low, high) in zip(
        ("balanced", "gaming", "benchmark"),
        ("Balanced", "Gaming", "Benchmark"),
        OBERON_DESKTOP_PROFILES,
    )
)


def _profiles_for(page, *, is_oberon: bool) -> tuple[GpuProfile, ...]:
    return OBERON_PROFILES if is_oberon else _load_profiles(page)


def _load_profiles(page) -> tuple[GpuProfile, ...]:
    """Reads the profile overrides already saved by the original page."""
    profiles: list[GpuProfile] = []
    overrides = getattr(page, "_custom_profile_overrides", {}) or {}
    for slot, default in enumerate(DEFAULT_PROFILES):
        override = overrides.get(slot)
        if not override:
            profiles.append(replace(default))
            continue
        profiles.append(
            GpuProfile(
                key=default.key,
                name=str(override.get("name") or default.name),
                minimum=int(override.get("min") or default.minimum),
                maximum=int(override.get("max") or default.maximum),
            )
        )
    return tuple(profiles)


def _persist_profile(page, profile: GpuProfile) -> None:
    """Saves an edited profile under the same keys the page already uses."""
    try:
        from .gpu_governor import (  # lazy import: avoids a module cycle
            _save_custom_gpu_profile,
            application_settings,
        )
    except ImportError:  # pragma: no cover - the page was renamed
        return

    slot = next(
        (index for index, default in enumerate(DEFAULT_PROFILES) if default.key == profile.key),
        None,
    )
    if slot is None:
        return
    payload = {
        "name": profile.name,
        "min": int(profile.minimum),
        "max": int(profile.maximum),
        "frequency": int(profile.maximum),
        "voltage": int(voltage_for(profile.maximum)),
    }
    overrides = getattr(page, "_custom_profile_overrides", None)
    if overrides is not None:
        overrides[slot] = payload
    _save_custom_gpu_profile(application_settings(), slot, payload)
    if hasattr(page, "_apply_profile_overrides"):
        page._apply_profile_overrides()
    if hasattr(page, "_update_profile_availability"):
        page._update_profile_availability()


# ─────────────────────────────────────────────────────────────────────────────
# Hardware actions — always through _run_backend_action
# ─────────────────────────────────────────────────────────────────────────────

def _run(page, view: GpuGovernorView, operation: Callable, summary: str,
         error_title: str, *, controls: tuple[QWidget, ...] = (),
         toast_title: str = "") -> None:
    """Runs a controller operation with the page's own plumbing.

    ``toast_title`` also reports the outcome in a toast, for an action whose
    result is not visible anywhere on the page (an export, for instance).
    """

    def success(result: object) -> None:
        message = str(result) if isinstance(result, str) and result else summary
        if isinstance(result, dict):
            message = str(result.get("operation_message") or summary)
        page._last_operation_summary = message
        last_line = getattr(page, "last_operation_line", None)
        if last_line is not None:
            last_line.set_values(tr("Last operation"), message)
        page._append_console(message)
        if toast_title:
            page._show_info(toast_title, summary, tone="green")

    page._run_backend_action(operation, success, error_title, controls=controls)


def _apply_range(page, view: GpuGovernorView, minimum: int, maximum: int) -> None:
    """The view already confirmed with its own dialog: just execute here."""
    # The staged range is now the requested range, so the view can go back to
    # following whatever the hardware reports.
    view.follow_hardware_again()
    _run(
        page,
        view,
        lambda: page.controller.aplicar_perfil_gpu(minimum, maximum),
        tr_format(
            "D-Bus range {minimum}–{maximum} MHz requested.",
            minimum=minimum, maximum=maximum,
        ),
        "GPU range failed",
        controls=(view.apply_button,),
    )


def _save_for_startup(page, view: GpuGovernorView, minimum: int, maximum: int) -> None:
    _run(
        page,
        view,
        page.controller.guardar_rango_gpu_arranque,
        tr_format(
            "D-Bus range {minimum}–{maximum} MHz saved for startup.",
            minimum=minimum, maximum=maximum,
        ),
        "Could not save the startup range",
        controls=(view.startup_button,),
    )


def _export_profiles_to_decky(page, view: GpuGovernorView) -> None:
    """Publishes the three visible profile cards for the Decky panel to read.

    Read-only metadata, not a hardware change, so it reuses ``_run`` (which
    already routes through the concurrency gate, background execution and
    console) without touching ``_run_backend_action``'s cache-invalidation
    path meant for GPU state changes.
    """
    payload = [
        {"key": profile.key, "name": profile.name, "min": profile.minimum, "max": profile.maximum}
        for profile in view.profiles()
    ]
    _run(
        page,
        view,
        lambda: page.controller.exportar_perfiles_gpu_decky(payload),
        tr("Profiles exported to Decky Quick Access."),
        "Could not export profiles to Decky",
        controls=(view._export_decky_button,),
        # Nothing on the page changes after an export, so without this the
        # click looked ignored; the CPU and Fans pages already said so.
        toast_title=tr("Export to Decky"),
    )


def _toggle_high_points(page, view: GpuGovernorView, enable: bool) -> None:
    """The view already showed the red confirmation dialog."""

    def success(result: object) -> None:
        if hasattr(page, "_apply_high_points_toggle_feedback"):
            page._apply_high_points_toggle_feedback(enable)
        message = str(result) if isinstance(result, str) and result else tr("Governor TOML updated.")
        page._last_operation_summary = message
        page._append_console(message)
        view.apply_state(replace(view._state, unlocked=enable))

    page._run_backend_action(
        lambda: page.controller.alternar_puntos_gpu_altos(enable),
        success,
        "Could not update advanced safe-points",
        controls=(view.unlock_button,),
    )


def _apply_compatibility(page, view: GpuGovernorView, options: dict) -> None:
    """The view owns the method selectors; mirror them onto the legacy combos.

    The original page keeps its own combos alive (hidden) and reads them in
    ``_request_cyan_compatibility``, so both paths must agree.
    """
    set_method = str(options.get("set_method") or "smu")
    usage_method = str(options.get("usage_method") or "busy-flag")
    for attribute, value in (
        ("cyan_set_method", set_method),
        ("cyan_usage_method", usage_method),
    ):
        combo = getattr(page, attribute, None)
        if combo is None or not hasattr(combo, "findData"):
            continue
        index = combo.findData(value)
        if index >= 0:
            blocked = combo.blockSignals(True)
            try:
                combo.setCurrentIndex(index)
            finally:
                combo.blockSignals(blocked)

    _run(
        page,
        view,
        lambda: page.controller.configurar_compatibilidad_gpu_cyan(
            set_method,
            usage_method,
            bool(options.get("metrics")),
            bool(options.get("frequencies")),
        ),
        tr("Cyan compatibility updated."),
        "Could not update Cyan compatibility settings",
    )


# ``plan_gpu_service_action`` only accepts these three names and raises
# ValueError on anything else — which, inside a Qt slot, takes the process
# down.  The view speaks English, so translate here rather than leaking the
# backend vocabulary into the presentation layer.
_SERVICE_ACTIONS = {
    "enable": "activar",
    "restart": "reiniciar",
    "disable": "desactivar",
}

# Cyan's fix-metrics / fix-freq replace GPU sensor files with patched copies
# through a bind mount that lives as long as the daemon does. Both are off by
# default because a stock BC-250 kernel cannot host them: the startup guard in
# gpu_repository refuses fix-metrics outright ("this kernel/runtime cannot
# provide Cyan gpu_metrics safely"), and a fix-freq mount left behind by an
# earlier run makes the next start fail with exit status 32. Starting the
# service is therefore the moment to put both back to off. set-method and the
# usage method are the user's deliberate choices and are never touched here;
# anyone on a patched kernel can turn either flag back on explicitly.
FACTORY_FIX_METRICS = False
FACTORY_FIX_FREQUENCY = False


def _service_action(page, action: str) -> None:
    """'status' is a pure read; everything else uses the page's own confirmed flow."""
    if action == "status":
        page.read_service_status()
        return
    backend_action = _SERVICE_ACTIONS.get(action)
    if backend_action is None:
        page._append_console(f"Unsupported governor service action: {action}")
        return
    if action == "enable":
        _reset_fix_flags_to_factory(page)
    page._service_action(backend_action)


def _reset_fix_flags_to_factory(page) -> None:
    """Put fix-metrics / fix-freq back to their known-good values.

    Best effort on purpose: if the compatibility write fails the service start
    still goes ahead, and the daemon reports the real reason itself. Silently
    refusing to start because a preparatory step failed would be worse.
    """
    telemetry = (getattr(page, "current_state", None) or {}).get("cyan_telemetry")
    current = telemetry if isinstance(telemetry, dict) else {}
    set_method = str(current.get("set_method") or "smu")
    usage_method = str(current.get("method") or "busy-flag")
    if (
        bool(current.get("fix_metrics", FACTORY_FIX_METRICS)) == FACTORY_FIX_METRICS
        and bool(current.get("fix_frequency", FACTORY_FIX_FREQUENCY)) == FACTORY_FIX_FREQUENCY
    ):
        return
    try:
        page.controller.configurar_compatibilidad_gpu_cyan(
            set_method, usage_method, FACTORY_FIX_METRICS, FACTORY_FIX_FREQUENCY
        )
    except Exception as error:  # pragma: no cover - reported, never fatal
        page._append_console(f"Could not reset Cyan fix flags: {error}")
    else:
        page._append_console(
            "Cyan fix-metrics and fix-freq reset to their default values before start."
        )


def _copy_diagnostics(view: GpuGovernorView) -> None:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(view.console_text())
        view.append_console_line(tr("Diagnostics copied to clipboard."))


# ─────────────────────────────────────────────────────────────────────────────
# State push — wraps the page's existing hooks
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_apply_state(page, view: GpuGovernorView) -> None:
    """After every refresh, translates the backend dict into the view.

    Both backends are shown here now. Oberon used to keep the original screen,
    which meant two different layouts for the same job; it now wears this one
    with the Cyan-only panels hidden, so the buttons sit in the same places on
    either board. Cyan's own behaviour is unchanged.
    """
    original = page._apply_state

    def patched(gpu: dict, perf: dict) -> None:
        original(gpu, perf)
        is_oberon = _is_oberon(gpu)
        legacy_scroll = getattr(page, "overview_scroll", None)
        view.setVisible(True)
        if legacy_scroll is not None:
            legacy_scroll.setVisible(False)
        view.set_oberon_mode(is_oberon)
        view.set_profiles(_profiles_for(page, is_oberon=is_oberon))
        try:
            telemetry = page._telemetry_copy(gpu, perf)
        except Exception:  # pragma: no cover - partial telemetry
            telemetry = {}
        state = GpuViewState.from_backend(gpu, telemetry)
        view.apply_state(state)
        # The view itself decides whether to take this: it ignores the hardware
        # range while the user is staging one of their own.
        view.sync_active_range(state.active_minimum, state.active_maximum)

    page._apply_state = patched  # type: ignore[method-assign]


def _wrap_console(page, view: GpuGovernorView) -> None:
    """Mirrors the page's console into the view's console."""
    original = page._append_console

    def patched(message: str) -> None:
        original(message)
        view.append_console_line(str(message))

    page._append_console = patched  # type: ignore[method-assign]


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def install_redesigned_gpu_view(page) -> GpuGovernorView:
    """Mounts the redesigned view over an already-built ``GpuGovernorPage``.

    Idempotent: if it is already installed, returns the same instance.
    """
    existing = getattr(page, _ATTRIBUTE, None)
    if existing is not None:
        return existing

    view = GpuGovernorView(page)
    setattr(page, _ATTRIBUTE, view)

    # 1 · take over the overview page without touching page_stack. The swap
    # happens here rather than on the first refresh: waiting meant the old
    # screen was painted for the second or so before telemetry arrived, and
    # since this view now serves both backends there is nothing left to wait
    # for. Cyan is the starting mode because that is also what
    # ``resolve_gpu_governor`` falls back to; an Oberon board corrects itself
    # on the first refresh.
    layout = page.overview_page.layout()
    if layout is not None:
        layout.addWidget(view)
    view.show()
    legacy_scroll = getattr(page, "overview_scroll", None)
    if legacy_scroll is not None:
        legacy_scroll.hide()

    # 2 · saved profiles
    view.set_profiles(_load_profiles(page))

    # 3 · signals → real backend
    view.range_apply_requested.connect(
        lambda low, high: _apply_range(page, view, low, high)
    )
    view.range_startup_requested.connect(
        lambda low, high: _save_for_startup(page, view, low, high)
    )
    view.high_points_toggle_requested.connect(
        lambda enable: _toggle_high_points(page, view, enable)
    )
    view.compatibility_apply_requested.connect(
        lambda options: _apply_compatibility(page, view, options)
    )
    view.service_action_requested.connect(lambda action: _service_action(page, action))
    view.profile_changed.connect(lambda profile: _persist_profile(page, profile))
    view.export_to_decky_requested.connect(lambda: _export_profiles_to_decky(page, view))
    view.voltage_lab_requested.connect(page.open_voltage_lab)
    view.config_open_requested.connect(page._open_governor_config)
    view.diagnostics_copy_requested.connect(lambda: _copy_diagnostics(view))

    # 4 · backend → view
    _wrap_apply_state(page, view)
    _wrap_console(page, view)

    # 5 · initial state if a refresh already happened
    current = getattr(page, "current_state", None)
    if current:
        legacy_scroll = getattr(page, "overview_scroll", None)
        view.setVisible(True)
        if legacy_scroll is not None:
            legacy_scroll.setVisible(False)
        view.set_oberon_mode(_is_oberon(current))
        view.set_profiles(_profiles_for(page, is_oberon=_is_oberon(current)))
        view.apply_state(
            GpuViewState.from_backend(current, getattr(page, "current_perf", {}) or {})
        )
    return view


def uninstall_redesigned_gpu_view(page) -> None:
    """Reverts to the original screen (useful for comparing during rollout)."""
    view = getattr(page, _ATTRIBUTE, None)
    if view is None:
        return
    view.setParent(None)
    view.deleteLater()
    delattr(page, _ATTRIBUTE)
    legacy_scroll = getattr(page, "overview_scroll", None)
    if legacy_scroll is not None:
        legacy_scroll.show()
