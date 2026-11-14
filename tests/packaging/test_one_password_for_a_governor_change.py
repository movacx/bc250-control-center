"""Changing the GPU range asked for the password twice.

Applying a range edits the governor TOML (``governor-config``) and then
restarts the service (``service-control``). Those are two polkit actions, and a
kept authorization only covers the action that asked for it, so polkit
prompted once for each. Each action now implies the other: authenticating for
either one covers the pair.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

POLICY = (
    Path(__file__).resolve().parents[2]
    / "privileged/policies/io.github.movacx.bc250-control-center.policy"
)
PREFIX = "io.github.movacx.bc250-control-center."
IMPLY = "org.freedesktop.policykit.imply"


def _implied(action_id):
    for action in ET.parse(POLICY).getroot().iter("action"):
        if action.get("id") == PREFIX + action_id:
            return {
                token
                for node in action.iter("annotate")
                if node.get("key") == IMPLY
                for token in (node.text or "").split()
            }
    raise AssertionError(f"{action_id} is not in the policy")


def test_config_and_restart_share_one_authentication():
    assert PREFIX + "service-control" in _implied("governor-config")
    assert PREFIX + "governor-config" in _implied("service-control")


def test_both_actions_keep_the_authorization_for_the_session():
    for action in ET.parse(POLICY).getroot().iter("action"):
        if action.get("id") in (PREFIX + "governor-config", PREFIX + "service-control"):
            assert action.findtext("defaults/allow_active") == "auth_admin_keep"
