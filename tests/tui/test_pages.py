import pytest

from frontends.tui.layout import Glyphs, build_layout
from frontends.tui.pages import build_pages
from frontends.tui.pages.extras import TABS as EXTRA_TABS
from frontends.tui.pages.extras import AdditionalSettingsPage

from .fakes import GPU_STATE, FakeService, FakeUI, make_context

GLYPHS = Glyphs.for_terminal(unicode_ok=False)


def render(page, ctx, ui, tab=""):
    ctx.page_data[page.key] = page.load(ctx) if page.loads else None
    blocks = page.build(ctx, ctx.page_data[page.key], tab, ui)
    return build_layout(blocks, 80, GLYPHS)


def text_of(layout):
    return "\n".join("".join(t for t, _ in row.spans) for row in layout.rows)


def choice(layout, label):
    return next(c for c in layout.choices if c.label == label)


def test_every_sidebar_page_builds_on_every_tab_without_a_service_error():
    ctx, ui = make_context(), FakeUI()
    for key, page in build_pages().items():
        tabs = [name for name, _ in page.tabs(ctx)] or [""]
        for tab in tabs:
            layout = render(page, ctx, ui, tab)
            assert layout.rows, (key, tab)


def test_sidebar_covers_the_desktop_sections():
    assert set(build_pages()) == {
        "dashboard", "cpu", "gpu", "extras", "cu", "performance", "fans", "processes", "black_box",
        "firmware", "settings",
    }


def test_dashboard_shows_the_live_gpu_reading_and_a_missing_one_as_dashes():
    ctx, ui = make_context(), FakeUI()
    page = build_pages()["dashboard"]
    assert "1500 MHz" in text_of(render(page, ctx, ui))
    ctx.metrics = {}
    ctx.metrics_error = "boom"
    assert "boom" in text_of(render(page, ctx, ui))


def test_gpu_range_sliders_step_through_the_safe_points_and_apply_after_confirmation():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()["gpu"]
    layout = render(page, ctx, ui)
    choice(layout, "Maximum frequency").adjust(ui, 1)  # 1850 -> 2000
    layout = render(page, ctx, ui)
    choice(layout, "Review and apply range").handler(ui)
    assert ("aplicar_rango_bc250", (1000, 2000), {}) in service.calls
    assert ui.confirmations


def test_gpu_profile_applies_its_range_after_confirmation():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI()
    layout = render(build_pages()["gpu"], ctx, ui)
    next(c for c in layout.choices if c.label.strip().endswith("Gaming") or "Gaming" in c.label).handler(ui)
    assert ("aplicar_perfil_gpu", (1000, 1850), {}) in service.calls


def test_declining_the_confirmation_changes_nothing():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI(confirm=False)
    page = build_pages()["gpu"]
    choice(render(page, ctx, ui), "Maximum frequency").adjust(ui, 1)
    choice(render(page, ctx, ui), "Review and apply range").handler(ui)
    assert not [call for call in service.calls if call[0].startswith("aplicar")]


def test_cancelling_a_prompt_changes_nothing():
    service = FakeService()
    ctx = make_context(service)

    class Cancelling(FakeUI):
        def ask_int(self, *args):
            return None

    ui = Cancelling()
    choice(render(build_pages()["cpu"], ctx, ui), "Frequency").handler(ui)
    assert service.calls == []


def test_voltage_lab_shows_the_selected_curve_and_applies_a_boost_after_confirmation():
    service = FakeService()
    service.estado_bc250 = lambda: dict(GPU_STATE, safe_points_with_voltage=[
        {"frequency": f, "voltage": v} for f, v in ((500, 700), (1000, 800), (2000, 960), (2400, 1150))],
        safe_points=[{"frequency": 500}, {"frequency": 2400}])
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()["gpu"]
    layout = render(page, ctx, ui, "voltage")
    assert "2000 MHz" in text_of(layout) and "970 mV" in text_of(layout)  # +10 mV above 2000 MHz
    choice(layout, "Review and apply").handler(ui)
    assert ("aplicar_laboratorio_voltaje_gpu", (1,), {}) in service.calls
    assert ui.confirmations[-1][1] is True


def test_voltage_lab_refuses_a_custom_curve_that_goes_down_with_frequency():
    service = FakeService()
    service.estado_bc250 = lambda: dict(GPU_STATE, safe_points_with_voltage=[
        {"frequency": f, "voltage": v} for f, v in ((500, 700), (1000, 800), (2000, 960))])
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()["gpu"]
    ctx.state("gpu")["level"] = -1
    ctx.state("gpu")["custom"] = {2000: 700}
    layout = render(page, ctx, ui, "voltage")
    choice(layout, "Review and apply").handler(ui)
    assert not any(c[0].startswith("aplicar_laboratorio") for c in service.calls)
    assert ui.notes and ui.notes[-1][1] == "bad"


def test_a_failing_service_call_is_reported_with_the_catalogue_text_not_a_traceback():
    class Broken(FakeService):
        def guardar_rango_gpu_arranque(self):
            raise RuntimeError("helper exploded")

    ctx, ui = make_context(Broken()), FakeUI()
    choice(render(build_pages()["gpu"], ctx, ui), "Save active range for startup").handler(ui)
    message, tone = ui.notes[-1]
    assert tone == "bad" and "helper exploded" in message and "Traceback" not in message


def test_compute_units_grid_toggles_the_cell_under_the_cursor_and_applies_the_edited_table():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()["cu"]
    layout = render(page, ctx, ui)
    grid = layout.choices[0].pad
    assert grid is not None
    grid.toggle(ui)  # cursor starts on SE0.SH0 / WGP0
    layout = render(page, ctx, ui)
    assert "38 / 40" in text_of(layout)
    choice(layout, "Apply live table").handler(ui)
    applied = next(call for call in service.calls if call[0] == "aplicar_tabla_cu")
    assert applied[1][0] == [30, 31, 31, 31]


def test_compute_units_grid_moves_in_two_dimensions_and_reports_the_edges():
    ctx, ui = make_context(), FakeUI()
    grid = render(build_pages()["cu"], ctx, ui).choices[0].pad
    assert grid.move(0, 1) and grid.move(1, 0)
    assert ctx.state("cu")["cursor"] == (1, 1)
    assert not grid.move(-2, 0) or ctx.state("cu")["cursor"] == (1, 1)
    for _ in range(10):
        grid.move(0, 1)
    assert ctx.state("cu")["cursor"][1] == 4 and grid.move(0, 1) is False


def test_fans_set_duty_converts_percent_to_pwm():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI(ints=[100])
    layout = render(build_pages()["fans"], ctx, ui)
    next(c for c in layout.choices if c.label.startswith("Apply PWM")).handler(ui)
    assert ("aplicar_pwm_fan", (2, 255), {}) in service.calls


def test_protected_processes_cannot_be_acted_on():
    ctx, ui = make_context(), FakeUI()
    layout = render(build_pages()["processes"], ctx, ui)
    protected = choice(layout, "systemd")
    assert not protected.enabled
    assert choice(layout, "game").enabled


def test_closing_a_process_needs_a_choice_and_a_confirmation():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI(choices=["close"])
    choice(render(build_pages()["processes"], ctx, ui), "game").handler(ui)
    assert any(call[0] == "cerrar_procesos" for call in service.calls)
    assert ui.confirmations[-1][1] is True


def test_extras_only_offers_what_applies_to_the_detected_family():
    ctx, ui = make_context(), FakeUI()
    page = AdditionalSettingsPage()
    ctx.state("extras").update(family="steamos", name="SteamOS")
    labels = {c.label for c in render(page, ctx, ui, "compatibility").choices}
    assert "SteamOS read-only mode" in labels and "Simultaneous multithreading (SMT)" not in labels
    ctx.state("extras").update(family="bazzite", name="Bazzite")
    labels = {c.label for c in render(page, ctx, ui, "compatibility").choices}
    assert "Simultaneous multithreading (SMT)" in labels and "SteamOS read-only mode" not in labels


def test_extras_action_runs_the_selected_service_method_with_the_selected_action():
    service = FakeService()
    ctx, ui = make_context(service), FakeUI(choices=["disable"])
    ctx.state("extras").update(family="bazzite", name="Bazzite")
    layout = render(AdditionalSettingsPage(), ctx, ui, "compatibility")
    choice(layout, "Simultaneous multithreading (SMT)").handler(ui)
    assert ("gestionar_smt_bazzite", ("disable",), {}) in service.calls
    assert ui.confirmations[-1][1] is True  # disabling SMT is a dangerous action


def test_every_extras_entry_targets_a_method_the_real_service_has():
    from bc250cc.infrastructure.system_service import SistemaService

    for entries in EXTRA_TABS.values():
        for entry in entries:
            assert hasattr(SistemaService, entry.method), entry.method


def test_every_service_method_the_pages_call_exists_on_the_real_service():
    import ast
    from pathlib import Path

    from bc250cc.infrastructure.system_service import SistemaService

    allowed_missing = set()
    for path in Path("frontends/tui/pages").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "service" and not hasattr(SistemaService, node.attr)):
                allowed_missing.add((path.name, node.attr))
    assert not allowed_missing


def test_settings_language_change_is_saved_and_applied():
    saved = []
    ctx, ui = make_context(), FakeUI(choices=["es"])
    ctx.settings.save_local_config = saved.append
    page = build_pages()["settings"]
    layout = render(page, ctx, ui, "general")
    choice(layout, "Language").handler(ui)
    assert saved and saved[-1]["idioma"] == "es"
    from frontends.tui.i18n import set_language
    set_language("en")


def test_settings_theme_is_applied_to_the_screen():
    ctx, ui = make_context(), FakeUI(choices=["mono"])
    choice(render(build_pages()["settings"], ctx, ui, "general"), "Theme").handler(ui)
    assert ui.theme == "mono"


def test_black_box_diagnosis_tabs_follow_the_desktop_grouping():
    service = FakeService()
    service.diagnostico_completo = lambda: [("Kernel", "k"), ("Journal logs", "j"), ("Packages", "p")]
    ctx, ui = make_context(service), FakeUI()
    page = build_pages()["black_box"]
    layout = render(page, ctx, ui, "logs")
    choice(layout, "View full diagnosis").handler(ui)
    layout = render(page, ctx, ui, "logs")
    titles = {c.label for c in layout.choices}
    assert "Journal logs" in titles and "Kernel" not in titles
    assert {"Kernel", "Journal logs", "Packages"} <= {c.label for c in render(page, ctx, ui, "all").choices}


@pytest.mark.parametrize("key", ["gpu", "cu", "fans", "processes", "black_box", "firmware", "cpu"])
def test_pages_with_hardware_data_show_a_wait_note_before_the_first_load(key):
    ctx, ui = make_context(), FakeUI()
    page = build_pages()[key]
    blocks = page.build(ctx, None, "recorder" if key == "black_box" else "", ui)
    assert blocks  # never an empty screen
