"""Exercise the real OpenSSH transport against an isolated, unprivileged sshd."""
from __future__ import annotations

import os
import pwd
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bc250cc.application.system import web_access
from frontends.web.ssh import SSHSession

ROOT = Path(__file__).resolve().parents[2]


def wait_for(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    return None


def test_real_ssh_worker_rejects_arbitrary_actions_and_keeps_the_job_channel(tmp_path, monkeypatch):
    binaries = {name: shutil.which(name) for name in ("sshd", "ssh", "ssh-agent", "ssh-add", "ssh-keygen")}
    if not all(binaries.values()):
        pytest.skip("The isolated OpenSSH integration needs openssh-server and openssh-clients")
    for key in ("host", "client"):
        subprocess.run([binaries["ssh-keygen"], "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / key)], check=True)
    authorized = tmp_path / "authorized_keys"
    authorized.write_bytes((tmp_path / "client.pub").read_bytes())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = tmp_path / "sshd_config"
    config.write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {tmp_path / 'host'}\n"
                      f"AuthorizedKeysFile {authorized}\nPidFile {tmp_path / 'sshd.pid'}\n"
                      "UsePAM no\nStrictModes no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n"
                      "PermitRootLogin yes\nLogLevel QUIET\n")
    daemon = subprocess.Popen([binaries["sshd"], "-D", "-e", "-f", str(config)], stderr=subprocess.PIPE)
    agent = None
    session = None
    try:
        time.sleep(.2)
        if daemon.poll() is not None:
            message = daemon.stderr.read().decode(errors="replace")
            pytest.skip("Isolated sshd unavailable: " + message[:200])
        response = subprocess.run([binaries["ssh-agent"], "-a", str(tmp_path / "agent"), "-s"], check=True, capture_output=True, text=True).stdout
        agent = int(re.search(r"SSH_AGENT_PID=(\d+)", response)[1])
        monkeypatch.setenv("SSH_AUTH_SOCK", str(tmp_path / "agent"))
        subprocess.run([binaries["ssh-add"], str(tmp_path / "client")], check=True, capture_output=True)
        fields = (tmp_path / "host.pub").read_text().split()
        target = {"user": pwd.getpwuid(os.getuid()).pw_name, "port": port,
                  "known_hosts": f"[127.0.0.1]:{port} {fields[0]} {fields[1]}\n",
                  "root": str(ROOT), "pythonpath": f"{ROOT / 'src'}:{ROOT}", "python": sys.executable}
        monkeypatch.setattr(web_access, "ssh_target", lambda: target)
        session = SSHSession()
        assert wait_for(lambda: session.ready or session.closed), session.status()
        assert session.ready, session.status()
        assert session.login_input("must never be sent after authentication") is False
        assert session.request("action", action="exec", params={"command": "id"})["ok"] is False
        assert session.request("action", action="gpu.range", params={"min": 500, "max": 2400})["ok"] is False
        result = session.request("action", action="gpu.status", title="read-only test")
        assert result["ok"] is True
        assert wait_for(lambda: session.request("job").get("done")), session.status()
        session.close()
        assert wait_for(lambda: session.closed)
    finally:
        if session:
            session.close()
        daemon.terminate()
        daemon.wait(timeout=5)
        if agent:
            os.kill(agent, 15)
