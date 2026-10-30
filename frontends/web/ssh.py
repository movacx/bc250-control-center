"""OpenSSH to this board, isolated per browser. No shell endpoint or saved password."""

from __future__ import annotations

import errno
import json
import os
import queue
import select
import shlex
import shutil
import tempfile
import termios
import threading
import time
from pathlib import Path
from subprocess import TimeoutExpired

from bc250cc.application.system import web_access
from bc250cc.application.system.privacy import redact_machine
from frontends.tui.console import Console
from frontends.web.ssh_worker import PREFIX

IDLE_SECONDS = 15 * 60


class SSHSession:
    def __init__(self) -> None:
        target = web_access.ssh_target()
        self.console = Console("SSH")
        self.ready = False
        self.closed = False
        self.last_used = time.monotonic()
        self._rpc_lock = threading.Lock()
        self._responses: queue.Queue = queue.Queue()
        self._counter = 0
        self._directory = tempfile.TemporaryDirectory(prefix="bc250-web-ssh-")
        known = Path(self._directory.name) / "known_hosts"
        known.write_text(target["known_hosts"], encoding="utf-8")
        known.chmod(0o600)
        command = (f"stty -echo; cd {shlex.quote(target['root'])} && exec env "
                   f"PYTHONPATH={shlex.quote(target['pythonpath'])} BC250_TERMINAL_AUTH=1 "
                   f"{shlex.quote(target['python'])} -u -m frontends.web.ssh_worker")
        argv = [shutil.which("ssh") or "ssh", "-F", "/dev/null", "-tt", "-e", "none",
                "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}",
                "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
                "-o", "NumberOfPasswordPrompts=3", "-o", "ForwardAgent=no",
                "-o", "ClearAllForwardings=yes", "-p", str(target["port"]),
                "-l", target["user"], "127.0.0.1", command]
        try:
            self.console.process, self.console.master = self.console._spawn(argv)
        except BaseException:
            self._directory.cleanup()
            raise
        threading.Thread(target=self._read, name="bc250-web-ssh", daemon=True).start()

    def _read(self) -> None:
        pending = b""
        master, process = self.console.master, self.console.process
        try:
            while not self.closed and time.monotonic() - self.last_used < IDLE_SECONDS:
                readable, _, _ = select.select([master], [], [], .2)
                if not readable:
                    if process.poll() is not None:
                        break
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                if not self.ready:
                    self.console._feed(chunk)
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    offset = line.find(PREFIX.encode())
                    if offset < 0:
                        continue
                    try:
                        message = json.loads(line[offset + len(PREFIX):])
                    except ValueError:
                        continue
                    if message.get("event") == "ready":
                        self.ready = True
                    elif "id" in message:
                        self._responses.put(message)
                if len(pending) > 2 * 1024 * 1024:
                    break
        finally:
            self.closed, self.ready = True, False
            self.console.master = None
            os.close(master)
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except TimeoutExpired:
                process.kill()
                process.wait()
            self._directory.cleanup()
            self._responses.put({"id": None, "result": {"ok": False, "error": "SSH disconnected"}})

    def request(self, op: str, **values) -> dict:
        with self._rpc_lock:
            if not self.ready or self.closed:
                return {"ok": False, "error": "SSH disconnected"}
            self.last_used = time.monotonic()
            self._counter += 1
            self.console.send((json.dumps({"id": self._counter, "op": op, **values}) + "\n").encode())
            try:
                while True:
                    answer = self._responses.get(timeout=15)
                    if answer["id"] in (None, self._counter):
                        return answer["result"]
            except queue.Empty:
                self.close()
                return {"ok": False, "error": "SSH disconnected"}

    def login_input(self, text: str) -> bool:
        self.last_used = time.monotonic()
        return not self.ready and not self.closed and self.password_prompt() and self.console.send(text.encode() + b"\n")

    def password_prompt(self) -> bool:
        try:
            return self.console.master is not None and not bool(termios.tcgetattr(self.console.master)[3] & termios.ECHO)
        except (OSError, termios.error):
            return False

    def status(self) -> dict:
        lines = self.console.view(20)[0]
        return {"ready": self.ready, "closed": self.closed,
                "prompt": not self.ready and self.password_prompt(),
                "text": redact_machine("\n".join("".join(run[0] for run in line).rstrip() for line in lines))}

    def close(self) -> None:
        if self.closed:
            return
        if self.ready:
            self.console.send(b'{"op":"close"}\n')
            try:
                self.console.process.wait(timeout=2)
            except TimeoutExpired:
                self.closed = True
        self.closed = True
        if self.console.process.poll() is None:
            self.console.process.terminate()
