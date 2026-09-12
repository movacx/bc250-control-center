"""How this copy of the application got here, so an update can be suggested.

"There is a newer version" is only half an answer. What to *do* about it
depends entirely on how the running copy was installed, and telling an AUR user
to download a release tarball would undo their package manager's bookkeeping.

The question is answered by asking the package manager which package owns the
file we are executing from — not by guessing from a path, because every
installer here can be pointed at a different prefix. Only read-only queries are
used, each bounded in time, and every failure resolves to
``UpdateChannel.RELEASE``: sending someone to the releases page is correct for
a source install and merely unhelpful for anyone else, which is the right way
for this to be wrong.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SECONDS = 5.0

# The AUR recipe builds ``-git``; ``build-local-pkg.sh`` builds the plain name.
# Both are foreign to pacman, so ``-Qm`` cannot separate them and the name is
# what does: a locally built package is updated by building it again, which is
# the releases path, while the AUR one is updated by an AUR helper.
AUR_PACKAGE = "bc250-control-center-git"
PACKAGE_NAME = "bc250-control-center"

# In preference order. Whichever is installed is the one named in the hint.
AUR_HELPERS = ("paru", "yay", "pikaur", "trizen")


class UpdateChannel(Enum):
    """Where an update should come from for this install."""

    AUR = "aur"
    #: A distribution package built from this project (rpm, deb, local pacman).
    PACKAGE = "package"
    #: A source or script install, and the fallback whenever nothing is known.
    RELEASE = "release"


@dataclass(frozen=True, slots=True)
class InstallSource:
    channel: UpdateChannel
    package: str = ""
    manager: str = ""
    helper: str = ""

    @property
    def command(self) -> str:
        """The command that updates this install, or ``""`` if there isn't one."""
        if self.channel is UpdateChannel.AUR:
            helper = self.helper or AUR_HELPERS[0]
            return f"{helper} -Syu {self.package or AUR_PACKAGE}"
        return ""


def _run(argv: list[str]) -> tuple[int, str]:
    """A bounded, read-only query. Never raises."""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECONDS,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.debug("Install-source query %s failed: %s", argv[0], error)
        return 1, ""
    return result.returncode, (result.stdout or "").strip()


def _own_path() -> Path:
    """A file that belongs to this installation, whatever the prefix."""
    return Path(__file__).resolve()


def _available_aur_helper() -> str:
    for helper in AUR_HELPERS:
        if shutil.which(helper):
            return helper
    return ""


def _pacman_owner(path: Path) -> str:
    """The pacman package owning ``path``, or ``""``."""
    if not shutil.which("pacman"):
        return ""
    code, output = _run(["pacman", "-Qoq", str(path)])
    if code != 0 or not output:
        return ""
    names = [line.strip() for line in output.splitlines() if line.strip()]
    # A directory is owned by every package that puts a file in it, so more
    # than one name means the question was ambiguous, not that the first answer
    # is right. ``/usr/bin`` alone reports hundreds.
    if len(names) != 1:
        return ""
    return names[0]


def detect_install_source(*, path: Path | None = None) -> InstallSource:
    """Work out where an update for this copy should come from.

    Resolves to ``RELEASE`` for anything unrecognised, including a development
    checkout and a script install, because that page is always a correct place
    to look and never breaks a package manager's records.
    """
    target = path if path is not None else _own_path()
    # Only a regular file identifies one package; see ``_pacman_owner``.
    try:
        if not target.is_file():
            return InstallSource(UpdateChannel.RELEASE)
    except OSError:
        return InstallSource(UpdateChannel.RELEASE)

    owner = _pacman_owner(target)
    if owner:
        if owner == AUR_PACKAGE or owner.endswith("-git"):
            return InstallSource(
                UpdateChannel.AUR,
                package=owner,
                manager="pacman",
                helper=_available_aur_helper(),
            )
        return InstallSource(UpdateChannel.PACKAGE, package=owner, manager="pacman")

    if shutil.which("rpm"):
        code, output = _run(["rpm", "-qf", "--queryformat", "%{NAME}", str(target)])
        if code == 0 and output and " " not in output:
            return InstallSource(UpdateChannel.PACKAGE, package=output, manager="rpm")

    if shutil.which("dpkg-query"):
        code, output = _run(["dpkg-query", "-S", str(target)])
        if code == 0 and ":" in output:
            package = output.split(":", 1)[0].strip()
            if package:
                return InstallSource(
                    UpdateChannel.PACKAGE, package=package, manager="dpkg"
                )

    return InstallSource(UpdateChannel.RELEASE)
