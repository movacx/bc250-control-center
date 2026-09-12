"""Detection of other community toolkits that own the same BC-250 state."""

from __future__ import annotations

from pathlib import Path

from bc250cc.infrastructure.toolkit_conflicts import (
    KNOWN_TOOLKITS,
    SHARED_CONFIGURATION,
    describe_toolkit_conflict,
    detect_foreign_toolkits,
)


def _touch(root: Path, path: str) -> None:
    target = root / path.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")


def test_clean_system_reports_no_toolkit(tmp_path: Path) -> None:
    assert detect_foreign_toolkits(root=tmp_path) == ()


def test_shared_paths_alone_are_not_evidence(tmp_path: Path) -> None:
    """Control Center writes these itself, so they must never accuse anyone."""
    for path in SHARED_CONFIGURATION:
        _touch(tmp_path, path)
    assert detect_foreign_toolkits(root=tmp_path) == ()


def test_marker_file_identifies_the_toolkit(tmp_path: Path) -> None:
    _touch(tmp_path, "/etc/systemd/system/bc250-cu-failure-capture.service")
    detected = detect_foreign_toolkits(root=tmp_path)
    assert len(detected) == 1
    assert detected[0]["identifier"] == "bc250-toolkit"
    assert "/etc/systemd/system/bc250-cu-failure-capture.service" in detected[0]["evidence"]


def test_detection_reports_the_shared_files_that_will_be_fought_over(tmp_path: Path) -> None:
    _touch(tmp_path, "/etc/udev/rules.d/91-ac3-audio.rules")
    _touch(tmp_path, "/etc/bc250-smu-oc.conf")
    detected = detect_foreign_toolkits(root=tmp_path)
    assert detected[0]["shared_paths"] == ["/etc/bc250-smu-oc.conf"]
    assert "CPU tuning" in detected[0]["overlapping_areas"]


def test_message_names_the_toolkit_without_ordering_a_removal(tmp_path: Path) -> None:
    _touch(tmp_path, "/etc/dracut.conf.d/bc250-modules.conf")
    message = describe_toolkit_conflict(detect_foreign_toolkits(root=tmp_path))
    assert "BC250 Toolkit" in message
    # The user is entitled to run other tools; never tell them to uninstall.
    assert "uninstall" not in message.lower()
    assert "remove" not in message.lower()


def test_every_spec_declares_evidence_and_overlap() -> None:
    for spec in KNOWN_TOOLKITS:
        assert spec.markers, f"{spec.identifier} has no marker to detect it"
        assert spec.overlapping_areas, f"{spec.identifier} declares no overlap"
        assert spec.upstream.startswith("https://")
        # A marker that Control Center also writes would accuse itself.
        assert not set(spec.markers) & set(SHARED_CONFIGURATION)


def test_real_toolkit_is_identified_by_its_own_units(tmp_path: Path) -> None:
    """Markers taken from the upstream installer, not guessed."""
    _touch(tmp_path, "/etc/systemd/system/bc250-toolkit-persist.service")
    detected = detect_foreign_toolkits(root=tmp_path)
    assert [item["identifier"] for item in detected] == ["bc250-steamos-real-toolkit"]
    assert "Audio" in detected[0]["overlapping_areas"]


def test_batocera_tools_are_identified_by_their_userdata_paths(tmp_path: Path) -> None:
    """Batocera keeps state under /userdata because its root is read-only."""
    _touch(tmp_path, "/userdata/system/bc250-8core")
    detected = detect_foreign_toolkits(root=tmp_path)
    assert [item["identifier"] for item in detected] == ["bc250-batocera-tools"]


def test_two_toolkits_at_once_are_both_reported(tmp_path: Path) -> None:
    _touch(tmp_path, "/etc/bc250-control")
    _touch(tmp_path, "/etc/dracut.conf.d/bc250-modules.conf")
    identifiers = {item["identifier"] for item in detect_foreign_toolkits(root=tmp_path)}
    assert identifiers == {"bc250-steamos-real-toolkit", "bc250-toolkit"}
