"""Update this installation to the latest published release.

The dashboard already knows when a newer version exists (``release_check``).
This module does the rest: it reads that release from GitHub, picks the one
package that matches how this copy was installed, downloads it with the
checksum GitHub publishes for it, and builds the one command that installs
it. The command runs in the application's terminal like every other
privileged workflow, so the password prompt, the output and the exit status
are the ones the user already knows.

The same rules as the version check, tightened for a file that gets
installed:

* **HTTPS only, one repository.** Redirects are followed only while they stay
  on https (GitHub hands downloads to its asset CDN).
* **Checksummed or refused.** A package is installed only when GitHub (or the
  release's ``SHA256SUMS.txt``) publishes its SHA-256, and only when the
  download matches it. The install command checks it again right before the
  package manager runs, so a file swapped in the cache meanwhile is refused.
* **The package manager decides.** pacman, dnf, rpm-ostree and APT install
  the package; nothing here copies files into place itself.
* **Never guess.** A development checkout, SteamOS' read-only image with a
  release package, or a release without a package for this system gets the
  release page instead of a best effort.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bc250cc.infrastructure.install_source import (
    AUR_PACKAGE,
    PACKAGE_NAME,
    InstallSource,
    UpdateChannel,
)
from bc250cc.infrastructure.persistence.config_paths import app_cache_dir
from bc250cc.infrastructure.release_check import RELEASES_PAGE_URL, USER_AGENT

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/movacx/bc250-control-center/releases/latest"
#: The release JSON is about 10 KiB; anything near this is not a release.
MAX_RELEASE_JSON_BYTES = 2 * 1024 * 1024
#: The largest package so far is 7 MiB; a download past this is refused.
MAX_PACKAGE_BYTES = 200 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10.0
DOWNLOAD_TIMEOUT_SECONDS = 30.0
CHUNK_BYTES = 64 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}")


class UpdateError(RuntimeError):
    """Something the dialog should say, in words, and stop at."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    size: int
    url: str
    sha256: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    title: str
    published_at: str
    notes: str
    page_url: str
    assets: tuple[ReleaseAsset, ...] = ()


@dataclass(frozen=True)
class UpdatePlan:
    """How this installation gets the release: which file, which command."""

    #: "package" (download and install a package), "aur" (rebuild with the
    #: AUR helper), "source" (the source archive and install-local.sh), or
    #: "manual" (the release page; nothing is run).
    kind: str
    asset: ReleaseAsset | None = None
    manager: str = ""
    helper: str = ""
    reboot_required: bool = False
    #: Why the plan is manual, for the dialog.
    reason: str = ""
    #: What the dialog says the plan will do.
    summary: str = ""
    steps: tuple[str, ...] = field(default=())

    @property
    def downloads(self) -> bool:
        return self.kind in {"package", "source"} and self.asset is not None


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        if not str(newurl).lower().startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(_HttpsOnlyRedirect)


def _version_from_tag(tag: str) -> str:
    return tag[1:] if tag[:1] in {"v", "V"} else tag


def clean_release_notes(body: str) -> str:
    """The release text as the dialog shows it.

    Release notes here follow one shape: Highlights, Packages, a picture of
    the Quick Access panel, notes. The package list is what this dialog
    already chose from, and remote pictures are not loaded inside the
    application, so both go; the rest stays as written.
    """
    text = str(body or "").replace("\r\n", "\n")
    text = re.sub(r"<img\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    lines = text.split("\n")
    kept: list[str] = []
    skipping = False
    for line in lines:
        heading = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if heading:
            skipping = heading.group(2).strip().casefold() in {"packages", "paquetes"}
        if not skipping:
            kept.append(line)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def parse_release(payload: object) -> ReleaseInfo:
    if not isinstance(payload, dict):
        raise UpdateError("GitHub returned something that is not a release.")
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("The latest release has no version tag.")
    assets = []
    for item in payload.get("assets") or ():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if not name or not url.lower().startswith("https://"):
            continue
        digest = str(item.get("digest") or "")
        sha256 = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
        assets.append(
            ReleaseAsset(
                name=name,
                size=int(item.get("size") or 0),
                url=url,
                sha256=sha256 if _SHA256.fullmatch(sha256) else "",
            )
        )
    return ReleaseInfo(
        version=_version_from_tag(tag),
        tag=tag,
        title=str(payload.get("name") or tag),
        published_at=str(payload.get("published_at") or ""),
        notes=clean_release_notes(str(payload.get("body") or "")),
        page_url=str(payload.get("html_url") or RELEASES_PAGE_URL),
        assets=tuple(assets),
    )


def _get(url: str, *, limit: int, accept: str, timeout: float) -> bytes:
    if not url.lower().startswith("https://"):
        raise UpdateError("Only https addresses are used for updates.")
    request = urllib.request.Request(
        url, method="GET", headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    try:
        with _opener().open(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise UpdateError(f"GitHub answered {response.status}.")
            data = response.read(limit + 1)
    except UpdateError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise UpdateError(f"GitHub could not be reached: {error}") from error
    if len(data) > limit:
        raise UpdateError("GitHub's answer was larger than a release can be.")
    return data


def fetch_latest_release(*, url: str = LATEST_RELEASE_URL) -> ReleaseInfo:
    """The latest published release, or ``UpdateError`` saying why not."""
    raw = _get(url, limit=MAX_RELEASE_JSON_BYTES, accept="application/vnd.github+json", timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise UpdateError("GitHub's release information could not be read.") from error
    release = parse_release(payload)
    return _with_published_checksums(release)


def _with_published_checksums(release: ReleaseInfo) -> ReleaseInfo:
    """Fill checksums from ``SHA256SUMS.txt`` for assets GitHub gave none."""
    if all(asset.sha256 for asset in release.assets):
        return release
    sums = next((asset for asset in release.assets if asset.name.upper() == "SHA256SUMS.TXT"), None)
    if sums is None:
        return release
    try:
        text = _get(sums.url, limit=64 * 1024, accept="text/plain", timeout=REQUEST_TIMEOUT_SECONDS).decode("utf-8", "replace")
    except UpdateError:
        return release
    published: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and _SHA256.fullmatch(parts[0].lower()):
            published[parts[1].lstrip("*")] = parts[0].lower()
    assets = tuple(
        asset if asset.sha256 else ReleaseAsset(asset.name, asset.size, asset.url, published.get(asset.name, ""))
        for asset in release.assets
    )
    return ReleaseInfo(
        release.version, release.tag, release.title, release.published_at,
        release.notes, release.page_url, assets,
    )


def _asset_for(release: ReleaseInfo, *suffixes: str, prefer: str = "") -> ReleaseAsset | None:
    candidates = [
        asset for asset in release.assets
        if asset.name.startswith(PACKAGE_NAME) and asset.name.endswith(suffixes)
    ]
    if prefer:
        preferred = [asset for asset in candidates if prefer in asset.name]
        if preferred:
            candidates = preferred
    return candidates[0] if candidates else None


def plan_update(
    release: ReleaseInfo,
    source: InstallSource,
    *,
    os_family: str = "",
    atomic: bool | None = None,
    project_root: Path | None = None,
) -> UpdatePlan:
    """The one way this installation gets ``release``."""
    atomic = Path("/run/ostree-booted").exists() if atomic is None else atomic
    root = project_root if project_root is not None else Path(__file__).resolve().parents[3]
    family = str(os_family or "").lower()

    if (root / ".git").exists():
        return UpdatePlan(
            "manual",
            reason="This copy runs from a git checkout. Update it with git pull.",
        )
    if source.channel is UpdateChannel.AUR:
        helper = source.helper
        if not helper:
            return UpdatePlan("manual", reason="No AUR helper (paru, yay...) was found.")
        return UpdatePlan(
            "aur",
            helper=helper,
            manager="pacman",
            summary=f"{helper} rebuilds {source.package or AUR_PACKAGE} from the AUR.",
        )
    if source.channel is UpdateChannel.PACKAGE:
        if source.manager == "pacman":
            if family == "steamos":
                return UpdatePlan(
                    "manual",
                    reason="SteamOS keeps its system image read-only; install the package from Desktop Mode by hand.",
                )
            asset = _asset_for(release, ".pkg.tar.zst")
            manager = "pacman"
        elif source.manager == "rpm":
            asset = _asset_for(release, ".rpm", prefer="atomic" if atomic else "fedora")
            manager = "rpm-ostree" if atomic else "dnf"
        elif source.manager == "dpkg":
            asset = _asset_for(release, ".deb")
            manager = "apt"
        else:
            asset, manager = None, ""
        if asset is None:
            return UpdatePlan("manual", reason="This release has no package for this system.")
        if not asset.sha256:
            return UpdatePlan("manual", asset=asset, reason="This release publishes no checksum for its package.")
        return UpdatePlan(
            "package",
            asset=asset,
            manager=manager,
            reboot_required=manager == "rpm-ostree",
            summary=asset.name,
        )
    asset = _asset_for(release, ".tar.gz")
    if asset is None:
        return UpdatePlan("manual", reason="This release has no source archive.")
    if not asset.sha256:
        return UpdatePlan("manual", asset=asset, reason="This release publishes no checksum for its archive.")
    return UpdatePlan("source", asset=asset, manager="install-local.sh", summary=asset.name)


def updates_directory() -> Path:
    directory = Path(app_cache_dir()) / "updates"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:
        logger.debug("Could not restrict the updates directory", exc_info=True)
    return directory


def download_asset(
    asset: ReleaseAsset,
    directory: Path | None = None,
    *,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    opener=None,
) -> Path:
    """Download ``asset`` and prove it is the published file.

    Streams to ``<name>.part`` while hashing, and only a complete file whose
    size and SHA-256 match what GitHub published becomes ``<name>``.
    """
    if not asset.sha256:
        raise UpdateError("No published checksum; the package will not be downloaded.")
    if not asset.url.lower().startswith("https://"):
        raise UpdateError("Only https addresses are used for updates.")
    if asset.size > MAX_PACKAGE_BYTES:
        raise UpdateError("The package is larger than any release of this application.")
    if "/" in asset.name or asset.name.startswith("."):
        raise UpdateError("The package name is not a plain file name.")
    directory = directory if directory is not None else updates_directory()
    target = directory / asset.name
    partial = directory / f"{asset.name}.part"
    request = urllib.request.Request(asset.url, method="GET", headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    received = 0
    total = max(0, int(asset.size))
    try:
        with (opener or _opener()).open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, \
                open(partial, "wb") as handle:
            if getattr(response, "status", 200) != 200:
                raise UpdateError(f"The download answered {response.status}.")
            while True:
                if cancelled is not None and cancelled():
                    raise UpdateError("Cancelled.")
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_PACKAGE_BYTES or (total and received > total):
                    raise UpdateError("The download is larger than the published package.")
                digest.update(chunk)
                handle.write(chunk)
                if progress is not None:
                    progress(received, total)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"The download failed: {error}") from error
    if total and received != total:
        partial.unlink(missing_ok=True)
        raise UpdateError("The download ended before the whole package arrived.")
    if digest.hexdigest() != asset.sha256:
        partial.unlink(missing_ok=True)
        raise UpdateError("The downloaded package does not match its published SHA-256.")
    os.replace(partial, target)
    try:
        target.chmod(0o600)
    except OSError:
        logger.debug("Could not restrict the downloaded package", exc_info=True)
    return target


def install_command(plan: UpdatePlan, package: Path | None = None) -> str:
    """The shell command the terminal runs for ``plan``.

    A downloaded package is checked against its SHA-256 again in the same
    command, right before the package manager sees it.
    """
    if plan.kind == "aur":
        helper = plan.helper
        package_name = shlex.quote(AUR_PACKAGE)
        flags = {
            "paru": "--noconfirm --skipreview",
            "yay": "--noconfirm --answerclean None --answerdiff None --answeredit None",
        }.get(helper, "")
        return f"{shlex.quote(helper)} -S {flags} {package_name}".replace("  ", " ")
    if plan.kind not in {"package", "source"} or plan.asset is None or package is None:
        raise UpdateError("Nothing to install for this plan.")
    path = shlex.quote(str(package))
    verify = f"printf '%s  %s\\n' {shlex.quote(plan.asset.sha256)} {path} | sha256sum -c -"
    if plan.kind == "source":
        return (
            f"{verify} && workdir=$(mktemp -d) && tar -xzf {path} -C \"$workdir\" "
            "&& cd \"$workdir\"/bc250-control-center-* && bash scripts/install-local.sh"
        )
    install = {
        "pacman": f"sudo pacman -U --noconfirm -- {path}",
        "dnf": f"sudo dnf install -y -- {path}",
        "apt": f"sudo apt install -y -- {path}",
        # A layered package is replaced in one transaction; a system that has
        # none layered yet takes it as a new one.
        "rpm-ostree": (
            f"current=$(rpm -q {shlex.quote(PACKAGE_NAME)} 2>/dev/null || true); "
            f"if [ -n \"$current\" ]; then sudo rpm-ostree uninstall \"$current\" --install {path} "
            f"|| sudo rpm-ostree install {path}; else sudo rpm-ostree install {path}; fi"
        ),
    }.get(plan.manager)
    if install is None:
        raise UpdateError("No installer is known for this system.")
    return f"{verify} && {install}"
