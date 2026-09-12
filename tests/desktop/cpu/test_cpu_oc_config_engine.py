from pathlib import Path

import pytest

import bc250cc.infrastructure.cpu_oc_config as engine
from bc250cc.infrastructure.cpu_oc_config import (
    estimated_vid,
    parse_cpu_oc_config,
    read_cpu_oc_config,
)


def config(frequency="3850", scale="-30", temperature="90"):
    return (
        "[overclock]\n"
        f"frequency = {frequency}\n"
        f"scale = {scale}\n"
        f"max_temperature = {temperature}\n"
    )


def test_pure_parser_returns_typed_upstream_values():
    result = parse_cpu_oc_config(config(), path="/fixture/overclock.conf")
    assert result == {
        "path": "/fixture/overclock.conf",
        "exists": True,
        "readable": True,
        "valid": True,
        "error": "",
        "error_kind": "",
        "frequency": 3850,
        "scale": -30,
        "max_temperature": 90,
        "estimated_vid": estimated_vid(3850, -30),
        "vid_source": "upstream-curve-estimate",
    }


@pytest.mark.parametrize(
    ("text", "kind"),
    (
        ("", "parse"),
        ("[overclock]\nfrequency=3850\nfrequency=3900\nscale=-30\nmax_temperature=90", "parse"),
        (config(frequency="nan"), "parse"),
        (config(frequency="3099"), "range"),
        (config(frequency="4201"), "range"),
        (config(scale="-51"), "range"),
        (config(scale="1"), "range"),
        (config(temperature="69"), "range"),
        (config(temperature="91"), "range"),
    ),
)
def test_invalid_or_out_of_range_content_fails_closed(text, kind):
    result = parse_cpu_oc_config(text)
    assert result["valid"] is False
    assert result["readable"] is True
    assert result["error_kind"] == kind


def test_direct_symlink_is_rejected_without_reading_target(tmp_path):
    target = tmp_path / "target"
    target.write_text(config(), encoding="utf-8")
    link = tmp_path / "overclock.conf"
    link.symlink_to(target)
    result = read_cpu_oc_config(link)
    assert result["valid"] is False
    assert result["error_kind"] == "type"


def test_symlink_swap_between_preflight_and_open_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "overclock.conf"
    source.write_text(config(), encoding="utf-8")
    target = tmp_path / "other"
    target.write_text(config(scale="0"), encoding="utf-8")
    original_open = engine.os.open
    swapped = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == source and not swapped:
            swapped = True
            source.unlink()
            source.symlink_to(target)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(engine.os, "open", racing_open)
    result = read_cpu_oc_config(source)
    assert result["valid"] is False
    assert result["error_kind"] == "io"


def test_file_size_is_bounded_before_parse(tmp_path):
    source = tmp_path / "overclock.conf"
    source.write_bytes(b"x" * 65)
    result = read_cpu_oc_config(source, maximum=64)
    assert result["valid"] is False
    assert result["error_kind"] == "size"


def test_non_utf8_file_is_io_error_not_parser_success(tmp_path):
    source = tmp_path / "overclock.conf"
    source.write_bytes(b"\xff")
    result = read_cpu_oc_config(source)
    assert result["valid"] is False
    assert result["error_kind"] == "io"
