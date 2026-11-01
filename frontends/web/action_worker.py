"""Run one validated action as the ordinary user on the session's inherited tty.

Only the existing installed helpers elevate via native sudo. This module must
never be run as root. Passwords belong to sudo's /dev/tty, never to this protocol.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from bc250cc.application import ApplicationContainer
from bc250cc.application.system.workflow_console import (
    TERMINAL_AUTH_ENV,
    WEB_SUDO_AUTH_ENV,
    TerminalLaunchResult,
    set_embedded_terminal_launcher,
    set_translator,
)
from frontends.desktop.i18n import set_language, tr
from frontends.tui.runtime import Context, describe_error, describe_result
from frontends.web.actions import ACTIONS, Invalid


class InheritedTerminal:
    """Synchronous workflows: no nested pty, GUI agent or external terminal."""

    writes_transcript = False
    inherit_tty = True

    def __init__(self):
        self.failed = False

    def run(self, argv):
        try:
            status = subprocess.call(argv)
        except OSError as error:
            print(describe_error(error), flush=True)
            status = 127
        self.failed |= status != 0
        return status

    def __call__(self, request):
        self.run(list(request.argv))
        # A launched workflow must never fall back to another terminal and run
        # again after an error. The child exit status reports failure instead.
        return TerminalLaunchResult(terminal="bc250-web", title=request.title, pid=None,
                                    status_file=request.status_file, log_file=request.log_file)

    def shell(self, command):
        if self.run(list(command) if isinstance(command, (list, tuple)) else ["bash", "-c", command]):
            raise RuntimeError("The hardware workflow did not complete successfully.")
        return ""


def main() -> int:
    if os.geteuid() == 0:
        print("The web action worker must run as the ordinary Linux user.", flush=True)
        return 1
    os.environ[TERMINAL_AUTH_ENV] = "1"
    os.environ[WEB_SUDO_AUTH_ENV] = "1"
    terminal = InheritedTerminal()
    set_embedded_terminal_launcher(terminal)
    try:
        request = json.loads(sys.argv[1])
        set_language(request.get("language") or "en")
        set_translator(tr)
        container = ApplicationContainer.production()
        ctx = Context(service=container.system_service, settings=container.settings_service,
                      activity=container.activity_service, platform=container.platform,
                      config=container.settings_service.read_local_config())
        build = ACTIONS.get(request.get("action"))
        if build is None or not isinstance(request.get("params", {}), dict):
            raise Invalid("action")
        level, work = build(ctx, request.get("params") or {}, terminal.shell)
        if level and request.get("confirmed") is not True:
            raise Invalid("confirmation")
        result = work()
        if terminal.failed:
            return 1
        message = describe_result(result)
        if message:
            print(message, flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        print(describe_error(error) if isinstance(error, Exception) else "Operation cancelled.", flush=True)
        return 130 if isinstance(error, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
