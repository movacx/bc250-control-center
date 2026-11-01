"""Read-only firewall diagnosis and explicit privileged LAN repair."""
import json
import subprocess

from bc250cc.infrastructure.system_setup import HELPER
from bc250cc.shared.errors import ActionNeeded


def inspect(port):
    try:
        if not HELPER.is_file() or '"web-firewall-status"' not in HELPER.read_text(encoding="utf-8"):
            return {"state": "update_helper", "repairable": False}
        result = subprocess.run([str(HELPER), "web-firewall-status", "--web-port", str(port)],
                                capture_output=True, text=True, timeout=45, check=False)
        if result.returncode:
            return {"state": "unknown", "repairable": False}
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else {"state": "unknown"}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"state": "unknown", "repairable": False}


def repair(port):
    if not HELPER.is_file() or '"web-firewall-repair"' not in HELPER.read_text(encoding="utf-8"):
        raise ActionNeeded("Update or reinstall Control Center to install the LAN firewall helper.")
    try:
        result = subprocess.run(["pkexec", str(HELPER), "web-firewall-repair", "--web-port", str(port)],
                                capture_output=True, text=True, timeout=240, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ActionNeeded("LAN firewall repair could not finish. Check its status before retrying.") from error
    if result.returncode:
        raise ActionNeeded(result.stderr.strip() or "LAN firewall repair was cancelled or failed.")
    return inspect(port)
