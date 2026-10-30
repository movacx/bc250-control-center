"""Private SSH stdio protocol. Only the web's validated actions can run here."""

from __future__ import annotations

import json
import os
import sys

from bc250cc.application import ApplicationContainer
from bc250cc.application.system.workflow_console import (
    TERMINAL_AUTH_ENV,
    set_translator,
)
from frontends.desktop.i18n import set_language, tr
from frontends.tui.runtime import Context, describe_error
from frontends.web.actions import ACTIONS, Invalid
from frontends.web.jobs import Jobs

PREFIX = "BC250_RPC "


def reply(value: dict) -> None:
    # Jobs redirect stdout to their console; the protocol must keep its own stream.
    sys.__stdout__.write(PREFIX + json.dumps(value, ensure_ascii=True, default=str) + "\n")
    sys.__stdout__.flush()


def main() -> None:
    os.environ[TERMINAL_AUTH_ENV] = "1"
    container = ApplicationContainer.production()
    ctx = Context(service=container.system_service, settings=container.settings_service,
                  activity=container.activity_service, platform=container.platform,
                  config=container.settings_service.read_local_config())
    jobs = Jobs()
    reply({"event": "ready"})
    while line := sys.stdin.buffer.readline(65537):
        if len(line) > 65536:
            break
        request = {}
        try:
            request = json.loads(line)
            op = request.get("op")
            if op == "action":
                set_language(request.get("language") or "en")
                set_translator(tr)
                build = ACTIONS.get(request.get("action"))
                if build is None:
                    raise Invalid("action")
                level, work = build(ctx, request.get("params") or {}, jobs.shell)
                if level and request.get("confirmed") is not True:
                    raise Invalid("confirmation")
                result = {"ok": True, "job": jobs.start(str(request.get("title", ""))[:80], work)}
            elif op == "job":
                result = jobs.view() or {"id": 0}
            elif op == "input":
                result = {"ok": jobs.send(str(request.get("text", ""))[:256])}
            elif op == "interrupt":
                jobs.interrupt()
                result = {"ok": True}
            elif op == "close":
                jobs.interrupt()
                break
            else:
                raise Invalid("operation")
            reply({"id": request.get("id"), "result": result})
        except Exception as error:
            reply({"id": request.get("id"), "result": {"ok": False, "error": describe_error(error)}})
    jobs.interrupt()


if __name__ == "__main__":
    main()
