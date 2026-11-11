"""Update this installation to the latest published release.

The dashboard already knows when a newer version exists (``release_check``).
This module does the rest: it reads that release from GitHub, picks the one
package that matches how this copy was installed, downloads it with the
checksum GitHub publishes for it, and builds the one command that installs
it. The command runs in the application's terminal like every other
privileged workflow, so the output and the exit status are the ones the user
already knows.

Authorization asks for a window first. A password typed into the terminal was
the only route, and on a board driven with a controller from the sofa nobody
typed it: sudo timed out twice and the update failed at 81 %. With a
graphical Polkit agent, pacman, dnf and APT run through ``pkexec``, and
rpm-ostree asks Polkit itself; the terminal password stays as the fallback.

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
* **Never guess.** A development checkout or a release without a package for
  this system gets the release page instead of a best effort.
* **SteamOS too.** Its root is read-only, so the one authorization runs a
  small root script that switches the protection off, installs the package
  with pacman and switches it back on, whether pacman succeeded or not.
* **One package in the cache.** A verified download is reused by a retry
  instead of fetched again, every other file in the updates folder (older
  versions, a ``.part`` left by a crash) is removed before a download, and the
  package is deleted once it is installed.
"""

from __future__ import annotations

import hashlib
import html
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


#: Sections that describe the release page rather than the change.
_DROPPED_SECTIONS = frozenset({"packages", "paquetes", "screenshots", "capturas", "capturas de pantalla"})


def _version_from_tag(tag: str) -> str:
    return tag[1:] if tag[:1] in {"v", "V"} else tag


def clean_release_notes(body: str) -> str:
    """The release text as the dialog shows it.

    Release notes here follow one shape: Highlights, Packages, a picture of
    the Quick Access panel, notes. The package list is what this dialog
    already chose from, and remote pictures are not loaded inside the
    application, so both go; the rest stays as written.

    HTML goes too. The notes are shown as text, and 1.20.3 pasted the
    README's screenshot carousel, a ``<table>`` of links, which the dialog
    printed as raw markup under "Screenshots".
    """
    text = str(body or "").replace("\r\n", "\n")
    text = re.sub(r"<img\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = html.unescape(re.sub(r"</?[A-Za-z][^<>]*>", "", text))
    lines = text.split("\n")
    kept: list[str] = []
    skipping = False
    for line in lines:
        heading = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if heading:
            skipping = heading.group(2).strip().casefold() in _DROPPED_SECTIONS
        if not skipping:
            kept.append(line.rstrip())
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
            asset = _asset_for(release, ".pkg.tar.zst")
            manager = "pacman-steamos" if family == "steamos" else "pacman"
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune_updates(directory: Path | None = None, *, keep: str = "") -> None:
    """Remove everything in the updates folder except the file named ``keep``.

    Older versions and a ``.part`` left by a crash only take space, and a
    stale file under the same name is re-verified before it is reused.
    """
    directory = directory if directory is not None else updates_directory()
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name == keep or not entry.is_file() or entry.is_symlink():
            continue
        try:
            entry.unlink()
        except OSError:
            logger.debug("Could not remove %s from the updates folder", entry, exc_info=True)


def discard_update(path: Path) -> None:
    """Delete an installed package; the package manager keeps its own copy."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove the installed update package", exc_info=True)


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
    size and SHA-256 match what GitHub published becomes ``<name>``. A file
    already there that still matches is returned without downloading again,
    which is what makes a retry after a failed install quick; one that does
    not match is thrown away first.
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
    prune_updates(directory, keep=asset.name)
    if target.is_file() and not target.is_symlink():
        try:
            reusable = target.stat().st_size == asset.size and _file_sha256(target) == asset.sha256
        except OSError:
            reusable = False
        if reusable:
            if progress is not None:
                progress(asset.size, asset.size)
            return target
        target.unlink(missing_ok=True)
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


# ``bc250_admin CMD...`` runs CMD as root. With a graphical agent it asks
# through pkexec's window; when that window is dismissed (126) or no agent
# answers (127) the terminal asks through sudo instead of failing.
_ADMIN_FUNCTION = """bc250_admin() {
  if [ "${BC250_GRAPHICAL_AUTH:-0}" = 1 ] && command -v pkexec >/dev/null 2>&1; then
    pkexec "$@"
    bc250_rc=$?
    if [ "$bc250_rc" -ne 126 ] && [ "$bc250_rc" -ne 127 ]; then return "$bc250_rc"; fi
    echo "The authorization window did not answer; asking for the password in this terminal."
  fi
  sudo "$@"
}"""

# rpm-ostree talks to its daemon over D-Bus and asks Polkit itself, so it runs
# without sudo: the desktop shows its authorization window. Only when Polkit
# refuses without asking (no agent) does it fall back to sudo in the terminal.
# It waits for a running transaction (Bazzite's automatic system updates) and
# replaces what the next deployment actually layers, read from rpm-ostree's
# own status, instead of the booted rpm's name: a plain ``rpm-ostree install``
# next to a layered older version fails with "cannot install both".
_RPM_OSTREE_BUSY = (
    "import json, sys\n"
    "sys.exit(0 if json.load(sys.stdin).get('transaction') else 1)\n"
)
_RPM_OSTREE_LAYERED = (
    "import json, sys\n"
    "deployments = json.load(sys.stdin).get('deployments') or [{}]\n"
    "d = deployments[0]\n"
    "names = list(d.get('requested-local-packages') or []) + list(d.get('requested-packages') or [])\n"
    "print(' '.join(n for n in names if n == 'bc250-control-center' or n.startswith('bc250-control-center-')))\n"
)


def _rpm_ostree_install(path: str) -> str:
    busy = shlex.quote(_RPM_OSTREE_BUSY)
    layered = shlex.quote(_RPM_OSTREE_LAYERED)
    return f"""bc250_rpm_ostree() {{
  bc250_log=$(mktemp)
  rpm-ostree "$@" 2>&1 | tee "$bc250_log"
  bc250_rc=${{PIPESTATUS[0]}}
  bc250_busy=0
  if grep -q 'Transaction in progress' "$bc250_log"; then bc250_busy=1; fi
  if [ "$bc250_rc" -ne 0 ] && grep -qiE 'authoriz|not allowed|polkit' "$bc250_log"; then
    rm -f "$bc250_log"
    echo "No authorization window answered; asking for the password in this terminal."
    sudo rpm-ostree "$@"
    return $?
  fi
  # A 404 means the cached repository metadata is older than the mirrors
  # (updates-archive after a Fedora bump): refresh it and try once more.
  if [ "$bc250_rc" -ne 0 ] && grep -qE 'Status code: 404|All mirrors were tried' "$bc250_log"; then
    echo "Repository metadata is out of date; refreshing it and trying once more..."
    rpm-ostree refresh-md --force 2>&1 || sudo rpm-ostree refresh-md --force
    rpm-ostree "$@" 2>&1 | tee "$bc250_log"
    bc250_rc=${{PIPESTATUS[0]}}
  fi
  # rpm-ostree re-resolves every layered package. One that this Fedora release
  # no longer ships (for example coolercontrol, R-506fdded) blocks the update.
  if [ "$bc250_rc" -ne 0 ] && grep -q 'Packages not found:' "$bc250_log"; then
    bc250_missing="$(grep -m1 'Packages not found:' "$bc250_log" | sed 's/.*Packages not found: *//')"
    echo "ERROR: $(grep -m1 'Packages not found:' "$bc250_log")"
    echo "Layered on this system, but no enabled repository publishes it any more: $bc250_missing"
    echo "Control Center did not install it. Re-enable the repository that provides it, or remove it on purpose and update again: rpm-ostree uninstall $bc250_missing"
  fi
  rm -f "$bc250_log"
  return "$bc250_rc"
}}
bc250_attempt=0
while :; do
  bc250_waited=0
  while rpm-ostree status --json 2>/dev/null | python3 -c {busy}; do
    if [ "$bc250_waited" -eq 0 ]; then echo "Another rpm-ostree transaction (usually an automatic system update) is running; waiting for it to finish..."; fi
    bc250_waited=$((bc250_waited + 1))
    if [ "$bc250_waited" -ge 180 ]; then echo "ERROR: rpm-ostree stayed busy for 15 minutes. Try again once the system update has finished."; exit 75; fi
    sleep 5
  done
  bc250_layered=$(rpm-ostree status --json 2>/dev/null | python3 -c {layered})
  if [ -n "$bc250_layered" ]; then
    bc250_rpm_ostree uninstall $bc250_layered --install {path}
  else
    bc250_rpm_ostree install {path}
  fi
  bc250_status=$?
  bc250_attempt=$((bc250_attempt + 1))
  # An automatic update can start between the check and the install (R-a7519f9d).
  if [ "$bc250_busy" -eq 1 ] && [ "$bc250_attempt" -lt 3 ]; then
    echo "A system update started at the same moment; waiting for it to finish and trying again..."
    sleep 5
    continue
  fi
  break
done
(exit "$bc250_status")"""


# Runs as root with the package path as $1. The read-only protection is
# restored only if this script is the one that turned it off.
_STEAMOS_ROOT_INSTALL = r"""set -u
bc250_package="$1"
bc250_restore=0
if command -v steamos-readonly >/dev/null 2>&1 && steamos-readonly status 2>&1 | grep -Eqi '(^|[^a-z])enabled'; then
  echo "Temporarily disabling SteamOS read-only protection."
  steamos-readonly disable || exit 70
  bc250_restore=1
fi
pacman -U --noconfirm -- "$bc250_package"
bc250_rc=$?
if [ "$bc250_restore" = 1 ]; then
  echo "Restoring SteamOS read-only protection."
  if ! steamos-readonly enable; then
    echo "ERROR: Could not turn read-only protection back on. Run: sudo steamos-readonly enable"
    [ "$bc250_rc" -eq 0 ] && bc250_rc=71
  fi
fi
exit "$bc250_rc"
"""


def _source_installer(install_root: Path | None) -> str:
    """install-local.sh, aimed at the prefix this copy was installed under.

    Without PREFIX the installer puts a user's copy in ~/.local, so a copy
    installed with sudo under /usr/local got a second, newer one in the home
    folder instead of an update, and the old one kept its menu entry. The
    previous in-place updater (update-local.sh) passed the prefix; this does
    the same, with sudo where the installed folder is not the user's.
    """
    root = (install_root if install_root is not None else Path(__file__).resolve().parents[3]).resolve()
    if root.name != PACKAGE_NAME or root.parent.name != "share":
        return "bash scripts/install-local.sh"
    prefix = shlex.quote(str(root.parent.parent))
    if os.access(root, os.W_OK):
        return f"env PREFIX={prefix} bash scripts/install-local.sh"
    return f"sudo env PREFIX={prefix} bash scripts/install-local.sh"


def install_command(
    plan: UpdatePlan,
    package: Path | None = None,
    *,
    graphical: bool = False,
    install_root: Path | None = None,
) -> str:
    """The shell command the terminal runs for ``plan``.

    A downloaded package is checked against its SHA-256 again in the same
    command, right before the package manager sees it. ``graphical`` says a
    Polkit agent is running, so the administrator step can ask in a window.
    ``install_root`` is the folder this copy runs from (for a source install).
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
            f"&& cd \"$workdir\"/bc250-control-center-* && {_source_installer(install_root)}"
        )
    if plan.manager == "rpm-ostree":
        return f"{verify} || exit 1\n{_rpm_ostree_install(path)}"
    auth = "BC250_GRAPHICAL_AUTH=1" if graphical else "BC250_GRAPHICAL_AUTH=0"
    if plan.manager == "pacman-steamos":
        from bc250cc.infrastructure.steamos_readonly import STEAMOS_PASSWORD_GUARD

        # One authorization for the whole transaction, not one per step.
        root_script = shlex.quote(_STEAMOS_ROOT_INSTALL)
        return (
            f"{auth}\n{_ADMIN_FUNCTION}\n{STEAMOS_PASSWORD_GUARD}\n"
            f"{verify} || exit 1\n"
            "bc250_require_password\n"
            f"bc250_admin bash -c {root_script} bc250-update {path}"
        )
    install = {
        "pacman": f"bc250_admin pacman -U --noconfirm -- {path}",
        "dnf": f"bc250_admin dnf install -y -- {path}",
        "apt": f"bc250_admin apt install -y -- {path}",
    }.get(plan.manager)
    if install is None:
        raise UpdateError("No installer is known for this system.")
    return f"{auth}\n{_ADMIN_FUNCTION}\n{verify} && {install}"
