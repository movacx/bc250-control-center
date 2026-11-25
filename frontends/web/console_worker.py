"""Private tty protocol between the web server and the user's own session.

The worker stops reading requests while an action owns the terminal. Native
sudo can therefore read /dev/tty without competing with a JSON reader.
"""
from __future__ import annotations

import json
import os
import secrets
import signal
import sys
import termios

PREFIX = "\x1eBC250_RPC "


def reply(value: dict) -> None:
    sys.stdout.write(PREFIX + json.dumps(value, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def preload() -> None:
    """Import what every action needs, so that starting one costs a fork and not a new interpreter."""
    try:
        from bc250cc.application import ApplicationContainer
        from frontends.web import action_worker  # noqa: F401

        ApplicationContainer.production()
    except Exception:  # noqa: BLE001 - the action itself reports what is wrong
        return


def run_action(action: dict) -> int:
    """One action in a child of its own: same tty, same user, and a Ctrl+C ends only it."""
    child = os.fork()
    if child == 0:
        status = 1
        try:
            signal.signal(signal.SIGINT, signal.default_int_handler)
            sys.stdin = open(0, encoding="utf-8", closefd=False)  # noqa: SIM115 - nothing read ahead by the parent
            from frontends.web import action_worker

            status = action_worker.run(json.dumps(action, ensure_ascii=True))
        except KeyboardInterrupt:
            status = 130
        except SystemExit as error:
            status = error.code if isinstance(error.code, int) else 1
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(int(status) & 0xFF)
    _pid, ended = os.waitpid(child, 0)
    return os.waitstatus_to_exitcode(ended)


def main() -> None:
    terminal = termios.tcgetattr(0)
    terminal[3] &= ~termios.ECHO
    termios.tcsetattr(0, termios.TCSANOW, terminal)
    token = secrets.token_hex(32)
    reply({"event": "ready", "token": token})
    preload()
    while True:
        try:
            line = sys.stdin.buffer.readline(65537)
            if not line or len(line) > 65536:
                break
            request = json.loads(line)
            # Late tty input must never become a new RPC when an action ends.
            # This token stays inside the transport, outside browser responses.
            if not isinstance(request, dict) or request.get("token") != token:
                continue
            if request.get("op") == "close":
                break
            if request.get("op") != "action":
                reply({"id": request.get("id"), "result": {"ok": False, "error": "Invalid operation"}})
                continue
            # Caught SIGINT resets to default in the exec'd child; this reader
            # survives cancelling that child and can serve the next action.
            previous = signal.signal(signal.SIGINT, lambda *_: None)
            try:
                action = {key: request[key] for key in ("action", "params", "confirmed", "language", "title")
                          if key in request}
                status = run_action(action)
            finally:
                signal.signal(signal.SIGINT, previous)
                termios.tcsetattr(0, termios.TCSANOW, terminal)
            reply({"id": request.get("id"), "result": {"ok": status == 0, "exit_code": status}})
        except KeyboardInterrupt:
            continue
        except (ValueError, OSError):
            break


if __name__ == "__main__":
    main()
