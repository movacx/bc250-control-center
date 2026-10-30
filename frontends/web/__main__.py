from __future__ import annotations

import sys

from frontends.web.server import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
