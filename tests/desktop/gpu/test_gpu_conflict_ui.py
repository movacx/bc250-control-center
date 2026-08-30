from frontends.desktop.pages.gpu_governor import GpuGovernorPage


class SafetyNotice:
    def __init__(self):
        self.payload = None

    def set_notice(self, title, message, *, tone):
        self.payload = (title, message, tone)


class Status:
    def __init__(self):
        self.text = ""
        self.tone = ""

    def setText(self, value):
        self.text = value

    def set_tone(self, value):
        self.tone = value


def test_existing_conflicting_governor_gets_visible_red_warning():
    page = type("Page", (), {
        "_update_safety_notice": GpuGovernorPage._update_safety_notice,
        "safety_notice": SafetyNotice(),
        "configuration_status": Status(),
        "safe_frequencies": [],
    })()
    page._update_safety_notice({
        "dbus_ok": True,
        "tools": {
            "incompatible_gpu_governors": [{
                "identifier": "oberon-governor",
                "active": True,
            }],
        },
    })
    title, message, tone = page.safety_notice.payload
    assert title == "Incompatible GPU governor detected"
    assert "green screen" in message
    assert tone == "red"
    assert page.configuration_status.tone == "red"


def test_invalid_cyan_toml_blocks_curve_controls_with_a_specific_notice():
    page = type("Page", (), {
        "_update_safety_notice": GpuGovernorPage._update_safety_notice,
        "safety_notice": SafetyNotice(),
        "configuration_status": Status(),
        "safe_frequencies": [],
    })()

    page._update_safety_notice({
        "governor_backend": "cyan-skillfish-governor-smu",
        "safe_points_error": "Governor TOML validation failed",
        "tools": {},
    })

    title, message, tone = page.safety_notice.payload
    assert title == "Governor configuration could not be validated"
    assert "safe-point curve was not loaded" in message
    assert tone == "red"
    assert page.configuration_status.tone == "red"


def test_cyan_compatibility_ui_exposes_and_syncs_every_upstream_usage_method(qapp):
    page = GpuGovernorPage(object())
    try:
        assert [
            page.cyan_usage_method.itemData(index)
            for index in range(page.cyan_usage_method.count())
        ] == ["busy-flag", "process", "kernel"]

        page._sync_cyan_compatibility(
            {
                "cyan_telemetry": {
                    "set_method": "kernel",
                    "method": "kernel",
                    "fix_metrics": False,
                    "fix_frequency": False,
                }
            },
            is_oberon=False,
        )

        assert page.cyan_set_method.currentData() == "kernel"
        assert page.cyan_usage_method.currentData() == "kernel"
        assert page.cyan_fix_metrics.isChecked() is False
        assert page.cyan_fix_frequency.isChecked() is False
    finally:
        page.timer.stop()
        page.deleteLater()
