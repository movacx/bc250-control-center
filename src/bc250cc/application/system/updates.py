"""New releases, as an interface asks about them and installs them.

The same rules as the desktop's updater: the published version is cached for
hours, and an installation is updated only through the plan that matches how
it was installed (package, AUR, source archive, or a manual note).
"""

from bc250cc.infrastructure.install_source import detect_install_source
from bc250cc.infrastructure.release_check import RELEASES_PAGE_URL, check_for_update
from bc250cc.infrastructure.self_update import (
           UpdateError,
           download_asset,
           fetch_latest_release,
           plan_update,
)

__all__ = ["RELEASES_PAGE_URL", "UpdateError", "check_for_update", "detect_install_source", "download_asset",
           "fetch_latest_release", "plan_update"]
