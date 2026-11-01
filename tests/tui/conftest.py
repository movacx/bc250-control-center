"""Keep remote ownership and SSH tests isolated from the owner's actual session."""
from copy import deepcopy

import pytest


@pytest.fixture(autouse=True)
def isolated_remote_access(monkeypatch):
    from bc250cc.application.system import remote_access, web_access

    web = {"running": False, "key": "TEST-TEST", "port": 8250, "lan": False,
           "local_url": "https://127.0.0.1:8250", "devices": [], "autostart": {"supported": False}}
    ssh = {"active": False, "enabled": False, "supported": False, "unit": "", "addresses": []}
    monkeypatch.setattr(web_access, "status", lambda: deepcopy(web))
    monkeypatch.setattr(remote_access, "status", lambda: deepcopy(ssh))
    for name in ("start", "stop", "configure", "set_autostart", "set_control", "revoke", "revoke_all", "set_lifetime"):
        monkeypatch.setattr(web_access, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(web_access, "access_key", lambda **kwargs: "TEST-TEST")
    monkeypatch.setattr(remote_access, "configure", lambda **kwargs: None)
    return web, ssh
