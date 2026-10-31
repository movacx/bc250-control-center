from __future__ import annotations

import os
import sys

from bc250cc.application.system.web_access import (
    launch_command,
    require_supported_version,
)
from bc250cc.shared.errors import ActionNeeded


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--help" in arguments or "-h" in arguments:
        from frontends.web.arguments import argument_parser

        argument_parser().parse_args(arguments)
        return 0
    try:
        require_supported_version()
    except ActionNeeded:
        # The public CLI uses the same isolated runtime as Remote access.
        # Exec preserves flags and signals; never start a second server here.
        try:
            command = launch_command()
        except ActionNeeded as error:
            print(str(error), file=sys.stderr)
            return 2
        os.execv(command[0], [*command, *arguments])
    from frontends.web.server import main as serve

    return serve(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
