import runpy
from pathlib import Path

from bc250cc.infrastructure.core_unlock_trust import (
    REVIEWED_REVISION,
    REVIEWED_SCRIPT_SHA256,
)
from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-core-unlock-helper"


def test_packaged_helper_and_unprivileged_ui_share_exact_trust_anchors():
    namespace = runpy.run_path(str(HELPER))
    assert namespace["REVIEWED_REVISION"] == REVIEWED_REVISION
    assert namespace["REVIEWED_SCRIPT_SHA256"] == REVIEWED_SCRIPT_SHA256
    assert EXTERNAL_TOOLS["core_unlock"].reviewed_revision == REVIEWED_REVISION

