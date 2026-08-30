from pathlib import Path

import pytest

from bc250cc.application.preparation.component_engine import (
    UnknownComponentError,
    component_capabilities,
    normalize_components,
    preparation_plan,
    unavailable_components,
    verification_shell,
)
from bc250cc.platform.packages.strategies.detector import OSInfo
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr


def test_runtime_is_mandatory_and_cu_manager_adds_umr():
    assert normalize_components({"cu_manager"}) == frozenset({"runtime", "umr", "cu_manager"})


def test_unknown_component_fails_before_system_work():
    with pytest.raises(UnknownComponentError, match="unknown-tool"):
        normalize_components({"unknown-tool"})


def test_capabilities_have_dependency_metadata_and_reboot_policy():
    info = OSInfo("bazzite", ("fedora",), "Bazzite", "Bazzite", "bazzite", "bazzite", True)
    capabilities = component_capabilities(info)
    assert capabilities["cu_manager"]["dependencies"] == ["umr"]
    assert capabilities["runtime"]["reboot"] is True
    assert capabilities["core_unlock"]["reboot"] is False


def test_verification_only_mentions_selected_optional_components():
    shell = "; ".join(verification_shell(
        {"runtime", "cpu_oc"},
        governor_binary="cyan-skillfish-governor-smu",
        cpu_oc_script=Path("/tools/bc250_detect.py"),
        core_unlock_script=Path("/tools/unlock.py"),
        cu_manager_script=Path("/tools/cu-manager"),
    ))
    assert "/tools/bc250_detect.py" in shell
    assert "cyan-skillfish-governor-smu" not in shell
    assert "/tools/unlock.py" not in shell
    assert "command -v umr" not in shell
    assert "stress" not in shell
    assert "sensors" not in shell


def test_plan_has_stable_component_order():
    assert [item["component"] for item in preparation_plan({"cu_manager"}, "steamos")] == [
        "runtime", "umr", "cu_manager"
    ]


def test_alpine_exposes_cpu_oc_limit_before_any_preparation_command():
    info = OSInfo("alpine", (), "Alpine", "Alpine", "", "alpine")
    capabilities = component_capabilities(info)

    assert capabilities["runtime"]["available"] is True
    assert capabilities["cpu_oc"]["available"] is False
    assert "stress binary" in str(capabilities["cpu_oc"]["detail"])
    assert set(unavailable_components({"cpu_oc"}, info)) == {"cpu_oc"}


def test_alpine_cpu_oc_limit_is_localized_in_every_interface_language():
    source = (
        "CPU OC is unavailable on Alpine: bc250_smu_oc requires the exact stress binary, "
        "while Alpine packages stress-ng with an incompatible interface."
    )
    # Polish uses a separately maintained catalog and may intentionally fall
    # back to the source while it is translated upstream; every other shipped
    # interface language must have an explicit non-English message.
    for language in SUPPORTED_LANGUAGES - {"pl", "en"}:
        assert tr(source, language=language) != source
