from pathlib import Path

import bc250cc.infrastructure.cpu_oc_config as cpu_oc_config
from bc250cc.infrastructure.cpu_repository import CPURepository


def _config_text(frequency=3850, scale=-30, temperature=90):
    return (
        "[overclock]\n"
        f"frequency = {frequency}\n"
        f"scale = {scale}\n"
        f"max_temperature = {temperature}\n"
    )


def test_cpu_oc_config_parser_distinguishes_permission_error_from_invalid_content(tmp_path, monkeypatch):
    config = tmp_path / "bc250-smu-oc.conf"
    config.write_text(_config_text(), encoding="utf-8")
    original_open = cpu_oc_config.os.open

    def protected_open(path, *args, **kwargs):
        if Path(path) == config:
            raise PermissionError(13, "Permission denied", str(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(cpu_oc_config.os, "open", protected_open)
    state = CPURepository._read_cpu_oc_config(config)

    assert state["exists"] is True
    assert state["valid"] is False
    assert state["readable"] is False
    assert state["error_kind"] == "permission"
    assert "protected" in state["error"].lower()


def test_cpu_oc_config_parser_marks_valid_boot_config_readable(tmp_path):
    config = tmp_path / "bc250-smu-oc.conf"
    config.write_text(_config_text(), encoding="utf-8")
    state = CPURepository._read_cpu_oc_config(config)
    assert state["readable"] is True
    assert state["valid"] is True
    assert state["error_kind"] == ""
