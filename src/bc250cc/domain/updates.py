"""Deciding whether a published version is newer than the installed one.

Pure arithmetic on version strings, kept away from the code that fetches them
so the comparison can be tested without a network and the fetch cannot smuggle
policy in with it.

The rule is deliberately strict about what counts as a version. Whatever comes
back from the network is untrusted text: a proxy error page, a rate-limit
notice, or a repository whose ``VERSION`` file someone is mid-way through
editing. Anything this module cannot read as a plain dotted release is treated
as "no answer", which shows the user nothing — never a badge, never a warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A release is digits and dots, optionally announced with a leading ``v``.
# Nothing else: no ranges, no build metadata, no pre-release suffixes, because
# this project has never published one and accepting them would mean deciding
# how they order.
_RELEASE_RE = re.compile(r"^v?(\d{1,5}(?:\.\d{1,5}){0,3})$")

# Enough for "10.20.30.40" plus a newline. A published VERSION file is tiny;
# refusing a large one is how a fetch that landed on the wrong page fails
# closed instead of being parsed.
MAX_VERSION_TEXT_BYTES = 64


def parse_version(text: object) -> tuple[int, ...] | None:
    """Read a release string, or return ``None`` if it is not one."""
    if not isinstance(text, str):
        return None
    candidate = text.strip()
    if not candidate or len(candidate.encode("utf-8", "ignore")) > MAX_VERSION_TEXT_BYTES:
        return None
    match = _RELEASE_RE.match(candidate)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _padded(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """``1.19`` and ``1.19.0`` name the same release."""
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def is_newer(published: object, installed: object) -> bool:
    """Is ``published`` a release after ``installed``?

    False whenever either side cannot be read. A development checkout reports
    its version as ``development``, which is not a release — so a developer is
    never told to update to the file they are editing.
    """
    new = parse_version(published)
    current = parse_version(installed)
    if new is None or current is None:
        return False
    new, current = _padded(new, current)
    return new > current


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    """What a check concluded, and nothing about how it was performed."""

    installed: str
    published: str = ""
    checked_at_unix: float = 0.0
    # Separate from ``published`` being empty: a check that could not reach the
    # network is not the same as one that found nothing newer, and only the
    # second means "you are up to date".
    reachable: bool = False

    @property
    def update_available(self) -> bool:
        return self.reachable and is_newer(self.published, self.installed)

    @property
    def summary(self) -> str:
        """One short line for a tooltip; wording lives in the interface."""
        if not self.reachable:
            return ""
        return self.published if self.update_available else ""
