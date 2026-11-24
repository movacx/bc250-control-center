"""sudo for a helper started from the terminal interface.

The helpers are started with pipes and the interface owns the terminal, so sudo
would have nowhere to ask. This file is both ends of the way out, and runs as
the ordinary user (only ``sudo`` itself becomes root):

* ``--serve SOCKET`` keeps a pseudo-terminal of the interface's console as its
  controlling terminal and starts each ``sudo`` there. sudo asks in the
  console, and remembers the password for that terminal as it always does.
* ``[NAME=value] -- PROGRAM...`` is what a service runs instead: it hands its
  three standard streams to the server and exits with the command's status.

Standard library only and no package imports: it is started by path.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import struct
import subprocess  # nosec B404
import sys
import threading

SOCKET_ENV = "BC250_SUDO_SOCKET"
#: Set on the console's own workflows: they already have a terminal to ask on.
CONSOLE_ENV = "BC250_CONSOLE_TTY"
PROMPT = "[sudo] Linux password: "
MAX_REQUEST = 1 << 20


def sudo_argv(arguments: list[str]) -> list[str]:
    sudo = shutil.which("sudo")
    if sudo is None:
        raise RuntimeError("sudo was not found. It is needed to authorize this action in the terminal.")
    return [sudo, "-p", PROMPT, *arguments]


def missing_password() -> str:
    """What to say when this account cannot answer sudo at all (SteamOS' deck, until its owner sets one)."""
    try:
        status = subprocess.run(["passwd", "-S"], capture_output=True, text=True, timeout=5, check=False).stdout.split()  # nosec B603 B607
        if len(status) < 2 or status[1] not in {"NP", "L", "LK", "NL"}:
            return ""
        if subprocess.run(sudo_argv(["-n", "true"]), capture_output=True, timeout=5, check=False).returncode == 0:  # nosec B603
            return ""  # sudo trusts it without one
    except (OSError, subprocess.SubprocessError):
        return ""
    return (f"ERROR: The {status[0]} account has no password yet, so sudo cannot authorize this change.\n"
            "Set one first: run passwd in a terminal, then try again.\n")


def _descends_from(pid: int, ancestor: int) -> bool:
    """``pid`` was started, directly or not, by ``ancestor``."""
    for _step in range(64):
        if pid == ancestor:
            return True
        if pid <= 1:
            return False
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
                pid = int(handle.read().rpartition(")")[2].split()[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def _answer(connection: socket.socket, owner: int) -> None:
    with connection:
        pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        # The password sudo remembers is for this interface's own actions only.
        if uid != os.getuid() or not _descends_from(pid, owner):
            return
        data, fds, _flags, _address = socket.recv_fds(connection, MAX_REQUEST, 3)
        try:
            request = json.loads(data)
            argv = sudo_argv([str(item) for item in request["argv"]])
            if len(fds) != 3:
                raise ValueError("three streams are needed")
            if problem := missing_password():
                os.write(fds[2], problem.encode())
                connection.sendall(b"77")
                return
            # A fresh interpreter rather than fork(): this process has threads.
            child = subprocess.Popen(  # nosec B603
                [sys.executable, "-I", __file__, "--front", *argv], stdin=fds[0], stdout=fds[1], stderr=fds[2],
                cwd=request.get("cwd") or "/", close_fds=True)
        finally:
            for descriptor in fds:
                os.close(descriptor)
        code = child.wait()
        connection.sendall(str(code if code >= 0 else 128 - code).encode())


def front(argv: list[str]) -> int:
    """Take the terminal, so its keyboard and Ctrl+C reach this command, and become it."""
    os.setpgid(0, 0)
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    terminal = os.open("/dev/tty", os.O_RDWR)
    os.tcsetpgrp(terminal, os.getpid())
    os.close(terminal)
    signal.signal(signal.SIGTTOU, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    os.execv(argv[0], argv)


def serve(path: str) -> int:
    owner = os.getppid()
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C is for the command in front
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, 0o600)
    server.listen(8)
    while True:
        connection, _address = server.accept()
        threading.Thread(target=_answer, args=(connection, owner), daemon=True).start()


def request(arguments: list[str]) -> int:
    if os.environ.get(CONSOLE_ENV) == "1":
        argv = sudo_argv(arguments)
        os.execv(argv[0], argv)
    path = os.environ.get(SOCKET_ENV, "")
    try:
        if os.isatty(0):  # the interface's own screen: sudo must not touch its modes
            os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(path)
            socket.send_fds(connection, [json.dumps({"argv": arguments, "cwd": os.getcwd()}).encode()], [0, 1, 2])
            os.close(0)
            answer = connection.recv(16)
        return int(answer)
    except (OSError, ValueError):
        print("Terminal authorization is unavailable.", file=sys.stderr)
        return 126


def main() -> int:
    arguments = sys.argv[1:]
    if len(arguments) == 2 and arguments[0] == "--serve":
        return serve(arguments[1])
    if arguments[:1] == ["--front"]:
        return front(arguments[1:])
    return request(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
