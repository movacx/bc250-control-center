from PyQt6.QtWidgets import QPushButton

from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _oberon_state(*, detected: bool, active: str) -> dict:
    return {
        "governor_backend": "oberon-governor",
        "service_active": active,
        "range_control_ok": active == "active",
        "tools": {
            "incompatible_gpu_governors": [],
            "supported_gpu_governors": {
                "oberon-governor": {
                    "detected": detected,
                    "binary_path": "/usr/local/bin/oberon-governor" if detected else "",
                    "unit_path": "/usr/lib/systemd/system/oberon-governor.service" if detected else "",
                    "active": active == "active",
                }
            },
        },
    }


def test_oberon_notice_distinguishes_missing_stopped_and_active(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)

    cases = (
        (_oberon_state(detected=False, active="not-found"), "Oberon Governor was not found", "Prepare dependencies"),
        (_oberon_state(detected=True, active="inactive"), "Oberon Governor is not active", "Activate service"),
        (_oberon_state(detected=True, active="active"), "Oberon profiles ready", "655%"),
    )
    for index, (state, expected_title, expected_detail) in enumerate(cases):
        page.current_state = state
        page._update_safety_notice(state)
        assert page.safety_notice.title.text() == expected_title
        assert expected_detail in page.safety_notice.body.text()
        if index < 2:
            assert "full" in page.safety_notice.body.text().lower()
            assert "Cyan Skillfish Governor" in page.safety_notice.body.text()


def test_removed_gpu_noise_cards_are_not_constructed(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)

    assert len(page.metric_tiles) == 6
    assert not hasattr(page, "power_metric")
    assert not hasattr(page, "dependencies_metric")
    assert not hasattr(page, "floor_buttons")
    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "Save persistent floor" not in button_texts
    assert "Prepare dependencies" not in button_texts


def test_new_oberon_notices_are_complete_in_every_supported_language():
    sources = (
        "Oberon Governor was not found",
        "Oberon is selected, but its program or system service is missing. Use Prepare dependencies to install it, or select Cyan Skillfish Governor for full BC250 Control Center support.",
        "Oberon Governor is not active",
        "Oberon is installed, but its service is stopped. Use Activate service to start it. BC250 Control Center provides full integration only with Cyan Skillfish Governor.",
        "Oberon profiles ready",
        "Oberon is active. Choose 1000–1500 or 1000–1850 MHz, or the fixed 2000 MHz benchmark profile after stopping all 3D load. BC250 verifies GPU idle state before restarting Oberon. MangoHud or radeontop may still report about 655% GPU usage.",
        "Protected",
        "Telemetry is passive. Hardware changes still require explicit confirmation.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language
