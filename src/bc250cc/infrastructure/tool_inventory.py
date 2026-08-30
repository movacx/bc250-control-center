"""Pure capability selection for discovered BC250 tools."""

from __future__ import annotations

from dataclasses import dataclass

from .external_tools.catalog import EXTERNAL_TOOLS

STANDARD_CU_URL = EXTERNAL_TOOLS["cu_manager_standard"].upstream
STEAMOS_CU_URL = EXTERNAL_TOOLS["cu_manager_steamos"].upstream


@dataclass(frozen=True)
class CUBackendSelection:
    manager: str
    kind: str
    backend: str
    repository_path: str
    repository_url: str
    warning: str
    exists: bool
    blocked: bool
    wrong_backend_present: bool
    required_backend: str


def select_cu_backend(
    *,
    is_steamos: bool,
    standard_path: str,
    standard_path_exists: bool,
    standard_backend: str,
    standard_repository: str,
    steamos_path: str,
    steamos_exists: bool,
    steamos_repository: str,
    expected_steamos_repository: str,
) -> CUBackendSelection:
    """Choose a CU backend from already discovered, untrusted path evidence."""
    if not is_steamos:
        return CUBackendSelection(
            manager=standard_path if standard_path_exists else "",
            kind="WinnieLV/bc250-cu-live-manager" if standard_path_exists else "",
            backend="standard",
            repository_path=standard_repository if standard_path_exists else "",
            repository_url=STANDARD_CU_URL,
            warning="",
            exists=standard_path_exists,
            blocked=False,
            wrong_backend_present=False,
            required_backend="standard",
        )

    wrong_backend = bool(standard_path_exists and standard_backend != "steamos")
    if steamos_exists:
        warning = ""
    elif wrong_backend:
        warning = (
            "SteamOS requires the F5GO SteamOS 40CU backend. A standard WinnieLV "
            "installation was detected and has been ignored to prevent incompatible "
            "register operations. Use Prepare dependencies or Prepare Live Manager "
            "before using any 40CU action."
        )
    else:
        warning = (
            "SteamOS requires the F5GO SteamOS 40CU backend. Use Prepare dependencies "
            "or Prepare Live Manager before using any 40CU action."
        )
    return CUBackendSelection(
        manager=steamos_path if steamos_exists else "",
        kind="F5GO/bc250-cu-live-manager-SteamOS",
        backend="steamos",
        repository_path=(steamos_repository if steamos_exists else "")
        or expected_steamos_repository,
        repository_url=STEAMOS_CU_URL,
        warning=warning,
        exists=steamos_exists,
        blocked=not steamos_exists,
        wrong_backend_present=wrong_backend,
        required_backend="steamos",
    )


def mark_component_installation(
    capabilities: dict[str, dict[str, object]], installed: dict[str, bool]
) -> dict[str, dict[str, object]]:
    """Copy capability metadata and overlay only known installation evidence."""
    result = {key: dict(value) for key, value in capabilities.items()}
    for key, value in installed.items():
        if key in result:
            result[key]["installed"] = bool(value)
    return result
