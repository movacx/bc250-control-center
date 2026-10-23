"""Pinned sources and directory names the dependency flows share."""

from __future__ import annotations

from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS

from .cyan_governor_runtime import CYAN_REVIEWED_RELEASE  # noqa: F401 - re-exported

CORE_UNLOCK_REPOSITORY = EXTERNAL_TOOLS["core_unlock"].upstream
CORE_UNLOCK_DIRECTORY = "bc250-core-unlock"
CORE_UNLOCK_SCRIPT = "bc250-unlock-cores.py"
CYAN_GOVERNOR_REPOSITORY = EXTERNAL_TOOLS["cyan_smu"].upstream
CYAN_GOVERNOR_DIRECTORY = "cyan-skillfish-governor-smu"
CYAN_GOVERNOR_BRANCH = "smu"
STEAMOS_FIX_REPOSITORY = EXTERNAL_TOOLS["steamos_amdgpu"].upstream
STEAMOS_FIX_REVIEWED_COMMIT = EXTERNAL_TOOLS["steamos_amdgpu"].reviewed_revision
STEAMOS_FIX_DIRECTORY = "bc250-steamos"
STEAMOS_FIX_SUBDIRECTORY = "bc250-audio-fix"
STEAMOS_FIX_SCRIPT = "patch-driver.sh"
STEAMOS_CU_REVIEWED_COMMIT = EXTERNAL_TOOLS["cu_manager_steamos"].reviewed_revision
STANDARD_CU_REVIEWED_COMMIT = EXTERNAL_TOOLS["cu_manager_standard"].reviewed_revision
STEAMOS_SMU_OC_REVIEWED_COMMIT = EXTERNAL_TOOLS["cpu_smu_oc"].reviewed_revision
STEAMOS_CORE_UNLOCK_REVIEWED_COMMIT = EXTERNAL_TOOLS["core_unlock"].reviewed_revision
STEAMOS_CYAN_REVIEWED_COMMIT = EXTERNAL_TOOLS["cyan_smu"].reviewed_revision
# Retain the former SteamOS-specific spelling for callers that still import it.
# The executable release is now fixed on every supported distribution.
STEAMOS_CYAN_REVIEWED_RELEASE = CYAN_REVIEWED_RELEASE
OBERON_REPOSITORY = EXTERNAL_TOOLS["oberon_governor"].upstream
OBERON_REVIEWED_COMMIT = EXTERNAL_TOOLS["oberon_governor"].reviewed_revision
OBERON_YAML_CPP_REVIEWED_COMMIT = "f7320141120f720aecc4c32be25586e7da9eb978"
OBERON_DIRECTORY = "oberon-governor"
