"""DirectMesh: Mesh and Task shaders for the BC-250 through upstream's installer.

DirectMesh (lonewolf0622/Mesh-Shaders-for-Rdna-1-) is a Mesa 26.2.1 RADV with
``VK_EXT_mesh_shader`` for the BC-250 (GFX1013) and RDNA 1. Its ``install.sh``
builds only the Vulkan driver, for the current user, in
``~/.local/share/directmesh``; the system driver is never replaced. A game
uses it through a Steam launch option (``VK_DRIVER_FILES=...``) that the user
copies from the Compatibility card.

The rules this module follows:

* **Upstream's installer, unchanged.** It is the path the author tests and
  supports. The release's ``install.sh`` asset is downloaded on the user's
  PC and checked before it runs: a reviewed release against the SHA-256
  recorded here, a release found later by Check for new releases against the
  digest GitHub publishes for that asset (HelixSR's rule). It runs in the
  terminal, so its one ``sudo`` prompt (build packages) is the user's to
  answer.
* **Never the withdrawn ones.** ``directmesh-v1.4.1`` hung the GPU on a
  BC-250 and was withdrawn the same day; it is never offered even though
  GitHub still lists it as a pre-release.
* **Bazzite in a container.** The installer refuses immutable hosts and says
  to run it in a container of the same Fedora release. That is what is done
  here (distrobox, or toolbox), and it is marked experimental: the driver is
  built against the container's libraries, so the host is checked with
  ``ldd`` and ``vulkaninfo`` before the install counts.
* **Per game only.** ``--global`` is never passed: a GPU hang in the desktop
  compositor locks a BC-250 hard.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

DIRECTMESH_REPOSITORY = "https://github.com/lonewolf0622/Mesh-Shaders-for-Rdna-1-"
DIRECTMESH_RELEASES_API = (
    "https://api.github.com/repos/lonewolf0622/Mesh-Shaders-for-Rdna-1-/releases?per_page=50"
)
DIRECTMESH_TAG = "directmesh-v1.4"
DIRECTMESH_INSTALLER = "install.sh"
#: Each release reviewed here: the SHA-256 of its ``install.sh`` asset.
#: v1.4 (commit cac0bcc5) is the first release that ships the installer.
DIRECTMESH_REVIEWED: dict[str, dict[str, str]] = {
    "directmesh-v1.4": {
        "installer_sha256": "531c4960d769f36c8b59b392fb927cbeb240baeb6f956efd400e9d19bba5b00f",
    },
}
#: Upstream withdrew these (GPU hangs on a BC-250). Never offered.
DIRECTMESH_WITHDRAWN = frozenset({"directmesh-v1.4.1"})
#: Releases before this one have no ``install.sh`` asset.
DIRECTMESH_OLDEST = (1, 4)
DIRECTMESH_CONTAINER = "bc250-directmesh"
_RELEASES_LIMIT = 4 * 1024 * 1024
_TAG = re.compile(r"directmesh-v(\d{1,4}(?:\.\d{1,4}){1,3})")
_SHA256 = re.compile(r"[0-9a-f]{64}")

_HOST_IDS = frozenset({"arch", "cachyos", "cachy", "manjaro", "endeavouros"})
_CONTAINER_IDS = frozenset({"bazzite"})


# --- paths ----------------------------------------------------------------------------------------


def _data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".local" / "share"


def directmesh_prefix() -> Path:
    """Where upstream's installer puts the driver (its own default)."""
    return _data_home() / "directmesh"


def directmesh_icd() -> Path:
    return directmesh_prefix() / "share" / "vulkan" / "icd.d" / "radeon_icd.x86_64.json"


def directmesh_root() -> Path:
    """Control Center's own records: release list, pick, what was installed."""
    return _data_home() / "bc250-control-center" / "directmesh"


def _releases_path() -> Path:
    return directmesh_root() / "releases.json"


def _selection_path() -> Path:
    return directmesh_root() / "selection.json"


def _installed_path() -> Path:
    return directmesh_root() / "installed.json"


def _read_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


# --- releases -------------------------------------------------------------------------------------


def _version(tag: str) -> tuple[int, ...] | None:
    """``directmesh-v1.4`` -> (1, 4); None for any other tag."""
    match = _TAG.fullmatch(str(tag or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _published_release(entry: object) -> dict | None:
    """One release from GitHub's list, if it can be installed here.

    It needs a ``directmesh-vX.Y`` tag no older than DIRECTMESH_OLDEST, not
    withdrawn, and exactly one ``install.sh`` asset whose SHA-256 GitHub
    published.
    """
    if not isinstance(entry, dict) or entry.get("draft"):
        return None
    tag = str(entry.get("tag_name") or "")
    version = _version(tag)
    if version is None or version < DIRECTMESH_OLDEST or tag in DIRECTMESH_WITHDRAWN:
        return None
    installers = [
        asset for asset in entry.get("assets") or ()
        if isinstance(asset, dict) and asset.get("name") == DIRECTMESH_INSTALLER
    ]
    if len(installers) != 1:
        return None
    digest = str(installers[0].get("digest") or "").removeprefix("sha256:").lower()
    if not _SHA256.fullmatch(digest):
        return None
    return {"tag": tag, "installer_sha256": digest, "prerelease": bool(entry.get("prerelease"))}


def directmesh_releases() -> list[dict]:
    """The releases on offer, newest first.

    The reviewed ones always; the ones Check for new releases found on GitHub
    on top. A reviewed release keeps its reviewed digest. Once a list was
    read, a release GitHub no longer lists is not offered.
    """
    releases = {
        tag: {"tag": tag, **entry, "prerelease": False, "reviewed": True}
        for tag, entry in DIRECTMESH_REVIEWED.items()
        if tag not in DIRECTMESH_WITHDRAWN
    }
    listed = _read_json(_releases_path(), {}).get("releases")
    if isinstance(listed, list):
        found: dict[str, dict] = {}
        for entry in listed[:200]:
            release = _published_release(entry)
            if release is not None:
                found.setdefault(release["tag"], release)
        for tag, release in found.items():
            if tag in releases:
                releases[tag]["prerelease"] = release["prerelease"]
            else:
                releases[tag] = {**release, "reviewed": False}
        if found:
            releases = {tag: release for tag, release in releases.items() if tag in found}
    rows = [
        {
            **release,
            "version": tag.removeprefix("directmesh-v"),
            "default": tag == DIRECTMESH_TAG,
        }
        for tag, release in releases.items()
    ]
    return sorted(rows, key=lambda release: _version(release["tag"]) or (), reverse=True)


def directmesh_release(tag: str | None = None) -> dict:
    """The release with ``tag``, by default the one the user picked."""
    wanted = tag if tag is not None else _read_json(_selection_path(), {}).get("tag")
    releases = {release["tag"]: release for release in directmesh_releases()}
    if wanted in releases:
        return releases[wanted]
    if DIRECTMESH_TAG in releases:
        return releases[DIRECTMESH_TAG]
    return {
        "tag": DIRECTMESH_TAG,
        "version": DIRECTMESH_TAG.removeprefix("directmesh-v"),
        **DIRECTMESH_REVIEWED[DIRECTMESH_TAG],
        "prerelease": False,
        "reviewed": True,
        "default": True,
    }


def select_directmesh_release(tag: str) -> dict:
    """Pick the release Install/Update brings in. Nothing is downloaded here."""
    tag = str(tag or "").strip()
    if tag not in {release["tag"] for release in directmesh_releases()}:
        raise ValueError("This DirectMesh release is not on offer.")
    _write_json(_selection_path(), {"tag": tag})
    return {"ok": True, "tag": tag}


def _newer_release(installed_tag: str) -> dict | None:
    """The newest stable release, if newer than the installed one."""
    mine = _version(installed_tag) or ()
    for entry in directmesh_releases():
        if entry["prerelease"] or (_version(entry["tag"]) or ()) <= mine:
            continue
        return {key: entry[key] for key in ("tag", "version", "prerelease", "reviewed")}
    return None


# --- platform and state ---------------------------------------------------------------------------


def directmesh_platform(*, family: str, distro_id: str, version_id: str = "") -> tuple[str, str]:
    """``(platform, reason)``: "host", "container" or "" with why not."""
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    if distro_id in _CONTAINER_IDS or family == "bazzite":
        if not str(version_id or "").strip().isdigit():
            return "", "The Fedora release of this Bazzite could not be read."
        return "container", ""
    if family == "arch" or distro_id in _HOST_IDS:
        return "host", ""
    if family == "steamos" or distro_id == "steamos":
        return "", "DirectMesh's installer does not support SteamOS."
    return "", "Offered on Arch, CachyOS, Manjaro and Bazzite."


def _i686_icd() -> str:
    """The system's 32-bit RADV manifest, which 32-bit games keep using."""
    for candidate in (
        "/usr/share/vulkan/icd.d/radeon_icd.i686.json",
        "/usr/share/vulkan/icd.d/radeon_icd.x86.json",
    ):
        if Path(candidate).is_file():
            return candidate
    return ""


def directmesh_launch_option() -> str:
    """The Steam launch option for an installed DirectMesh, or ""."""
    if not _icd_valid():
        return ""
    files = str(directmesh_icd())
    i686 = _i686_icd()
    if i686:
        files = f"{files}:{i686}"
    return f"VK_DRIVER_FILES={shlex.quote(files)} %command%"


def _icd_valid() -> bool:
    try:
        manifest = json.loads(directmesh_icd().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    icd = manifest.get("ICD") if isinstance(manifest, dict) else None
    library = str(icd.get("library_path") or "") if isinstance(icd, dict) else ""
    if not library:
        return False
    path = Path(library)
    if not path.is_absolute():
        path = directmesh_icd().parent / path
    return path.is_file()


def directmesh_state(*, family: str, distro_id: str, version_id: str = "") -> dict:
    """Everything the Compatibility card shows. Reads files only."""
    platform, reason = directmesh_platform(
        family=family, distro_id=distro_id, version_id=version_id
    )
    installed = _icd_valid()
    record = _read_json(_installed_path(), {}) if installed else {}
    installed_tag = str(record.get("tag") or "")
    if _version(installed_tag) is None:
        installed_tag = ""
    selected = directmesh_release()
    releases = [
        {key: release[key] for key in ("tag", "version", "prerelease", "reviewed", "default")}
        for release in directmesh_releases()
    ]
    return {
        "supported": bool(platform),
        "platform": platform,
        "experimental": platform == "container",
        "reason": reason,
        "installed": installed,
        "installed_tag": installed_tag,
        "installed_version": installed_tag.removeprefix("directmesh-v"),
        "icd": str(directmesh_icd()),
        "launch_option": directmesh_launch_option() if installed else "",
        "releases": releases,
        "selected_tag": selected["tag"],
        "releases_checked": bool(_read_json(_releases_path(), {}).get("releases")),
        "newer": _newer_release(installed_tag) if installed and installed_tag else None,
    }


# --- terminal commands ----------------------------------------------------------------------------


def _fetch_check() -> str:
    return '''for bc250_command in sha256sum mktemp; do
  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }
done
if command -v curl >/dev/null 2>&1; then
  bc250_fetch() { curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$1" "$2"; }
elif command -v wget >/dev/null 2>&1; then
  bc250_fetch() { wget -q -O "$1" "$2"; }
else
  echo "ERROR: curl or wget is required to download DirectMesh's installer."; exit 69
fi'''


def _installer_url(tag: str) -> str:
    return f"{DIRECTMESH_REPOSITORY}/releases/download/{tag}/{DIRECTMESH_INSTALLER}"


def _container_lines(release_id: str, environment: str) -> str:
    """Run the verified installer inside a Fedora container (Bazzite)."""
    name = shlex.quote(DIRECTMESH_CONTAINER)
    image = shlex.quote(f"registry.fedoraproject.org/fedora-toolbox:{release_id}")
    return f'''echo "Bazzite: building in the container {DIRECTMESH_CONTAINER} (Fedora {release_id}), as DirectMesh's installer asks."
if command -v distrobox >/dev/null 2>&1; then
  if ! distrobox list --no-color 2>/dev/null | awk -F'|' '{{gsub(/ /, "", $2); print $2}}' | grep -qx {name}; then
    distrobox create --yes --name {name} --image {image}
  fi
  bc250_in_container() {{ distrobox enter {name} -- "$@"; }}
elif command -v toolbox >/dev/null 2>&1; then
  if ! toolbox list --containers 2>/dev/null | awk 'NR > 1 {{print $2}}' | grep -qx {name}; then
    toolbox create --assumeyes --container {name} --release {shlex.quote(release_id)}
  fi
  bc250_in_container() {{ toolbox run --container {name} "$@"; }}
else
  echo "ERROR: distrobox or toolbox is required to build DirectMesh on Bazzite."; exit 69
fi
if bc250_in_container test -e /run/ostree-booted; then
  echo "ERROR: the container looks like the immutable host to DirectMesh's installer; it would refuse to run."; exit 69
fi
bc250_in_container env {environment} bash "$bc250_installer"'''


def build_directmesh_install_command(*, family: str, distro_id: str, version_id: str = "") -> str:
    """Download and verify the picked release's installer, then run it."""
    platform, reason = directmesh_platform(
        family=family, distro_id=distro_id, version_id=version_id
    )
    if not platform:
        raise RuntimeError(reason)
    release = directmesh_release()
    tag = release["tag"]
    digest = str(release.get("installer_sha256") or "")
    if _version(tag) is None or tag in DIRECTMESH_WITHDRAWN or not _SHA256.fullmatch(digest):
        raise RuntimeError("This DirectMesh release cannot be verified.")
    prefix = str(directmesh_prefix())
    root = shlex.quote(str(directmesh_root()))
    icd = shlex.quote(str(directmesh_icd()))
    environment = " ".join((
        f"DIRECTMESH_VERSION={shlex.quote(tag)}",
        f"DIRECTMESH_PREFIX={shlex.quote(prefix)}",
    ))
    if platform == "container":
        run = _container_lines(str(version_id).strip(), environment)
    else:
        run = f'env {environment} bash "$bc250_installer"'
    source = "reviewed by Control Center" if release.get("reviewed") else "published by GitHub"
    return f'''set -Eeuo pipefail
echo "== DirectMesh {tag} =="
echo "Source: {DIRECTMESH_REPOSITORY} (upstream installer, unchanged)"
test "$(uname -m)" = x86_64 || {{ echo "ERROR: DirectMesh needs an x86_64 system."; exit 64; }}
{_fetch_check()}
mkdir -p "$HOME/.cache"
bc250_work="$(mktemp -d "$HOME/.cache/bc250-directmesh.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
bc250_installer="$bc250_work/install.sh"
bc250_fetch "$bc250_installer" {shlex.quote(_installer_url(tag))}
bc250_actual="$(sha256sum "$bc250_installer" | awk '{{print $1}}')"
if test "$bc250_actual" != {digest}; then
  echo "ERROR: the installer's SHA-256 is $bc250_actual, not the one {source} ({digest})."
  echo "Nothing was run. Check for new releases, or report it upstream."
  exit 29
fi
echo "Installer verified ({source})."
{run}
test -f {icd} || {{ echo "ERROR: the installer finished but {icd} is missing."; exit 29; }}
bc250_library="$(dirname {icd})/../../../lib/libvulkan_radeon.so"
if command -v ldd >/dev/null 2>&1 && test -f "$bc250_library" && ldd "$bc250_library" | grep -q 'not found'; then
  ldd "$bc250_library" | grep 'not found' || true
  echo "ERROR: this system lacks libraries the driver was built against. Remove DirectMesh and report it upstream."
  exit 29
fi
mkdir -p {root}
install -m 0644 "$bc250_installer" {root}/install.sh
printf '{{"tag": "%s", "installer_sha256": "%s", "platform": "%s"}}\\n' {shlex.quote(tag)} {digest} {platform} > {root}/installed.json
echo
echo "OK: DirectMesh {tag} is installed. Copy the launch option from the Compatibility card into"
echo "Steam > right-click the game > Properties > Launch options."
'''


def build_directmesh_check_command() -> str:
    """Ask Vulkan, through DirectMesh's driver, whether Mesh shaders are on."""
    option = directmesh_launch_option()
    if not option:
        raise RuntimeError("Install DirectMesh first.")
    files = option.removeprefix("VK_DRIVER_FILES=").removesuffix(" %command%")
    return f'''set -Euo pipefail
echo "== DirectMesh · check =="
command -v vulkaninfo >/dev/null 2>&1 || {{ echo "ERROR: vulkaninfo is not installed (package vulkan-tools)."; exit 69; }}
VK_DRIVER_FILES={files} vulkaninfo --summary 2>/dev/null | grep -E 'deviceName|driverInfo' | sed 's/^[[:space:]]*/   /' || true
if VK_DRIVER_FILES={files} vulkaninfo 2>/dev/null | grep -E 'meshShader *= *true' >/dev/null; then
  echo "OK: Mesh shaders: yes"
else
  echo "Mesh shaders: no (DirectMesh did not load, this GPU is not a BC-250 or Navi 10/12, or RADV_DIRECTMESH=0 is set)."
  exit 1
fi
'''


def build_directmesh_uninstall_command(*, family: str = "", distro_id: str = "") -> str:
    """Upstream's own --uninstall, then Control Center's records and container."""
    root = shlex.quote(str(directmesh_root()))
    prefix = shlex.quote(str(directmesh_prefix()))
    record = _read_json(_installed_path(), {})
    digest = str(record.get("installer_sha256") or "")
    if not _SHA256.fullmatch(digest):
        digest = "-"
    container = ""
    if str(family).lower() == "bazzite" or str(distro_id).lower() in _CONTAINER_IDS:
        name = shlex.quote(DIRECTMESH_CONTAINER)
        container = f'''if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | grep -qw {name}; then
  distrobox rm --force {name} || echo "Note: the container {DIRECTMESH_CONTAINER} could not be removed."
elif command -v toolbox >/dev/null 2>&1 && toolbox list --containers 2>/dev/null | grep -qw {name}; then
  toolbox rm --force {name} || echo "Note: the container {DIRECTMESH_CONTAINER} could not be removed."
fi'''
    return f'''set -Euo pipefail
echo "== DirectMesh · remove =="
bc250_saved={root}/install.sh
if test -f "$bc250_saved" && test "$(sha256sum "$bc250_saved" | awk '{{print $1}}')" = {shlex.quote(digest)}; then
  DIRECTMESH_PREFIX={prefix} bash "$bc250_saved" --uninstall
else
  echo "Removing the files DirectMesh's installer puts in place."
  rm -rf -- {prefix} "${{XDG_CACHE_HOME:-$HOME/.cache}}/directmesh-build" "$HOME/.local/bin/directmesh-run" \\
    "${{XDG_CONFIG_HOME:-$HOME/.config}}/environment.d/90-directmesh.conf"
fi
{container}
rm -f -- {root}/install.sh {root}/installed.json
echo "OK: DirectMesh was removed. Take VK_DRIVER_FILES=... out of the launch options of the games you added it to."
'''


def build_directmesh_releases_command() -> str:
    """Save GitHub's list of DirectMesh releases, for the version picker."""
    root = shlex.quote(str(directmesh_root()))
    python = shlex.quote(sys.executable or "python3")
    withdrawn = " ".join(sorted(DIRECTMESH_WITHDRAWN))
    return f'''set -Eeuo pipefail
echo "== DirectMesh · releases =="
echo "Source: {DIRECTMESH_REPOSITORY}/releases"
{_fetch_check()}
bc250_python="$(command -v python3 || echo {python})"
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-directmesh-releases.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
bc250_fetch "$bc250_work/releases.json" {shlex.quote(DIRECTMESH_RELEASES_API)}
mkdir -p {root}
"$bc250_python" -I - "$bc250_work/releases.json" {root}/releases.json {_RELEASES_LIMIT} {shlex.quote(withdrawn)} <<'BC250_RELEASES'
import json, os, sys, time
source, destination, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
withdrawn = set(sys.argv[4].split())
if os.path.getsize(source) > limit:
    sys.exit("ERROR: GitHub's answer is larger than expected.")
listed = json.load(open(source, encoding="utf-8"))
if not isinstance(listed, list):
    sys.exit("ERROR: GitHub did not answer with a list of releases.")
kept = []
for entry in listed[:200]:
    if not isinstance(entry, dict):
        continue
    kept.append({{
        "tag_name": str(entry.get("tag_name") or ""),
        "draft": bool(entry.get("draft")),
        "prerelease": bool(entry.get("prerelease")),
        "assets": [
            {{"name": str(a.get("name") or ""), "size": a.get("size"), "digest": str(a.get("digest") or "")}}
            for a in entry.get("assets") or () if isinstance(a, dict)
        ],
    }})
staged = destination + ".tmp"
with open(staged, "w", encoding="utf-8") as handle:
    json.dump({{"time": int(time.time()), "releases": kept}}, handle, indent=1)
os.replace(staged, destination)
for entry in kept:
    if entry["draft"]:
        continue
    has_installer = sum(1 for a in entry["assets"] if a["name"] == "install.sh") == 1
    note = ""
    if entry["tag_name"] in withdrawn:
        note = "  (withdrawn upstream: not offered)"
    elif not has_installer:
        note = "  (no install.sh: not offered)"
    print("  " + entry["tag_name"] + ("  (pre-release)" if entry["prerelease"] else "") + note)
BC250_RELEASES
echo "OK: the version list is up to date. Pick a version on the DirectMesh card, then Install or Update."
'''
