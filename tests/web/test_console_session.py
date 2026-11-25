"""The tty an action runs in: opened for it, private, and closed when it ends."""
from __future__ import annotations

import sys
import time

import pytest

from frontends.web.console_session import ConsoleSession


def wait_for(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    return None


def test_tty_streams_prompts_without_echoing_input_and_closes_with_its_action(tmp_path, monkeypatch):
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
    script = ("import sys; from frontends.web import console_worker; "
              f"sys.executable={str(standin)!r}; console_worker.main()")
    monkeypatch.setattr(Console, "_spawn", lambda self, _argv: spawn(self, [sys.executable, "-u", "-c", script]))
    session = ConsoleSession()
    try:
        assert wait_for(lambda: session.ready)
        # Model text typed outside an action: even valid-looking JSON
        # cannot impersonate transport RPCs.
        session.console.send(b'{"op":"action","action":"gpu.status","confirmed":true}\n')
        time.sleep(.1)
        assert session.ready and not session.closed
        assert session.request("action", action="exec", params={"command": "id"})["ok"] is False
        assert session.request("action", action="gpu.status", title="no hardware")["ok"]
        assert wait_for(lambda: session.view().get("waiting"))
        assert session.request("input", text="dummy-secret")["ok"]
        assert wait_for(lambda: session.view().get("done"))
        job = session.view()
        assert job["ok"] and "input accepted" in job["text"]
        assert "dummy-secret" not in job["text"]
        assert "BC250_RPC" not in job["text"]
        assert session.request("input", text="never sent after completion")["ok"] is False
        assert session.closed and not session.ready
        assert wait_for(lambda: session.console.process.poll() is not None)
        assert session.request("action", action="gpu.status")["ok"] is False
        assert session.view()["id"] == job["id"], "its result can still be read"
        again = ConsoleSession()
        try:
            assert wait_for(lambda: again.ready)
            assert again.request("action", action="gpu.status")["job"] > job["id"]
            assert wait_for(lambda: again.view().get("waiting"))
            again.request("interrupt")
            assert wait_for(lambda: again.view().get("done"))
            assert again.view()["cancelled"] and not again.view()["ok"]
        finally:
            again.close()
    finally:
        session.close()


def test_no_program_an_action_runs_can_offer_a_shell():
    from frontends.web.action_worker import SIN_PROGRAMAS_INTERACTIVOS as entorno
    assert entorno["LESSSECURE"] == "1" and entorno["PAGER"] == "cat"
    assert all(entorno[name] == "/bin/false" for name in ("EDITOR", "VISUAL", "SUDO_EDITOR", "SYSTEMD_EDITOR"))


@pytest.mark.parametrize("stop_exit", [None, 42])
def test_memory_helper_streams_samples_and_only_clean_interrupts_count_as_a_normal_stop(tmp_path, monkeypatch, stop_exit):
    from frontends.tui.console import Console
    child = tmp_path / "memory-child"
    handler = "" if stop_exit is None else f"import signal,sys;signal.signal(signal.SIGINT,lambda *_:sys.exit({stop_exit}))\n"
    child.write_text(f"#!{sys.executable}\nimport json,time\n" + handler + "print(json.dumps({'chips':[{'chip':0,'temperature_c':52.5}],'average_c':52.5}),flush=True)\ntime.sleep(30)\n")
    child.chmod(0o700)
    spawn = Console._spawn
    script = f"import sys;from frontends.web import console_worker;sys.executable={str(child)!r};console_worker.main()"
    monkeypatch.setattr(Console, "_spawn", lambda self, _argv: spawn(self, [sys.executable, "-u", "-c", script]))
    session = ConsoleSession()
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
