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
        # Validation happens again in the unprivileged child before any service call.
        assert session.request("action", action="gpu.profile", params={"min": 500, "max": 2400})["ok"] is True
        assert wait_for(lambda: session.request("job").get("done"))
        assert session.request("job")["ok"] is False
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


def test_local_persistent_tty_streams_prompts_without_echoing_input(tmp_path, monkeypatch):
    """Use the real protocol/pty, but a harmless stand-in for hardware services."""
    from frontends.tui.console import Console
    standin = tmp_path / "action-child"
    standin.write_text(f"#!{sys.executable}\n" + '''import sys
print("BC250 Linux password: ", end="", flush=True)
with open("/dev/tty") as terminal:
    value = terminal.readline().strip()
print("\\ninput accepted" if value == "dummy-secret" else "\\ninput refused", flush=True)
raise SystemExit(0 if value == "dummy-secret" else 1)
''')
    standin.chmod(0o700)
    spawn = Console._spawn
    script = ("import sys; from frontends.web import ssh_worker; "
              f"sys.executable={str(standin)!r}; ssh_worker.main()")
    monkeypatch.setattr(Console, "_spawn", lambda self, _argv: spawn(self, [sys.executable, "-u", "-c", script]))
    session = SSHSession(local=True)
    try:
        assert wait_for(lambda: session.ready)
        pid = session.console.process.pid
        # Model text arriving just after a job exits: even valid-looking JSON
        # typed in the terminal cannot impersonate transport RPCs.
        session.console.send(b'{"op":"action","action":"gpu.status","confirmed":true}\n')
        time.sleep(.1)
        assert session.ready and not session.closed
        for _ in range(2):
            assert session.request("action", action="gpu.status", title="no hardware")["ok"]
            assert wait_for(lambda: session.view().get("waiting"))
            assert session.request("input", text="dummy-secret")["ok"]
            assert wait_for(lambda: session.view().get("done"))
            job = session.view()
            assert job["ok"] and "input accepted" in job["text"]
            assert "dummy-secret" not in job["text"]
            assert "BC250_RPC" not in job["text"]
            assert session.request("input", text="never sent after completion")["ok"] is False
            assert session.console.process.pid == pid
        session.request("action", action="gpu.status")
        assert wait_for(lambda: session.view().get("waiting"))
        session.request("interrupt")
        assert wait_for(lambda: session.view().get("done"))
        assert not session.view()["ok"]
        assert session.ready and not session.closed
    finally:
        session.close()


@pytest.mark.parametrize("stop_exit", [None, 42])
def test_memory_helper_streams_samples_and_only_clean_interrupts_count_as_a_normal_stop(tmp_path, monkeypatch, stop_exit):
    from frontends.tui.console import Console
    child = tmp_path / "memory-child"
    handler = "" if stop_exit is None else f"import signal,sys;signal.signal(signal.SIGINT,lambda *_:sys.exit({stop_exit}))\n"
    child.write_text(f"#!{sys.executable}\nimport json,time\n" + handler + "print(json.dumps({'chips':[{'chip':0,'temperature_c':52.5}],'average_c':52.5}),flush=True)\ntime.sleep(30)\n")
    child.chmod(0o700)
    spawn = Console._spawn
    script = f"import sys;from frontends.web import ssh_worker;sys.executable={str(child)!r};ssh_worker.main()"
    monkeypatch.setattr(Console, "_spawn", lambda self, _argv: spawn(self, [sys.executable, "-u", "-c", script]))
    session = SSHSession(local=True)
    try:
        assert wait_for(lambda: session.ready)
        assert session.request("action", action="gddr6.monitor", confirmed=True)["ok"]
        sample = wait_for(lambda: session.view().get("sample"))
        assert sample["average_c"] == 52.5
        session.request("interrupt")
        assert wait_for(lambda: session.view().get("done"))
        assert session.view()["ok"] is (stop_exit is None)
    finally:
        session.close()
