from __future__ import annotations

import ast
from pathlib import Path

from bc250cc.application import ApplicationContainer
from bc250cc.platform import PlatformCapabilities
from bc250cc.shared import ErrorDetail, Result

ROOT = Path(__file__).resolve().parents[2]


def test_result_requires_exactly_one_outcome():
    success = Result.success("ready")
    failure = Result.failure(ErrorDetail("E_TEST", "not ready"))

    assert success.ok is True
    assert success.value == "ready"
    assert failure.ok is False
    assert failure.error.code == "E_TEST"


def test_empty_container_has_platform_capabilities():
    container = ApplicationContainer.empty()

    assert isinstance(container.platform, PlatformCapabilities)
    assert container.system_service is None


def test_new_layers_do_not_import_qt_or_subprocess():
    for path in (ROOT / "src" / "bc250cc" / "domain", ROOT / "src" / "bc250cc" / "application"):
        for source in path.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imports = {
                node.names[0].name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import) and node.names
            }
            imports.update(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            )
            assert not any(name == "subprocess" or name.startswith("PyQt") for name in imports), source


def test_system_use_cases_depend_on_contracts_not_infrastructure():
    for name in ("activity_service.py", "settings_service.py"):
        source = ROOT / "src" / "bc250cc" / "application" / "system" / name
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert not any(value.startswith("bc250cc.infrastructure") for value in imports), source
