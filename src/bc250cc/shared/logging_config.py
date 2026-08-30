from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    """Configure one predictable log format for GUI and backend diagnostics."""
    debug_enabled = os.environ.get("BC250_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    logging.basicConfig(
        level=logging.DEBUG if debug_enabled else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
