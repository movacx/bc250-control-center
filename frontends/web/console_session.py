"""A user tty opened for one validated action and closed as soon as it ends.

RPC carries validated action data; input reaches the tty only while that action
asks for it. There is no shell, no SSH, no root worker and no saved password:
closing the tty also ends whatever sudo remembered for it.
"""
from __future__ import annotations

import errno
import itertools
import json
import os
import queue
import re
import select
import sys
import threading
import time
from subprocess import TimeoutExpired

from bc250cc.application.system.privacy import redact_machine
from bc250cc.shared.operation_contract import OperationExit
from frontends.tui.console import Console
from frontends.web.actions import all_actions
from frontends.web.console_worker import PREFIX

IDLE_SECONDS = 15 * 60


#: Job numbers are unique across sessions: each action has a tty of its own.
_NUMBERS = itertools.count(1)


class ConsoleSession:
    def __init__(self) -> None:
        self.console = Console("Web")
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
        argv = [sys.executable, "-u", "-m", "frontends.web.console_worker"]
        self.console.process, self.console.master = self.console._spawn(argv)
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
                        status = result.get("exit_code")
                        if self.job_console.interrupted and status == -2:
                            status = OperationExit.CANCELLED
                        self.job_console.exit_status = status
                        self.job_console.finish(bool(result.get("ok")) or (self._monitor_stopped and status in (-2, OperationExit.CANCELLED)), result.get("error", ""))
                        self._active = False
                        self.ready, self.closed = False, True  # the tty is only open while it is needed
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
                    self.job_console.interrupted = True
                    self.console.interrupt()
            return {"ok": True}
        if op != "action" or values.get("action") not in all_actions():
            return {"ok": False, "error": "Invalid operation"}
        with self._state_lock:
            if not self.ready or self.closed or self._active:
                return {"ok": False, "error": "Terminal unavailable or busy"}
            self._job_id = next(_NUMBERS)
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
        action_needed = console.done.is_set() and console.exit_status == OperationExit.ACTION_NEEDED
        waiting = self._active and bool(re.search(r"BC250 Linux password:\s*$", text))
        interactive = self._active and (waiting or bool(re.search(r"[:?：？]\s*$|\[[yYnN/]+\]\s*$", text)))
        return {"id": self._job_id, "kind": getattr(self, "_kind", ""),
                "sample": getattr(self, "_sample", {}), "sample_age": time.monotonic() - getattr(self, "_sample_at", 0.0),
                "label": console.label, "done": console.done.is_set(),
                "ok": console.succeeded if console.done.is_set() else None,
                "message": redact_machine(text.strip()) if action_needed else "",
                "cancelled": console.done.is_set() and not console.succeeded and console.exit_status == OperationExit.CANCELLED,
                "action_needed": action_needed,
                "text": redact_machine(text), "waiting": waiting, "interactive": interactive}

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.console.process.poll() is None:
            # SIGHUP ends the tty session and native sudo timestamp context.
            self.console.process.terminate()
