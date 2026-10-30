"""Private tty protocol, shared by local and SSH user sessions.

The worker stops reading requests while an action owns the terminal. Native
sudo can therefore read /dev/tty without competing with a JSON reader.
"""
from __future__ import annotations

import json
import secrets
import signal
import subprocess
import sys
import termios

PREFIX = "\x1eBC250_RPC "


def reply(value: dict) -> None:
    sys.stdout.write(PREFIX + json.dumps(value, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main() -> None:
    terminal = termios.tcgetattr(0)
    terminal[3] &= ~termios.ECHO
    termios.tcsetattr(0, termios.TCSANOW, terminal)
    token = secrets.token_hex(32)
    reply({"event": "ready", "token": token})
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
                status = subprocess.call([sys.executable, "-u", "-m", "frontends.web.action_worker",
                                          json.dumps(action, ensure_ascii=True)])
            finally:
                signal.signal(signal.SIGINT, previous)
                termios.tcsetattr(0, termios.TCSANOW, terminal)
            reply({"id": request.get("id"), "result": {"ok": status == 0}})
        except KeyboardInterrupt:
            continue
        except (ValueError, OSError):
            break


if __name__ == "__main__":
    main()
