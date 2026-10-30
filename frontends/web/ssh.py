"""Persistent user tty per browser, optionally reached through pinned OpenSSH.

RPC carries validated action data; input is sent directly to the active tty.
No shell endpoint, root worker, saved password or sudoers changes.
"""
from __future__ import annotations

import errno
import json
import os
import queue
import re
import select
import shlex
import shutil
import sys
import tempfile
import termios
import threading
import time
from pathlib import Path
from subprocess import TimeoutExpired

from bc250cc.application.system import web_access
from bc250cc.application.system.privacy import redact_machine
from frontends.tui.console import Console
from frontends.web.actions import ACTIONS
from frontends.web.ssh_worker import PREFIX

IDLE_SECONDS = 15 * 60


class SSHSession:
    def __init__(self, *, local: bool = False) -> None:
        self.console = Console("Local" if local else "SSH")
        self.job_console: Console | None = None
        self.ready = False
        self.closed = False
        self.last_used = time.monotonic()
        self._rpc_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._responses: queue.Queue = queue.Queue()
        self._counter = 0
        self._token = ""
        self._job_id = 0
        self._active = False
        self._kind = ""
        self._sample = {}
        self._sample_at = 0.0
        self._sample_buffer = b""
        self._monitor_stopped = False
        self._directory = tempfile.TemporaryDirectory(prefix="bc250-web-tty-")
        if local:
            argv = [sys.executable, "-u", "-m", "frontends.web.ssh_worker"]
        else:
            target = web_access.ssh_target()
            known = Path(self._directory.name) / "known_hosts"
            known.write_text(target["known_hosts"], encoding="utf-8")
            known.chmod(0o600)
            command = (f"stty -echo; cd {shlex.quote(target['root'])} && exec env "
                       f"PYTHONPATH={shlex.quote(target['pythonpath'])} "
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
        threading.Thread(target=self._read, name="bc250-web-tty", daemon=True).start()

    def _feed(self, data: bytes) -> None:
        target = self.job_console if self._active else self.console
        if target is not None and data:
            target._feed(data)
        if self._active and self._kind == "gddr6.monitor":
            self._sample_buffer += data
            while b"\n" in self._sample_buffer:
                line, self._sample_buffer = self._sample_buffer.split(b"\n", 1)
                try:
                    sample = json.loads(line[line.find(b"{"):].strip())
                except ValueError:
                    continue
                if isinstance(sample, dict) and isinstance(sample.get("chips"), list):
                    self._sample, self._sample_at = sample, time.monotonic()
            if len(self._sample_buffer) > 65536:
                self._sample_buffer = b""

    def _read(self) -> None:
        pending = b""
        prefix = PREFIX.encode()
        master, process = self.console.master, self.console.process
        try:
            while not self.closed and (self._active or time.monotonic() - self.last_used < IDLE_SECONDS):
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
                pending += chunk
                while pending:
                    offset = pending.find(prefix)
                    if offset < 0:
                        # Keep a split frame prefix, but stream prompts without
                        # waiting for a newline (sudo prompts have none).
                        keep = next((n for n in range(min(len(pending), len(prefix) - 1), 0, -1)
                                     if pending.endswith(prefix[:n])), 0)
                        self._feed(pending[:-keep] if keep else pending)
                        pending = pending[-keep:] if keep else b""
                        break
                    self._feed(pending[:offset])
                    pending = pending[offset:]
                    if b"\n" not in pending:
                        break
                    line, pending = pending.split(b"\n", 1)
                    try:
                        message = json.loads(line[len(prefix):])
                    except ValueError:
                        continue
                    if message.get("event") == "ready":
                        self._token = message["token"]
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
            self._responses.put({"id": None, "result": {"ok": False, "error": "Terminal disconnected"}})

    def _execute(self, values: dict) -> None:
        with self._rpc_lock:
            self._counter += 1
            identifier = self._counter
            self.console.send((json.dumps({**values, "id": identifier, "op": "action", "token": self._token}) + "\n").encode())
            while True:
                try:
                    answer = self._responses.get(timeout=.5)
                except queue.Empty:
                    if not self.closed:
                        continue
                    answer = {"id": None, "result": {"ok": False}}
                if answer["id"] in (None, identifier):
                    result = answer["result"]
                    with self._state_lock:
                        self.job_console.finish(bool(result.get("ok")) or (self._monitor_stopped and result.get("exit_code") in (-2, 130)), result.get("error", ""))
                        self._active = False
                    break

    def request(self, op: str, **values) -> dict:
        self.last_used = time.monotonic()
        if op == "job":
            return self.view()
        if op == "input":
            text = str(values.get("text", ""))
            with self._state_lock:
                allowed = (self._active and self.view().get("interactive") and len(text) <= 256
                           and not any(ord(c) < 32 or ord(c) == 127 for c in text))
                return {"ok": bool(allowed and self.console.send(text.encode() + b"\n"))}
        if op == "interrupt":
            with self._state_lock:
                if self._active:
                    self._monitor_stopped = self._kind == "gddr6.monitor"
                    self.console.interrupt()
            return {"ok": True}
        if op != "action" or values.get("action") not in ACTIONS:
            return {"ok": False, "error": "Invalid operation"}
        with self._state_lock:
            if not self.ready or self.closed or self._active:
                return {"ok": False, "error": "Terminal unavailable or busy"}
            self._job_id += 1
            self._kind = values["action"]
            self._sample, self._sample_at, self._sample_buffer = {}, 0.0, b""
            self._monitor_stopped = False
            self.job_console = Console(str(values.get("title", ""))[:80], 24, 100)
            self._active = True
            threading.Thread(target=self._execute, args=(values,), name="bc250-web-action", daemon=True).start()
            return {"ok": True, "job": self._job_id}

    def view(self) -> dict:
        console = self.job_console
        if console is None:
            return {"id": 0}
        lines = console.view(240)[0]
        text = "\n".join("".join(run[0] for run in line).rstrip() for line in lines)
        waiting = self._active and bool(re.search(r"BC250 Linux password:\s*$", text))
        interactive = self._active and (waiting or bool(re.search(r"[:?：？]\s*$|\[[yYnN/]+\]\s*$", text)))
        return {"id": self._job_id, "kind": getattr(self, "_kind", ""),
                "sample": getattr(self, "_sample", {}), "sample_age": time.monotonic() - getattr(self, "_sample_at", 0.0),
                "label": console.label, "done": console.done.is_set(),
                "ok": console.succeeded if console.done.is_set() else None, "message": "",
                "text": redact_machine(text), "waiting": waiting, "interactive": interactive}

    def login_input(self, text: str) -> bool:
        self.last_used = time.monotonic()
        return (not self.ready and not self.closed and self.password_prompt()
                and self.console.send(text.encode() + b"\n"))

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
        self.closed = True
        if self.console.process.poll() is None:
            # SIGHUP ends the tty session and native sudo timestamp context.
            self.console.process.terminate()
