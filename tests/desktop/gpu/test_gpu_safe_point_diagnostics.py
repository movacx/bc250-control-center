from bc250cc.infrastructure.gpu_repository import GPURepository
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr


def test_gpu_safe_point_snapshot_uses_the_validated_editor(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n",
        encoding="utf-8",
    )
    repository = object.__new__(GPURepository)
    repository._GOVERNOR_CONFIG = config

    state = repository._safe_points_config()

    assert state["points_with_voltage"] == [{"frequency": 1000, "voltage": 800}]
    assert state["config_path"] == str(config)
    assert state["error"] == ""


def test_gpu_safe_point_snapshot_keeps_telemetry_path_alive_on_invalid_toml(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        "[[safe-points]]\nfrequency = 1000oops\nvoltage = 800\n",
        encoding="utf-8",
    )
    repository = object.__new__(GPURepository)
    repository._GOVERNOR_CONFIG = config

    state = repository._safe_points_config()

    assert state["points"] == []
    assert state["max_frequency"] is None
    assert "validation failed" in state["error"]


def test_safe_point_validation_notice_is_translated_for_every_language():
    messages = (
        "Governor configuration could not be validated",
        "The safe-point curve was not loaded because the Cyan TOML is invalid. Repair the configuration or run Prepare dependencies before changing GPU clocks.",
    )

    for message in messages:
        for language in SUPPORTED_LANGUAGES - {"en"}:
            assert tr(message, language) != message
