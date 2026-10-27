"""HelixSR: DLSS Model E reconstruction behind an FSR 3.1 DLL, per game.

HelixSR (lonewolf0622/HelixSR) is a drop-in replacement for a game's AMD
FidelityFX upscaler DLL. The game keeps talking to FSR 3.1; HelixSR runs
NVIDIA's DLSS Model E network as plain Direct3D 12 compute shaders, which
Proton/vkd3d-proton run on the BC-250 (it was developed on one).

Its licence shapes everything this module does:

* the release is never bundled: the official archive is downloaded on the
  user's PC and checked against the SHA-256 recorded here, then installed
  unmodified under the user's data folder. Every release since 1.2 is
  reviewed and recorded; the newest stable one is installed unless the user
  picks another. A newer release (a pre-release too) can be picked once
  Check for new releases has read GitHub's list, and is checked against
  the SHA-256 GitHub publishes for its archive;
* the network NVIDIA's DLL holds must never leave the PC. HelixSR's own
  setup builds it locally from NVIDIA's DLSS DLL (downloaded only after the
  user agrees in the terminal) and appends it to HelixSR's DLL; this module
  only copies that DLL next to a game's on the same PC. Releases before 1.7
  kept the network as two separate files (``helixsr_weights.bin`` and
  ``helixsr_kernels.pak``), which are still recognised and cleaned up;
* the setup's optional ``sudo`` package install is never reached: with numpy
  missing, the setup is told to use its portable Python instead.

Per game, HelixSR replaces the game's ``amd_fidelityfx_upscaler_dx12.dll`` or
``amd_fidelityfx_dx12.dll`` and keeps the original as ``*.original.dll``, as
upstream's README describes. Each change is recorded so it can be undone, and
removal puts the game's own file back.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

from bc250cc.shared.errors import ActionNeeded

from .steam_launch_options import (
    add_dll_override,
    installed_steam_game_folders,
    steam_libraries,
    steam_shortcut_game_folders,
)

HELIXSR_REPOSITORY = "https://github.com/lonewolf0622/HelixSR"

#: Every release this module was reviewed against, by tag. ``sha256`` is the
#: release archive's, ``dll_sha256`` the digest of ``amd_fidelityfx_dx12.dll``
#: inside it, as downloaded: the setup later appends the network to that DLL,
#: and a game file is HelixSR when it matches once that appended part is set
#: aside. 1.2 to 1.4 keep the network in two files beside the DLL, 1.7 builds
#: it the same way and 1.8 appends it to the DLL.
HELIXSR_REVIEWED: dict[str, dict] = {
    # 2.0 moved the DLL into HELIXSR_BUILD_FOLDER (helixsr_dll_folder finds
    # it) and builds DLSS frame generation there too, which this module asks
    # the setup to skip (see _setup_block).
    "v2.0.0": {
        "archive": "HelixSR-2.0.0.zip",
        "sha256": "0d60686eddbb0abd680b27d12a088344b212464ebf0a2dc18d10387e1c817f52",
        "size": 136_997_025,
        "dll_sha256": "82b612a73759117d4203f0ca76f18b325e1c6f3c61c64481c94750abce392a09",
    },
    "v1.8.1": {
        "archive": "HelixSR-1.8.1.zip",
        "sha256": "abab32b16acf2536b39663763c355f3cfd35c4876c90297d6b5481bd9ad03a19",
        "size": 55_766_339,
        "dll_sha256": "78af8c74d2c2634a2af84b463ad0ac3678081d47f22e8ea2aff635a491a9190b",
    },
    "v1.8.0": {
        "archive": "HelixSR-1.8.0.zip",
        "sha256": "7041d4bee121cc33c24660902c9f09481ed15644fe2ff5a458071337e0cda848",
        "size": 56_617_399,
        "dll_sha256": "95e31d2ccf60d3016971c6697d677001598b5888e6ec9f0d033ed0d9daab9e18",
    },
    "v1.7.0": {
        "archive": "HelixSR-1.7.0.zip",
        "sha256": "5254b507d4915293389c66de8f243749d84d7a764b4983671f78b243eb372785",
        "size": 56_601_341,
        "dll_sha256": "542bc9bd44ed5c1458be692b412a02bcde4f0cb348f30053ad95d77bf4c3bfe8",
    },
    "v1.4.3": {
        "archive": "HelixSR-1.4.3.zip",
        "sha256": "d79e849444e0ea8928c0b8df22ec21368ac08ec038417c087a3d2df7a6722119",
        "size": 2_342_525,
        "dll_sha256": "3fe8d532516b6441bd8893d986c494a19795375ebd2a6dffb1a9742e3db7dcfd",
    },
    "v1.3.0": {
        "archive": "HelixSR-1.3.0.zip",
        "sha256": "fb2b570abf2f35b336f83127720ee6640bbbdd8173809f975cfe1aab0e5181eb",
        "size": 2_337_353,
        "dll_sha256": "f1aa13ac8ade0cbccbb43ca8837520ddbcf6d496f1ca9dfe30c6fff9c7c8f3fb",
    },
    "v1.2.0": {
        "archive": "HelixSR-1.2.0.zip",
        "sha256": "7c9aeac2e3dcd73f6e9b2dd8b04c41a828fd8e1a8fe30a2ac77787097ddbeb0e",
        "size": 2_315_352,
        "dll_sha256": "745477ee77c5cccd2de4bd251fc950d33895387f411815e889625fbbdc12a7e4",
    },
}
#: The release installed unless the user picks another: the newest stable
#: one checked on a BC-250 with this module (2.0.0, tested by the maintainer).
HELIXSR_TAG = "v2.0.0"
HELIXSR_VERSION = HELIXSR_TAG.removeprefix("v")
HELIXSR_SHA256 = HELIXSR_REVIEWED[HELIXSR_TAG]["sha256"]
HELIXSR_DLL_SHA256 = HELIXSR_REVIEWED[HELIXSR_TAG]["dll_sha256"]
#: 1.2.0 is the first release whose download holds no NVIDIA content (its
#: setup builds the network on the user's PC): nothing older is offered.
HELIXSR_OLDEST = (1, 2, 0)
#: Every reviewed HelixSR DLL. A game keeps the copy it was given when the
#: release here changes; it is still HelixSR and still removable. 1.9.0 was
#: published as a pre-release and withdrawn; games given it are still known.
HELIXSR_DLL_DIGESTS = frozenset({
    *(release["dll_sha256"] for release in HELIXSR_REVIEWED.values()),
    "d9fc3ad6b3e3a47cf7ecbe8e8e7ad11c6c320ae295e8feed79303aabd0bed993",  # v1.9.0
})
HELIXSR_RELEASES_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases?per_page=50"
#: GitHub's answer for 50 releases with their notes is well under this.
_RELEASES_LIMIT = 4 * 1024 * 1024
#: The release archive: ``HelixSR-1.9.3.zip``, ``HelixSR-1.9.0.2.zip``. A
#: version follows the dash, so ``HelixSR-Scaler-1.0.6.zip`` is not one.
_RELEASE_ARCHIVE = re.compile(r"HelixSR-[0-9][0-9A-Za-z._-]*\.zip")
HELIXSR_DLL = "amd_fidelityfx_dx12.dll"
#: Since 2.0 the release keeps HelixSR's DLL, its helixsr.ini and the DLSS
#: frame generation the setup builds in this folder; earlier releases keep
#: the DLL at the top of the release.
HELIXSR_BUILD_FOLDER = "HelixSR-fsrfg"
HELIXSR_SETUP = "helixsr-setup.sh"
HELIXSR_MARKER = ".bc250-archive-sha256"
HELIXSR_DLL_MARKER = ".bc250-dll-sha256"
#: The network as two files beside the DLL: how releases before 1.7 kept it.
HELIXSR_NETWORK_FILES = ("helixsr_weights.bin", "helixsr_kernels.pak")
#: The setup appends the network to HelixSR's DLL and ends it with this
#: footer: magic, then three little-endian u64 (weights size, kernels size,
#: format), as its helixsr_setup.py ``embed`` writes it.
HELIXSR_EMBED_MAGIC = b"HXSRNET1"
_EMBED_FOOTER = 32
#: Where 1.7 and newer leave the built DLL's helixsr.ini, with its comments.
HELIXSR_DROP_IN = "fsr3-drop-in"
HELIXSR_LOG = "helixsr.log"
DLSS_LICENSE = "https://github.com/NVIDIA/DLSS/blob/v310.7.0/LICENSE.txt"
#: NVIDIA's nvngx_dlss.dll 310.7.0, the one HelixSR's setup builds from
#: (DLSS_SHA256 in its helixsr_setup.py). OptiScaler Client pins the same file.
DLSS_DLL_SHA256 = "be6e434a94ca32499515eb62ca0e6c274526055d568d0426e4c652dcdfb6ee6e"
DLSS_DLL_SIZE = 58_977_904
DLSS_DLL = "nvngx_dlss.dll"
#: Where HelixSR's setup itself downloads it from (DLSS_URL in helixsr_setup.py).
DLSS_DLL_URL = "https://raw.githubusercontent.com/NVIDIA/DLSS/v310.7.0/lib/Windows_x86_64/rel/nvngx_dlss.dll"

#: The FSR 3.1 DLLs HelixSR stands in for. In a folder that has both, the
#: upscaler DLL is the one replaced.
UPSCALER_DLL = "amd_fidelityfx_upscaler_dx12.dll"
LOADER_DLL = "amd_fidelityfx_dx12.dll"
_FSR_DLLS = (UPSCALER_DLL, LOADER_DLL)

#: A game folder is walked this deep and this wide, no further: Unreal games
#: keep the DLL six or seven folders down, and nothing needs more.
_SCAN_DEPTH = 10
_SCAN_ENTRY_LIMIT = 200_000


def _data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".local" / "share"


def helixsr_root() -> Path:
    return _data_home() / "bc250-control-center" / "helixsr"


def _version(tag: str) -> tuple[int, ...] | None:
    """``v1.8.1`` -> (1, 8, 1); None for a tag that is not a plain version."""
    parts = str(tag).removeprefix("v").split(".")
    if not 2 <= len(parts) <= 4 or not all(part.isdigit() and len(part) <= 4 for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _older(given: str, version: str) -> bool:
    """A game given ``given`` has an older release than ``version``; a
    version that cannot be read (a record from before versions) is older."""
    return (_version(given) or ()) < (_version(version) or ())


def _releases_path() -> Path:
    """GitHub's release list as Check for new releases saved it."""
    return helixsr_root() / "releases.json"


def _selection_path() -> Path:
    return helixsr_root() / "selection.json"


def _published_release(entry: dict) -> dict | None:
    """One release from GitHub's list, if it can be installed here.

    It needs a plain version tag no older than HELIXSR_OLDEST and exactly one
    ``HelixSR-<version>.zip`` asset whose SHA-256 GitHub published. That digest
    is what the terminal checks the download against. Since 1.9 a release also
    carries ``HelixSR-Scaler-*.zip``, a separate desktop app: it is not the
    release archive and does not count.
    """
    if not isinstance(entry, dict) or entry.get("draft"):
        return None
    tag = str(entry.get("tag_name") or "")
    version = _version(tag)
    if version is None or version < HELIXSR_OLDEST or not tag.startswith("v"):
        return None
    archives = [
        asset for asset in entry.get("assets") or ()
        if isinstance(asset, dict) and _RELEASE_ARCHIVE.fullmatch(str(asset.get("name") or ""))
    ]
    if len(archives) != 1:
        return None
    asset = archives[0]
    name = str(asset["name"])
    digest = str(asset.get("digest") or "").removeprefix("sha256:").lower()
    size = asset.get("size")
    if (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
            or not isinstance(size, int) or size <= 0
            or not all(c.isalnum() or c in "._-" for c in name)):
        return None
    return {"tag": tag, "archive": name, "sha256": digest, "size": size,
            "prerelease": bool(entry.get("prerelease"))}


def helixsr_releases() -> list[dict]:
    """The releases on offer, newest first.

    The reviewed ones always; the ones Check for new releases found on
    GitHub on top. A release reviewed here keeps its reviewed digests: if
    GitHub now lists another archive under its tag, the download is refused.
    A release GitHub no longer lists (withdrawn) is not offered.
    """
    releases = {tag: {"tag": tag, **entry, "prerelease": False, "reviewed": True}
                for tag, entry in HELIXSR_REVIEWED.items()}
    listed = _read_json(_releases_path(), {}).get("releases")
    if isinstance(listed, list):
        found = {}
        for entry in listed[:200]:
            release = _published_release(entry)
            if release is not None:
                found.setdefault(release["tag"], release)
        for tag, release in found.items():
            if tag in releases:
                releases[tag]["prerelease"] = release["prerelease"]
            else:
                releases[tag] = {**release, "dll_sha256": "", "reviewed": False}
        # GitHub's list is the truth about what can still be downloaded.
        releases = {tag: release for tag, release in releases.items() if tag in found}
    rows = [
        {**release, "version": tag.removeprefix("v"), "default": tag == HELIXSR_TAG}
        for tag, release in releases.items()
    ]
    return sorted(rows, key=lambda release: _version(release["tag"]), reverse=True)


def helixsr_release(tag: str | None = None) -> dict:
    """The release with ``tag``, by default the one the user picked.

    A pick that is no longer on offer falls back to the default release.
    """
    wanted = tag if tag is not None else _read_json(_selection_path(), {}).get("tag")
    releases = {release["tag"]: release for release in helixsr_releases()}
    if wanted in releases:
        return releases[wanted]
    if HELIXSR_TAG in releases:
        return releases[HELIXSR_TAG]
    return {"tag": HELIXSR_TAG, "version": HELIXSR_VERSION, **HELIXSR_REVIEWED[HELIXSR_TAG],
            "prerelease": False, "reviewed": True, "default": True}


def select_helixsr_release(tag: str) -> dict:
    """Pick the release Install/Update brings in. Nothing is downloaded here."""
    tag = str(tag or "").strip()
    if tag not in {release["tag"] for release in helixsr_releases()}:
        raise ValueError("This HelixSR release is not on offer.")
    _write_json(_selection_path(), {"tag": tag})
    return {"tag": tag, "version": tag.removeprefix("v")}


def helixsr_url(release: dict) -> str:
    return f"{HELIXSR_REPOSITORY}/releases/download/{release['tag']}/{release['archive']}"


def helixsr_directory() -> Path:
    return helixsr_root() / helixsr_release()["version"]


def helixsr_dll_folder(directory: Path | None = None) -> Path:
    """Where the release keeps HelixSR's DLL: HELIXSR_BUILD_FOLDER since 2.0."""
    directory = helixsr_directory() if directory is None else directory
    built = directory / HELIXSR_BUILD_FOLDER
    return built if (built / HELIXSR_DLL).is_file() else directory


def _digests_path() -> Path:
    """The digest of every HelixSR DLL installed here, as downloaded."""
    return helixsr_root() / "dll-digests.txt"


def _known_digests() -> frozenset[str]:
    """Reviewed DLLs, plus the ones of releases installed from GitHub's list."""
    try:
        lines = _digests_path().read_text(encoding="ascii").split()
    except (OSError, ValueError):
        lines = []
    recorded = {
        line.lower() for line in lines[:1000]
        if len(line) == 64 and all(c in "0123456789abcdef" for c in line.lower())
    }
    return HELIXSR_DLL_DIGESTS | recorded


def helixsr_cache() -> Path:
    """Upstream's own cache: portable Python, numpy and the shader compiler."""
    return _data_home() / "HelixSR"


def _records_path() -> Path:
    return helixsr_root() / "games.json"


def _scan_path() -> Path:
    return helixsr_root() / "scan.json"


def _folders_path() -> Path:
    """Game folders the user added by hand: games Steam does not know."""
    return helixsr_root() / "folders.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _embedded_size(handle, size: int) -> int:
    """Bytes the setup appended to a HelixSR DLL (its network), 0 for none."""
    if size < _EMBED_FOOTER:
        return 0
    handle.seek(size - _EMBED_FOOTER)
    footer = handle.read(_EMBED_FOOTER)
    if footer[:len(HELIXSR_EMBED_MAGIC)] != HELIXSR_EMBED_MAGIC:
        return 0
    weights, kernels, _format = struct.unpack("<QQQ", footer[len(HELIXSR_EMBED_MAGIC):])
    appended = _EMBED_FOOTER + weights + kernels
    # A footer that claims more than the file holds is not the setup's.
    return appended if appended <= size else 0


def _dll_digest(path: Path) -> str:
    """SHA-256 of a DLL as released: the network the setup appended is left out."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        remaining = size - _embedded_size(handle, size)
        handle.seek(0)
        while remaining > 0:
            block = handle.read(min(1 << 20, remaining))
            if not block:
                break
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _has_embedded_network(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return _embedded_size(handle, os.fstat(handle.fileno()).st_size) > 0
    except OSError:
        return False


def _carries_network(dll: Path) -> bool:
    """HelixSR's DLL has its network: appended to it, or as the two older files."""
    return _has_embedded_network(dll) or all(
        _nonempty(dll.parent / name) for name in HELIXSR_NETWORK_FILES
    )


def _is_helixsr(path: Path, digests: frozenset[str] | None = None) -> bool:
    known = _known_digests() if digests is None else digests
    try:
        return path.is_file() and not path.is_symlink() and _dll_digest(path) in known
    except OSError:
        return False


def _backup_for(path: Path) -> Path:
    """``x.dll`` -> ``x.original.dll``, the name upstream's README uses."""
    return path.with_name(f"{path.stem}.original{path.suffix}")


def _wine_candidates(home: Path) -> list[Path]:
    """Proton/Wine builds for the setup's shader compiler.

    First the ones upstream's setup looks for, in its order; then Proton in
    every other Steam library and installation: Flatpak Steam, Snap Steam
    (Ubuntu), a library on a second drive. Upstream knows only the native
    paths, so the terminal hands it one of these as ``wine`` on PATH.
    """
    found: list[Path] = []

    def add(paths) -> None:
        for path in paths:
            if path not in found:
                found.append(path)

    for pattern in (
        ".local/share/Steam/steamapps/common/Proton*/files/bin/wine",
        ".steam/steam/steamapps/common/Proton*/files/bin/wine",
        ".local/share/Steam/compatibilitytools.d/*/files/bin/wine",
        ".steam/root/compatibilitytools.d/*/files/bin/wine",
    ):
        try:
            add(sorted(home.glob(pattern)))
        except OSError:
            continue
    for library in steam_libraries(home):
        try:
            add(sorted(library.glob("steamapps/common/Proton*/files/bin/wine"), reverse=True))
            add(sorted(library.glob("compatibilitytools.d/*/files/bin/wine"), reverse=True))
        except OSError:
            continue
    return found


def wine_available(home: Path | None = None) -> bool:
    """Whether the setup can run its shader compiler (Proton or Wine)."""
    if any(os.access(path, os.X_OK) for path in _wine_candidates(home or Path.home())):
        return True
    return shutil.which("wine") is not None


# ---------------------------------------------------------------- records


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


def _records() -> dict[str, dict]:
    records = _read_json(_records_path(), {})
    return {
        str(appid): record for appid, record in records.items()
        if isinstance(record, dict) and isinstance(record.get("files"), list)
    }


def _record_state(record: dict) -> str:
    """``installed``: HelixSR is in place; ``restored``: the game put its own
    file back (an update or a file check), so only the backup is left;
    ``missing``: the game's folders are gone (uninstalled or moved)."""
    files = [Path(str(entry.get("path") or "")) for entry in record.get("files") or ()]
    if files and not any(path.parent.is_dir() for path in files):
        return "missing"
    if files and all(_is_helixsr(path) for path in files):
        return "installed"
    return "restored"


def _network_missing(dlls: list[Path]) -> bool:
    """HelixSR is in place but without its network (not appended to the DLL,
    no network files beside it): it would only do its simple upscale.
    Update HelixSR gives it the built DLL again."""
    return any(not _carries_network(dll) for dll in dlls)


def _network_files(source: Path) -> tuple[str, ...]:
    """The network files to copy beside HelixSR: none once its DLL carries it."""
    return () if _has_embedded_network(source / HELIXSR_DLL) else HELIXSR_NETWORK_FILES


# ---------------------------------------------------------------- scanning


def _fsr_folders(install: Path, dlss: list[Path] | None = None) -> list[Path]:
    """Every file HelixSR should replace in a game: one per folder.

    A folder with the FSR 3.1 upscaler DLL gets that one replaced; a folder
    with only the loader DLL gets the loader. Links are never followed.
    ``dlss`` collects, on the same walk, NVIDIA DLSS DLLs the size of 310.7.0.

    Beside an OptiScaler.ini, OptiScaler's own folder (its FSR4 DLL, which
    OptiScaler Client keeps checksums of) and HelixSR's are not the game's:
    they are never searched. Those games take HelixSR through OptiScaler.
    """
    targets: list[Path] = []
    seen = 0
    stack: list[tuple[Path, int]] = [(install, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        names: dict[str, Path] = {}
        optiscaler = any(entry.name.lower() == OPTISCALER_INI.lower() for entry in entries)
        for entry in entries:
            seen += 1
            if seen > _SCAN_ENTRY_LIMIT:
                return sorted(targets)
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if optiscaler and entry.name.lower() in _OPTISCALER_OWN_FOLDERS:
                        continue
                    if depth < _SCAN_DEPTH:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.name.lower() in _FSR_DLLS:
                    names[entry.name.lower()] = Path(entry.path)
                elif (dlss is not None and entry.name.lower() == DLSS_DLL
                      and entry.stat(follow_symlinks=False).st_size == DLSS_DLL_SIZE):
                    dlss.append(Path(entry.path))
            except OSError:
                continue
        for wanted in _FSR_DLLS:
            if wanted in names:
                targets.append(names[wanted])
                break
    return sorted(targets)


def _game_folders(home: Path | None = None) -> list[dict]:
    """Steam's games, then the non-Steam games added to Steam (GOG, Epic, a
    folder copied by hand): their shortcuts name the game's folder. A
    shortcut to a folder that is already listed (a Steam game, or a folder
    added by hand) is left out."""
    games = installed_steam_game_folders(home)
    seen = {Path(game["path"]) for game in games}
    for entry in _folders().values():
        try:
            seen.add(Path(str(entry["path"])).resolve())
        except OSError:
            continue
    for game in steam_shortcut_game_folders(home):
        if Path(game["path"]) not in seen:
            seen.add(Path(game["path"]))
            games.append(game)
    return games


def _library_signature(folders: list[dict]) -> list[list[str]]:
    """What the last search saw: each game and when Steam last wrote its
    manifest (or, for a non-Steam game, its shortcuts), which an install,
    an update or a removal all change."""
    signature = []
    for game in folders:
        manifest = Path(game["path"]).parent.parent / f"appmanifest_{game['appid']}.acf"
        try:
            stamp = str(game.get("stamp") or manifest.stat().st_mtime_ns)
        except OSError:
            stamp = ""
        signature.append([str(game["appid"]), str(game["path"]), stamp])
    return sorted(signature)


def refresh_helixsr_scan(*, home: Path | None = None) -> bool:
    """Search again only when the Steam library changed since the last search.

    Cheap when nothing changed (the manifests are only stat'ed), so the
    state read can call it every time: a game installed, updated or removed
    in Steam shows up without pressing Find FSR 3.1 games.
    """
    folders = _game_folders(home)
    scan = _read_json(_scan_path(), {})
    if isinstance(scan, dict) and scan.get("library") == _library_signature(folders):
        return False
    scan_helixsr_games(home=home, folders=folders)
    return True


def scan_helixsr_games(*, home: Path | None = None, folders: list[dict] | None = None) -> list[dict]:
    """Installed games (Steam's and non-Steam shortcuts) that ship an FSR 3.1
    DLL. Read-only; cached."""
    games = []
    sized: list[Path] = []
    folders = _game_folders(home) if folders is None else folders
    for game in folders:
        targets = _fsr_folders(Path(game["path"]), sized)
        if targets:
            games.append({
                "appid": game["appid"],
                "name": game["name"],
                "path": str(game["path"]),
                "files": [str(path) for path in targets],
            })
    # A game that ships NVIDIA's DLSS 310.7.0 spares its download: one copy
    # with the right digest is enough, and the terminal checks it again.
    dlss = next((str(path) for path in sized if _sha256_or_empty(path) == DLSS_DLL_SHA256), "")
    try:
        _write_json(_scan_path(), {"time": int(time.time()), "games": games, "dlss": dlss,
                                   "library": _library_signature(folders)})
    except OSError:
        pass
    return games


def _sha256_or_empty(path: Path) -> str:
    try:
        return _sha256(path)
    except OSError:
        return ""


# ---------------------------------------------------------------- folders
#
# Games outside Steam (GOG, Epic through Heroic, Lutris, a folder copied by
# hand) have no app manifest to find them by. The user picks the game's
# folder instead; it is searched exactly like a Steam game's, and from then
# on the game is a row like any other, with the same install, backup and
# removal. Its id is "folder-" and a digest of the path, so it can never
# collide with a Steam app id.

FOLDER_PREFIX = "folder-"
#: Non-Steam games added to Steam: their shortcut's id, see steam_shortcut_game_folders.
SHORTCUT_PREFIX = "shortcut-"


def _folder_id(path: Path) -> str:
    return FOLDER_PREFIX + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _folders() -> dict[str, dict]:
    folders = _read_json(_folders_path(), {})
    return {
        str(key): value for key, value in folders.items()
        if str(key).startswith(FOLDER_PREFIX) and isinstance(value, dict) and value.get("path")
    }


def add_helixsr_folder(path: str) -> dict:
    """Add a game folder from outside Steam, if it ships an FSR 3.1 DLL."""
    text = str(path or "").strip()
    if not text:
        raise ValueError("Choose the game's folder.")
    folder = Path(text).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise RuntimeError("That folder does not exist.")
    folder = folder.resolve()
    # The search stops after a fixed number of entries, so a whole drive or
    # home folder would end half searched: the game's own folder is wanted.
    if folder == Path(folder.anchor) or folder == Path.home().resolve():
        raise RuntimeError("Choose the game's own folder, not a whole drive or your home folder.")
    targets = _fsr_folders(folder)
    if not targets:
        raise ActionNeeded("No FSR 3.1 DLL was found in this game. HelixSR replaces amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_dx12.dll.")
    key = _folder_id(folder)
    folders = _folders()
    folders[key] = {"name": folder.name, "path": str(folder), "files": [str(t) for t in targets]}
    _write_json(_folders_path(), folders)
    return {"game": folder.name, "id": key, "files": [str(t) for t in targets]}


def forget_helixsr_folder(key: str) -> dict:
    """Take a folder off the list; HelixSR must not be in it any more."""
    key = str(key or "").strip()
    if key.startswith(OPTI_FOLDER_PREFIX):
        return _forget_optiscaler_folder(key)
    folders = _folders()
    if key not in folders:
        raise RuntimeError("This folder is not on the list.")
    if key in _records():
        raise RuntimeError("Remove HelixSR from this game first, so it gets its own FSR file back.")
    entry = folders.pop(key)
    _write_json(_folders_path(), folders)
    return {"game": str(entry.get("name") or key)}


def _record_folder(record: dict) -> str:
    """The game's folder: where it was installed, or what its files share."""
    if record.get("install"):
        return str(record["install"])
    parents = [str(Path(str(entry.get("path") or "")).parent) for entry in record.get("files") or ()]
    try:
        return os.path.commonpath(parents) if parents else ""
    except ValueError:
        return parents[0]


def helixsr_games(*, optiscaler: bool = True) -> list[dict]:
    """One row per game: recorded installs first, then the last scan's finds.

    ``optiscaler`` also offers the games where OptiScaler is in place; the
    ones already routed to HelixSR are listed either way.
    """
    records = _records()
    version = helixsr_release()["version"]
    rows: list[dict] = []
    for appid, record in records.items():
        rows.append({
            "appid": appid,
            "kind": "game",
            "name": str(record.get("name") or appid),
            "state": _record_state(record),
            "network_missing": _record_state(record) == "installed" and _network_missing(
                [Path(str(entry.get("path") or "")) for entry in record["files"]]
            ),
            "files": [str(entry.get("path") or "") for entry in record["files"]],
            "path": _record_folder(record),
            "version": str(record.get("version") or ""),
            # Given another release; update_helixsr_game brings it here.
            "outdated": str(record.get("version") or "") != version,
            "older": _older(str(record.get("version") or ""), version),
        })
    scan = _read_json(_scan_path(), {})
    for game in scan.get("games") or ():
        if not isinstance(game, dict):
            continue
        appid = str(game.get("appid") or "")
        if not appid or appid in records:
            continue
        files = [str(path) for path in game.get("files") or () if Path(str(path)).is_file()]
        if not files:
            continue
        rows.append({
            "appid": appid,
            "kind": "game",
            "name": str(game.get("name") or appid),
            "state": "available",
            "files": files,
            "path": str(game.get("path") or ""),
        })
    for key, entry in _folders().items():
        if key in records:
            continue
        files = [str(path) for path in entry.get("files") or () if Path(str(path)).is_file()]
        if not files:
            continue
        rows.append({
            "appid": key,
            "kind": "game",
            "name": str(entry.get("name") or key),
            "state": "available",
            "files": files,
            "folder": str(entry.get("path") or ""),
            "path": str(entry.get("path") or ""),
        })
    rows.extend(optiscaler_rows(available=optiscaler))
    order = {"installed": 0, "restored": 1, "missing": 1, "available": 2}
    return sorted(rows, key=lambda row: (order[row["state"]], row["name"].lower(), row["kind"]))


# ---------------------------------------------------------------- OptiScaler
#
# OptiScaler (installed per game by the FSR4 card's OptiScaler Client) can hand
# a game's DLSS, XeSS or FSR input to any FidelityFX upscaler DLL. Pointing it
# at HelixSR, as upstream's README describes, brings HelixSR to games that do
# not ship FSR 3.1. HelixSR goes into a folder of its own beside OptiScaler and
# OptiScaler.ini names it; nothing of OptiScaler or of the game is replaced.
#
# OptiScaler Client records the digest of every file it installed, the .ini
# included, and refuses to update or restore a game whose files changed. So
# the .ini is saved byte for byte first and put back byte for byte on removal,
# which leaves the client's records valid again.

OPTISCALER_INI = "OptiScaler.ini"
OPTISCALER_FOLDER = "HelixSR"
#: Folders beside OptiScaler.ini that belong to OptiScaler or to HelixSR.
_OPTISCALER_OWN_FOLDERS = frozenset({"optiscaler", OPTISCALER_FOLDER.lower()})
#: The name HelixSR's README uses for a second FidelityFX upscaler DLL.
SECOND_UPSCALER = "amd_fidelityfx_upscaler_dx12.amd.dll"
#: OptiScaler 10 calls its FidelityFX route (FSR 2.3, 3.1 and 4) "ffx"; older
#: releases, and HelixSR's README, call it "fsr31".
OPTISCALER_UPSCALER = "ffx"


def _optiscaler_path() -> Path:
    return helixsr_root() / ".optiscaler"


def _optiscaler_records() -> dict[str, dict]:
    records = _read_json(_optiscaler_path() / "games.json", {})
    return {str(key): value for key, value in records.items() if isinstance(value, dict)}


def _ini_get(text: str, section: str, key: str) -> str | None:
    current = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
        elif (current.lower() == section.lower() and "=" in stripped
              and stripped.split("=", 1)[0].strip().lower() == key.lower()):
            return stripped.split("=", 1)[1].strip()
    return None


def _ini_set(text: str, section: str, key: str, value: str, *, separator: str = "=") -> str:
    """Set one key in one section, as OptiScaler Client does; nothing else moves.

    ``separator`` keeps a file's own style: helixsr.ini writes ``Key = value``.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    line = f"{key}{separator}{value}"
    inside = found = written = False
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if inside and not written:
                # After the section's last line, not after the blank lines
                # that separate it from the next one.
                at = index
                while at > 0 and not lines[at - 1].strip():
                    at -= 1
                lines.insert(at, line)
                written = True
                index += 1
            inside = stripped[1:-1].lower() == section.lower()
            found = found or inside
        elif (inside and "=" in stripped
              and stripped.split("=", 1)[0].strip().lower() == key.lower()):
            lines[index] = line
            written = True
        index += 1
    if not found:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", f"[{section}]"]
    if not written:
        while inside and lines and not lines[-1].strip():
            lines.pop()
        lines.append(line)
    if lines and lines[-1].strip():
        lines.append("")
    return newline.join(lines)


def _windows_path(path: Path) -> str:
    """The path Proton's Wine sees: Z: is the Linux root."""
    return "Z:" + os.path.realpath(path).replace("/", "\\")


def _optiscaler_settings(folder: Path) -> dict[tuple[str, str], str]:
    return {
        ("Upscalers", "Dx12Upscaler"): OPTISCALER_UPSCALER,
        ("Libraries", "FfxDx12Path"): _windows_path(folder / LOADER_DLL),
        ("Libraries", "FfxDx12SRPath"): _windows_path(folder / UPSCALER_DLL),
    }


def _optiscaler_upscaler(root: Path, text: str) -> Path | None:
    """The FidelityFX upscaler OptiScaler loads now (the FSR4 DLL), if any."""
    configured = (_ini_get(text, "Libraries", "FfxDx12SRPath") or "auto").strip()
    folder = (_ini_get(text, "Libraries", "OptiDllPath") or "auto").strip()
    if configured.lower() == "auto":
        relative = (Path("OptiScaler") if folder.lower() == "auto" else Path(folder.replace("\\", "/"))) / UPSCALER_DLL
    elif ":" in configured or configured.startswith("/"):
        return None
    else:
        relative = Path(configured.replace("\\", "/"))
    if ".." in relative.parts:
        return None
    candidate = root / relative
    if candidate.is_dir():
        candidate = candidate / UPSCALER_DLL
    return candidate if candidate.is_file() and not _is_helixsr(candidate) else None


def _optiscaler_games() -> list[dict]:
    """Games with OptiScaler in place, from OptiScaler Client's list."""
    from .bc250_opticlient import opticlient_games, opticlient_state

    try:
        if not opticlient_state(games=False).get("current"):
            return []
        games = opticlient_games()
    except (OSError, ValueError, RuntimeError):
        return []
    found = []
    for game in games:
        adapter = str(game.get("adapter") or "")
        if not adapter or adapter == "unknown":
            continue
        found.append(game)
    return found


def _optiscaler_root(appid: str) -> tuple[dict, Path]:
    from .bc250_opticlient import opticlient_records

    appid = str(appid or "").strip()
    manual = _optiscaler_folders().get(appid)
    if manual is not None:
        root = Path(str(manual["root"]))
        if not (root / OPTISCALER_INI).is_file():
            raise RuntimeError("OptiScaler's settings file was not found in this game.")
        return {"appid": appid, "name": str(manual.get("name") or root.name)}, root
    game = next((g for g in _optiscaler_games() if str(g.get("appid")) == appid), None)
    if game is None:
        raise RuntimeError("OptiScaler is not installed in this game. Install it with the FSR4 OptiScaler Client first.")
    records = _read_json(opticlient_records() / "games.json", [])
    record = next(
        (r for r in records if isinstance(r, dict) and str(r.get("AppId") or "") == appid), None
    )
    install = Path(str((record or {}).get("InstallPath") or ""))
    root = install / str(game.get("location") or "")
    if not str(install) or not (root / OPTISCALER_INI).is_file():
        raise RuntimeError("OptiScaler's settings file was not found in this game.")
    return game, root


def _optiscaler_state(record: dict) -> str:
    """``installed`` while OptiScaler.ini still names the HelixSR folder."""
    root = Path(str(record.get("root") or ""))
    folder = root / OPTISCALER_FOLDER
    if not root.is_dir():
        return "missing"
    try:
        text = (root / OPTISCALER_INI).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "restored"
    pointed = _ini_get(text, "Libraries", "FfxDx12SRPath") == _windows_path(folder / UPSCALER_DLL)
    return "installed" if pointed and _is_helixsr(folder / UPSCALER_DLL) else "restored"


def optiscaler_rows(*, available: bool = True) -> list[dict]:
    """Games with OptiScaler: HelixSR routed through it, or ready to be."""
    records = _optiscaler_records()
    version = helixsr_release()["version"]
    rows = [
        {
            "appid": appid,
            "kind": "optiscaler",
            "name": str(record.get("name") or appid),
            "state": _optiscaler_state(record),
            "network_missing": _optiscaler_state(record) == "installed" and _network_missing(
                [Path(str(record.get("root") or "")) / OPTISCALER_FOLDER / UPSCALER_DLL]
            ),
            "files": [str(Path(str(record.get("root") or "")) / OPTISCALER_INI)],
            "path": str(record.get("root") or ""),
            "fsr4": bool(record.get("fsr4")),
            # A folder added by hand stays marked as one while HelixSR is in it.
            "folder": str(record.get("root") or "") if appid.startswith(OPTI_FOLDER_PREFIX) else "",
            "version": str(record.get("version") or ""),
            "outdated": str(record.get("version") or "") != version,
            "older": _older(str(record.get("version") or ""), version),
        }
        for appid, record in records.items()
    ]
    # Folders added by hand are listed either way, like games outside Steam.
    for key, entry in _optiscaler_folders().items():
        if key in records:
            continue
        rows.append({
            "appid": key,
            "kind": "optiscaler",
            "name": str(entry.get("name") or key),
            "state": "available",
            "files": [str(Path(str(entry["root"])) / OPTISCALER_INI)],
            "path": str(entry["root"]),
            "fsr4": False,
            "folder": str(entry["root"]),
        })
    if not available:
        return rows
    listed = set(records)
    for game in _optiscaler_games():
        appid = str(game.get("appid") or "")
        if not appid or appid in listed:
            continue
        listed.add(appid)
        rows.append({
            "appid": appid,
            "kind": "optiscaler",
            "name": str(game.get("name") or appid),
            "state": "available",
            "files": [],
            "path": str(game.get("path") or ""),
            "fsr4": False,
        })
    return rows


# OptiScaler put in a game by hand (or by another tool) has no OptiScaler
# Client record to find it by. The user picks the game's folder instead; the
# folder that holds OptiScaler.ini becomes the game's root and from then on it
# is handled exactly like a Client game: the HelixSR folder beside it, the
# .ini saved first and put back byte for byte.

OPTI_FOLDER_PREFIX = "optifolder-"


def _optiscaler_folders_path() -> Path:
    return _optiscaler_path() / "folders.json"


def _optiscaler_folders() -> dict[str, dict]:
    folders = _read_json(_optiscaler_folders_path(), {})
    if not isinstance(folders, dict):
        return {}
    return {
        str(key): value for key, value in folders.items()
        if str(key).startswith(OPTI_FOLDER_PREFIX) and isinstance(value, dict) and value.get("root")
    }


def _optiscaler_ini_folders(folder: Path) -> list[Path]:
    """Every folder under ``folder`` that holds an OptiScaler.ini; links are not followed."""
    found: list[Path] = []
    seen = 0
    stack: list[tuple[Path, int]] = [(folder, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > _SCAN_ENTRY_LIMIT:
                return sorted(found)
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < _SCAN_DEPTH and entry.name != OPTISCALER_FOLDER:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.name.lower() == OPTISCALER_INI.lower():
                    found.append(current)
            except OSError:
                continue
    return sorted(found)


def add_optiscaler_folder(path: str) -> dict:
    """Add a game whose OptiScaler was not installed by OptiScaler Client."""
    text = str(path or "").strip()
    if not text:
        raise ValueError("Choose the game's folder.")
    folder = Path(text).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise RuntimeError("That folder does not exist.")
    folder = folder.resolve()
    if folder == Path(folder.anchor) or folder == Path.home().resolve():
        raise RuntimeError("Choose the game's own folder, not a whole drive or your home folder.")
    roots = _optiscaler_ini_folders(folder)
    if not roots:
        raise RuntimeError("No OptiScaler.ini was found in this folder. Install OptiScaler in the game first.")
    if len(roots) > 1:
        raise RuntimeError("This folder has more than one OptiScaler.ini. Choose the folder of the one the game uses.")
    root = roots[0]
    if root.name.lower() == OPTISCALER_FOLDER.lower() and (root / HELIXSR_DLL).exists():
        raise RuntimeError("That is HelixSR's own folder. Choose the game's folder.")
    key = OPTI_FOLDER_PREFIX + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    folders = _optiscaler_folders()
    folders[key] = {"name": folder.name, "root": str(root)}
    _write_json(_optiscaler_folders_path(), folders)
    return {"game": folder.name, "id": key, "root": str(root)}


def _forget_optiscaler_folder(key: str) -> dict:
    folders = _optiscaler_folders()
    if key not in folders:
        raise RuntimeError("This folder is not on the list.")
    if key in _optiscaler_records():
        raise RuntimeError("Remove HelixSR from this game first, so OptiScaler gets its settings back.")
    entry = folders.pop(key)
    _write_json(_optiscaler_folders_path(), folders)
    return {"game": str(entry.get("name") or key)}


def install_helixsr_optiscaler(appid: str) -> dict:
    """Point a game's OptiScaler at HelixSR; FSR4 stays selectable beside it."""
    if not helixsr_state()["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    appid = str(appid or "").strip()
    records = _optiscaler_records()
    if appid in records:
        raise ActionNeeded("HelixSR is already recorded for this game. Remove it first, then add it again.")
    game, root = _optiscaler_root(appid)
    _refuse_running(root)
    folder = root / OPTISCALER_FOLDER
    if folder.exists() or folder.is_symlink():
        raise RuntimeError("This game already has a HelixSR folder that Control Center did not create. Remove it by hand first.")
    ini = root / OPTISCALER_INI
    original = ini.read_bytes()
    text = original.decode("utf-8", errors="surrogateescape")
    fsr4 = _optiscaler_upscaler(root, text)
    source = helixsr_dll_folder()
    backup = _optiscaler_path() / appid / OPTISCALER_INI
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    try:
        folder.mkdir()
        for name in (LOADER_DLL, UPSCALER_DLL):
            shutil.copyfile(source / HELIXSR_DLL, folder / name)
        for name in _network_files(source):
            shutil.copyfile(source / name, folder / name)
        settings = _release_ini()
        if fsr4 is not None:
            shutil.copyfile(fsr4, folder / SECOND_UPSCALER)
            settings = _ini_set(settings, "Forwarding", "UpscalerDll", SECOND_UPSCALER)
        settings = _settings_text(settings, helixsr_settings())
        (folder / "helixsr.ini").write_text(settings, encoding="utf-8")
        for (section, key), value in _optiscaler_settings(folder).items():
            text = _ini_set(text, section, key, value)
        written = text.encode("utf-8", errors="surrogateescape")
        staged = root / f".{OPTISCALER_INI}.bc250-helixsr"
        staged.write_bytes(written)
        os.replace(staged, ini)
        records[appid] = {
            "name": str(game.get("name") or appid),
            "root": str(root),
            "backup": str(backup),
            "written_sha256": hashlib.sha256(written).hexdigest(),
            "fsr4": fsr4 is not None,
            "version": helixsr_release()["version"],
        }
        _write_json(_optiscaler_path() / "games.json", records)
    except Exception:
        if ini.read_bytes() != original:
            ini.write_bytes(original)
        shutil.rmtree(folder, ignore_errors=True)
        (root / f".{OPTISCALER_INI}.bc250-helixsr").unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        raise
    return {"game": records[appid]["name"], "fsr4": fsr4 is not None}


def remove_helixsr_optiscaler(appid: str) -> dict:
    """Put OptiScaler.ini back exactly and remove the HelixSR folder."""
    appid = str(appid or "").strip()
    records = _optiscaler_records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR is not recorded for this game.")
    root = Path(str(record.get("root") or ""))
    _refuse_running(root)
    ini = root / OPTISCALER_INI
    backup = Path(str(record.get("backup") or ""))
    restored = "kept"
    if ini.is_file():
        current = ini.read_bytes()
        if hashlib.sha256(current).hexdigest() == record.get("written_sha256") and backup.is_file():
            # Untouched since: the saved file goes back byte for byte, so
            # OptiScaler Client recognises it again.
            staged = root / f".{OPTISCALER_INI}.bc250-helixsr"
            shutil.copyfile(backup, staged)
            os.replace(staged, ini)
            restored = "exact"
        elif _ini_get(current.decode("utf-8", errors="replace"), "Libraries", "FfxDx12SRPath") == \
                _windows_path(root / OPTISCALER_FOLDER / UPSCALER_DLL):
            # Changed in OptiScaler's own menu since: only HelixSR's three
            # values go back, every other setting stays.
            text = current.decode("utf-8", errors="surrogateescape")
            saved = backup.read_text(encoding="utf-8", errors="surrogateescape") if backup.is_file() else ""
            for section, key in _optiscaler_settings(root / OPTISCALER_FOLDER):
                text = _ini_set(text, section, key, _ini_get(saved, section, key) or "auto")
            ini.write_bytes(text.encode("utf-8", errors="surrogateescape"))
            restored = "settings"
    folder = root / OPTISCALER_FOLDER
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder)
    shutil.rmtree(backup.parent, ignore_errors=True)
    del records[appid]
    _write_json(_optiscaler_path() / "games.json", records)
    return {"game": str(record.get("name") or appid), "restored": restored}


def _refuse_running(folder: Path, proc: Path = Path("/proc")) -> None:
    """Refuse while a process runs from the game folder (Proton paths included)."""
    spellings = {str(folder).rstrip("/") + "/", os.path.realpath(folder).rstrip("/") + "/"}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.name.isdigit() or entry.name == str(os.getpid()):
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        command = command.replace("\\", "/")
        if any(spelling in command for spelling in spellings):
            raise ActionNeeded("Close this game before changing its files.")


# ---------------------------------------------------------------- state


def helixsr_state(*, machine: str | None = None) -> dict:
    """Read-only: the release, its network and every game's state."""
    release = helixsr_release()
    directory = helixsr_directory()
    try:
        marker = (directory / HELIXSR_MARKER).read_text(encoding="ascii").strip()
    except OSError:
        marker = ""
    installed = directory.exists()
    # A release from GitHub's list has no reviewed DLL digest: the terminal
    # recorded the one it unpacked, from the archive it checked.
    expected = release["dll_sha256"] or _recorded_digest(directory)
    current = bool(
        marker == release["sha256"]
        and expected
        and (directory / HELIXSR_SETUP).is_file()
        and _is_helixsr(helixsr_dll_folder(directory) / HELIXSR_DLL, frozenset({expected}))
    )
    network_ready = current and _carries_network(helixsr_dll_folder(directory) / HELIXSR_DLL)
    try:
        others = sorted(
            entry.name for entry in helixsr_root().iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
            and entry.name != release["version"]
        )
    except OSError:
        others = []
    supported = (machine or platform.machine()) in {"x86_64", "amd64", "AMD64"}
    if network_ready:
        state = "ready"
    elif current:
        state = "needs-network"
    elif installed:
        state = "invalid"
    elif others:
        # Another release is installed: an update when the picked one is
        # newer than all of them, otherwise an older one or a pre-release
        # picked on purpose.
        picked = _version(release["tag"]) or ()
        newer = all(picked > (_version(other) or ()) for other in others)
        state = "update-available" if newer else "other-version"
    else:
        state = "not-installed"
    if network_ready:
        try:
            refresh_helixsr_scan()
        except OSError:
            pass
    # Recorded games are listed even when the release folder is gone: they
    # still carry HelixSR and must stay removable.
    games = helixsr_games(optiscaler=network_ready)
    scaler_rows = helixsr_scaler_rows() if network_ready else _recorded_scaler_rows()
    return {
        "provider": "helixsr",
        "version": release["version"],
        "tag": release["tag"],
        "prerelease": release["prerelease"],
        "reviewed": release["reviewed"],
        # Every release on offer, newest first, for the version picker.
        "releases": [
            {key: entry[key] for key in ("tag", "version", "prerelease", "reviewed", "default")}
            for entry in helixsr_releases()
        ],
        "releases_checked": bool(_read_json(_releases_path(), {}).get("releases")),
        "repository": HELIXSR_REPOSITORY,
        "supported": supported,
        "installer_available": supported,
        "installed": installed,
        "current": current,
        "network_ready": network_ready,
        "state": state,
        "path": str(directory),
        "other_versions": others,
        "wine_available": wine_available(),
        "local_dlss": bool(local_dlss_candidates()),
        "games": games,
        # The release's bridge removes HelixSR Scaler again: games keep it in use.
        "installed_games": sum(1 for game in games if game["state"] != "available")
        + sum(1 for row in scaler_rows if row["state"] == "installed"),
        "scaler_supported": bool(current and network_ready and helixsr_scaler_supported(directory)),
        "fg_ready": bool(current and helixsr_fg_ready(directory)),
        "scaler_games": scaler_rows,
        "int8_supported": _reads_int8(release["tag"]),
        "fast_output_supported": _reads_fast_output(release["tag"]),
        "settings": helixsr_settings(),
        "settings_defaults": helixsr_defaults(),
        # Settings this release's helixsr.ini has and the form above does not
        # know yet, and HelixSR Scaler's own (its bridge's list).
        "settings_extra": helixsr_extra_settings() if current else [],
        "scaler_settings": helixsr_scaler_settings() if current else [],
        # The newest stable release on offer, when it is newer than this one.
        "newer": _newer_release(release) if current else None,
        "outdated_games": _outdated_games(games, scaler_rows),
    }


def _newer_release(release: dict) -> dict | None:
    """The newest release that is not a pre-release, if newer than ``release``."""
    mine = _version(release["tag"]) or ()
    for entry in helixsr_releases():
        if entry["prerelease"] or (_version(entry["tag"]) or ()) <= mine:
            continue
        return {key: entry[key] for key in ("tag", "version", "reviewed")}
    return None


def _outdated_games(games: list[dict], scaler_rows: list[dict]) -> int:
    """Games whose HelixSR is another release than the installed one."""
    return (sum(1 for game in games if game.get("state") == "installed" and game.get("outdated"))
            + sum(1 for row in scaler_rows if row.get("state") == "installed" and row.get("outdated")))


def _reads_int8(tag: str) -> bool:
    """Upscaling.Int8 is read by HelixSR 1.9 and newer; earlier releases skip it."""
    numbers = tuple(int(part) for part in re.findall(r"\d+", str(tag))[:2])
    return numbers >= (1, 9)


def _reads_fast_output(tag: str) -> bool:
    """Upscaling.FastOutput is read by HelixSR 2.0 and newer."""
    numbers = tuple(int(part) for part in re.findall(r"\d+", str(tag))[:2])
    return numbers >= (2, 0)


def _recorded_digest(directory: Path) -> str:
    try:
        digest = (directory / HELIXSR_DLL_MARKER).read_text(encoding="ascii").strip().lower()
    except (OSError, ValueError):
        return ""
    return digest if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest) else ""


def _nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


# ---------------------------------------------------------------- settings
#
# HelixSR reads helixsr.ini next to its DLL; every key has a default. The
# options a player is likely to touch are kept here once and written into
# every game that has HelixSR, on top of the release's own helixsr.ini so
# its comments stay. Keys this list does not know are never touched.

HELIXSR_INI = "helixsr.ini"

#: (section, key, kind, default, choices): ``kind`` is choice, bool or float.
HELIXSR_SETTINGS: tuple[tuple[str, str, str, object, tuple], ...] = (
    # 1.7 replaced Mode (off/game/override, always AMD's RCAS) with a choice of
    # filter and a switch for the game's slider; see _migrated_settings.
    ("Sharpening", "Sharpener", "choice", "off", ("off", "nvidia", "rcas")),
    ("Sharpening", "Sharpness", "float", 0.3, (0.0, 1.0)),
    ("Sharpening", "UseGameSlider", "bool", False, ()),
    ("Sharpening", "MotionAdaptive", "bool", True, ()),
    # Motion in output pixels per frame where the reduction starts and where
    # it is complete, and how much sharpening it takes away there.
    ("Sharpening", "MotionThreshold", "float", 2.0, (0.0, 64.0)),
    ("Sharpening", "MotionLimit", "float", 16.0, (0.0, 64.0)),
    ("Sharpening", "MotionReduction", "float", 0.6, (0.0, 1.0)),
    ("Upscaling", "NetworkResolution", "choice", "auto", ("auto", "fast", "full")),
    # 1.9.0 and newer; earlier releases ignore the key.
    ("Upscaling", "Int8", "choice", "auto", ("auto", "on", "off")),
    # 2.0.0 and newer: faster builds of the network's output kernels, same
    # image; off keeps the earlier ones. Earlier releases ignore the key.
    ("Upscaling", "FastOutput", "choice", "on", ("on", "off")),
    ("ModelE", "Network", "choice", "auto", ("auto", "nvidia", "main", "ultraperformance")),
    ("ModelE", "UseReactiveMask", "bool", False, ()),
    ("ModelE", "DilateDisplayMotionVectors", "bool", False, ()),
    ("ModelE", "InvertJitter", "bool", False, ()),
    ("ModelE", "InvertMotionVectors", "bool", False, ()),
    ("ModelE", "MotionVectorFrontEnd", "bool", False, ()),
    ("Compatibility", "WaveSize", "choice", "auto", ("auto", "32", "64")),
    ("Log", "Enabled", "bool", True, ()),
)


def _migrated_settings(saved: dict) -> dict:
    """Settings saved for 1.3, in the keys and values 1.7 and newer read.

    Mode used AMD's RCAS: "override" is RCAS at the saved strength, "game"
    the same following the game's slider.
    """
    saved = dict(saved)
    mode = str(saved.pop("Sharpening.Mode", "") or "").strip().lower()
    if mode and "Sharpening.Sharpener" not in saved:
        saved["Sharpening.Sharpener"] = "off" if mode == "off" else "rcas"
        if mode == "game":
            saved.setdefault("Sharpening.UseGameSlider", True)
    return saved


def _legacy_mode(values: dict[str, object]) -> str:
    """Sharpener and UseGameSlider as Mode, the key releases before 1.7 read."""
    if values["Sharpening.Sharpener"] == "off":
        return "off"
    return "game" if values["Sharpening.UseGameSlider"] else "override"


def _settings_path() -> Path:
    return helixsr_root() / "settings.json"


def _setting_id(section: str, key: str) -> str:
    return f"{section}.{key}"


def helixsr_defaults() -> dict[str, object]:
    values = {_setting_id(section, key): default for section, key, _kind, default, _choices in HELIXSR_SETTINGS}
    values.update(_extra_defaults())
    values.update({row["id"]: row["default"] for row in _scaler_rows_safely()})
    return values


# ------------------------------------------- settings a release adds

#: A key = value line of helixsr.ini; the value stops at a comment.
_INI_ENTRY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^;#\r\n]*?)\s*$")
#: "c = NVIDIA's light mode; full = ..." names the values a key takes.
_NAMED_VALUE = re.compile(r"(?:^|[\s;,(])([A-Za-z0-9][A-Za-z0-9.]*)\s+=\s")
#: "0.0 - 1.0" in a comment is the number's range.
_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)")
#: What may be written for a key the form does not know: one plain word.
_PLAIN_VALUE = re.compile(r"[A-Za-z0-9._-]{1,32}")
#: Sections the form leaves out. Frame generation runs only in HelixSR
#: Scaler, which writes [DlssFrameGeneration] from its own OptiScaler.ini at
#: every game start: its settings are the Scaler's (helixsr_scaler_settings).
_NOT_IN_FORM = frozenset({"DlssFrameGeneration"})


def _ini_entries(text: str) -> list[tuple[str, str, str, str]]:
    """(section, key, value, the comment above it) for every key in ``text``."""
    entries, section, comment = [], "", []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith((";", "#")):
            comment.append(line.lstrip(";# ").strip())
            continue
        if line.startswith("[") and line.endswith("]"):
            section, comment = line[1:-1].strip(), []
            continue
        match = _INI_ENTRY.match(line)
        if match and section:
            entries.append((section, match.group(1), match.group(2), " ".join(comment)))
        comment = []
    return entries


def _choices_in(comment: str, value: str) -> tuple[str, ...]:
    """The values a comment names: "a = ...; b = ..." or "...: a, b or c"."""
    named = [word for word in _NAMED_VALUE.findall(comment) if not word.replace(".", "").isdigit()]
    if len(named) < 2 and ":" in comment:
        tail = re.sub(r"\([^)]*\)", "", comment.rsplit(":", 1)[1])
        named = [word.strip(" .") for word in re.split(r",|\bor\b", tail)]
        named = [word for word in named if re.fullmatch(r"[A-Za-z0-9]+", word)]
    choices = tuple(dict.fromkeys(word.lower() for word in named))
    return choices if len(choices) >= 2 and value.lower() in choices else ()


def helixsr_extra_settings() -> list[dict]:
    """The keys this release's helixsr.ini has and HELIXSR_SETTINGS does not.

    Each with what its own comment says: a switch for true/false, a number
    (in the comment's range), one of the values the comment names, or a
    plain word. A new release brings its new settings to the form without a
    new version of Control Center; the text is HelixSR's own, in English.
    """
    known = {_setting_id(section, key) for section, key, _kind, _default, _choices in HELIXSR_SETTINGS}
    known.add("Sharpening.Mode")
    rows = []
    for section, key, value, comment in _ini_entries(_release_ini()):
        name = _setting_id(section, key)
        if name in known or section in _NOT_IN_FORM or not _PLAIN_VALUE.fullmatch(value):
            continue
        known.add(name)
        row = {"id": name, "section": section, "key": key, "help": comment[:400]}
        if value.lower() in {"true", "false"}:
            row.update(kind="bool", default=value.lower() == "true", choices=())
        elif re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            found = _RANGE.search(comment)
            low, high = (float(found.group(1)), float(found.group(2))) if found else (0.0, max(1.0, float(value) * 4))
            row.update(kind="float", default=float(value), choices=(min(low, high), max(low, high)))
        elif choices := _choices_in(comment, value):
            row.update(kind="choice", default=value.lower(), choices=choices)
        else:
            row.update(kind="text", default=value, choices=())
        rows.append(row)
    return rows


def _extra_defaults() -> dict[str, object]:
    return {row["id"]: row["default"] for row in _extra_rows_safely()}


def _extra_rows_safely() -> list[dict]:
    try:
        return helixsr_extra_settings()
    except OSError:
        return []


def _valid_extra(row: dict, value: object) -> object:
    if row["kind"] == "text":
        text = str(value).strip()
        if not _PLAIN_VALUE.fullmatch(text):
            raise ValueError(value)
        return text
    return _valid_setting(row["kind"], tuple(row["choices"]), value)


# ------------------------------------------- HelixSR Scaler's own settings


#: The bridge's literals by (path, size, mtime): it is parsed once per release.
_BRIDGE_LITERALS: dict[tuple, dict[str, object]] = {}


def _bridge_constant(name: str) -> object:
    """A literal from the installed release's bridge, read without running it."""
    import ast

    path = helixsr_directory() / HELIXSR_BRIDGE
    try:
        info = path.stat()
        key = (str(path), info.st_size, info.st_mtime_ns)
        if key not in _BRIDGE_LITERALS:
            literals: dict[str, object] = {}
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()):
                    try:
                        literals[node.targets[0].id] = ast.literal_eval(node.value)
                    except Exception:  # noqa: BLE001 - a downloaded file: any odd literal is skipped
                        continue
            _BRIDGE_LITERALS.clear()
            _BRIDGE_LITERALS[key] = literals
    except (OSError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    return _BRIDGE_LITERALS[key].get(name)


def helixsr_scaler_settings() -> list[dict]:
    """HelixSR Scaler's settings (in each game's OptiScaler.ini, [HelixSR]),
    as the release's bridge lists them: a release that adds one brings it."""
    allowed, defaults = _bridge_constant("SCALER_SETTINGS"), _bridge_constant("SCALER_DEFAULTS")
    if not isinstance(allowed, dict) or not isinstance(defaults, dict):
        return []
    rows = []
    for name, choices in allowed.items():
        if (not isinstance(name, str) or "." not in name or not isinstance(choices, (tuple, list)) or not choices
                or not all(isinstance(choice, str) and _PLAIN_VALUE.fullmatch(choice) for choice in choices)):
            continue
        default = str(defaults.get(name) or choices[0])
        rows.append({"id": f"Scaler:{name}", "name": name, "kind": "choice",
                     "default": default if default in choices else choices[0], "choices": tuple(choices)})
    return rows


def _scaler_rows_safely() -> list[dict]:
    try:
        return helixsr_scaler_settings()
    except OSError:
        return []


def _scaler_values(values: dict[str, object]) -> dict[str, str]:
    """The Scaler settings to send; QuickFlow runs only with the full preset."""
    sent = {row["name"]: str(values.get(row["id"], row["default"])) for row in _scaler_rows_safely()}
    if sent.get("HelixSR.FGPreset", "full") != "full" and "HelixSR.QuickFlow" in sent:
        sent["HelixSR.QuickFlow"] = "off"
    return sent


def _valid_setting(kind: str, choices: tuple, value: object) -> object:
    """The value in its type, or ValueError: nothing else reaches a game."""
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in {"true", "false"}:
            return str(value).strip().lower() == "true"
        raise ValueError(value)
    if kind == "float":
        number = round(float(value), 2)
        if not choices[0] <= number <= choices[1]:
            raise ValueError(value)
        return number
    text = str(value).strip().lower()
    if text not in choices:
        raise ValueError(value)
    return text


def helixsr_settings() -> dict[str, object]:
    """The saved settings over the defaults; anything unreadable is the default."""
    saved = _read_json(_settings_path(), {})
    values = helixsr_defaults()
    if not isinstance(saved, dict):
        return values
    saved = _migrated_settings(saved)
    for section, key, kind, _default, choices in HELIXSR_SETTINGS:
        name = _setting_id(section, key)
        if name in saved:
            try:
                values[name] = _valid_setting(kind, choices, saved[name])
            except (TypeError, ValueError):
                pass
    for row in _extra_rows_safely():
        if row["id"] in saved:
            try:
                values[row["id"]] = _valid_extra(row, saved[row["id"]])
            except (TypeError, ValueError):
                pass
    for row in _scaler_rows_safely():
        value = str(saved.get(row["id"], row["default"]))
        values[row["id"]] = value if value in row["choices"] else row["default"]
    return values


def _format_setting(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _settings_text(base: str, values: dict[str, object]) -> str:
    """``base`` (a helixsr.ini) with every known key set; the rest stays.

    Mode is written too, so a game still on a release before 1.7 sharpens as
    the settings say; newer releases ignore it.
    """
    text = base
    for section, key, _kind, _default, _choices in HELIXSR_SETTINGS:
        text = _ini_set(text, section, key, _format_setting(values[_setting_id(section, key)]),
                        separator=" = ")
    for row in _extra_rows_safely():
        if row["id"] in values:
            text = _ini_set(text, row["section"], row["key"], _format_setting(values[row["id"]]),
                            separator=" = ")
    return _ini_set(text, "Sharpening", "Mode", _legacy_mode(values), separator=" = ")


def _release_ini() -> str:
    """The release's commented helixsr.ini: 2.0 ships it beside the DLL in
    HELIXSR_BUILD_FOLDER, 1.7 to 1.9 write it beside the built DLL in
    fsr3-drop-in, and 1.3 shipped it at the top of the release."""
    directory = helixsr_directory()
    for path in (
        directory / HELIXSR_BUILD_FOLDER / HELIXSR_INI,
        directory / HELIXSR_DROP_IN / HELIXSR_INI,
        directory / HELIXSR_INI,
    ):
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return "; helixsr.ini - optional, next to the upscaler DLL. Every key has a default.\n"


def _write_settings(folder: Path, values: dict[str, object]) -> bool:
    """Write helixsr.ini in ``folder``; True when the file is new there."""
    path = folder / HELIXSR_INI
    created = not path.exists()
    base = _release_ini() if created else path.read_text(encoding="utf-8", errors="replace")
    _replace_text(path, _settings_text(base, values))
    return created


def _replace_text(path: Path, text: str) -> None:
    staged = path.parent / f".{path.name}.bc250-helixsr"
    staged.write_text(text, encoding="utf-8")
    os.replace(staged, path)


def save_helixsr_settings(values: dict) -> dict:
    """Keep the settings and write them into every game that has HelixSR.

    A game that is running is skipped and named; the next save reaches it.
    """
    if not isinstance(values, dict):
        raise ValueError("Invalid HelixSR settings.")
    clean = helixsr_settings()
    for section, key, kind, _default, choices in HELIXSR_SETTINGS:
        name = _setting_id(section, key)
        if name in values:
            try:
                clean[name] = _valid_setting(kind, choices, values[name])
            except (TypeError, ValueError):
                raise ValueError("Invalid HelixSR settings.") from None
    for row in helixsr_extra_settings():
        if row["id"] in values:
            try:
                clean[row["id"]] = _valid_extra(row, values[row["id"]])
            except (TypeError, ValueError):
                raise ValueError("Invalid HelixSR settings.") from None
    for row in helixsr_scaler_settings():
        if row["id"] in values:
            if str(values[row["id"]]) not in row["choices"]:
                raise ValueError("Invalid HelixSR settings.")
            clean[row["id"]] = str(values[row["id"]])
    if clean["Sharpening.MotionThreshold"] >= clean["Sharpening.MotionLimit"]:
        # HelixSR fades the sharpening between the two: the start comes first.
        raise ValueError("Invalid HelixSR settings.")
    _write_json(_settings_path(), clean)
    applied, skipped = 0, []
    records = _records()
    changed = False
    for appid, record in records.items():
        targets = [Path(str(entry.get("path") or "")) for entry in record.get("files") or ()]
        if not targets or not all(_is_helixsr(target) for target in targets):
            continue
        try:
            _refuse_running(Path(str(record.get("install") or targets[0].parent)))
        except RuntimeError:
            skipped.append(str(record.get("name") or appid))
            continue
        for entry, target in zip(record["files"], targets):
            if _write_settings(target.parent, clean):
                entry["created"] = [*entry.get("created", ()), HELIXSR_INI]
                changed = True
        applied += 1
    if changed:
        _write_json(_records_path(), records)
    for appid, record in _optiscaler_records().items():
        if _optiscaler_state(record) != "installed":
            continue
        root = Path(str(record.get("root") or ""))
        try:
            _refuse_running(root)
        except RuntimeError:
            skipped.append(str(record.get("name") or appid))
            continue
        _write_settings(root / OPTISCALER_FOLDER, clean)
        applied += 1
    # HelixSR Scaler keeps its settings in OptiScaler.ini: the bridge writes them.
    scaler = _scaler_values(clean)
    for appid, record in _scaler_records().items():
        if not scaler or _scaler_state(record) != "installed":
            continue
        folder = Path(str(record.get("folder") or ""))
        try:
            _refuse_running(folder)
            _run_bridge("settings-set", "--game", str(folder), "--values", json.dumps(scaler))
        except RuntimeError:
            skipped.append(str(record.get("name") or appid))
            continue
        applied += 1
    return {"settings": clean, "games": applied, "skipped": skipped}


# ---------------------------------------------------------------- terminal

def _wine_check() -> str:
    """Find Proton or Wine as the setup will, plus every Steam library."""
    candidates = " ".join(shlex.quote(str(path)) for path in _wine_candidates(Path.home()))
    return f'''bc250_wine=""
for bc250_candidate in "$HOME"/.local/share/Steam/steamapps/common/Proton*/files/bin/wine \\
    "$HOME"/.steam/steam/steamapps/common/Proton*/files/bin/wine \\
    "$HOME"/.local/share/Steam/compatibilitytools.d/*/files/bin/wine \\
    "$HOME"/.steam/root/compatibilitytools.d/*/files/bin/wine {candidates}; do
  if test -x "$bc250_candidate"; then bc250_wine="$bc250_candidate"; break; fi
done
test -n "$bc250_wine" || bc250_wine="$(command -v wine || true)"
test -n "$bc250_wine" || {{
  echo "ERROR: HelixSR's setup compiles its shaders through Proton or Wine, and neither was found."
  echo "Install Proton from Steam (any game set to Proton installs it), then retry."
  exit 69
}}'''


def local_dlss_candidates() -> list[Path]:
    """Copies of NVIDIA's DLSS 310.7.0 DLL already on this PC.

    OptiScaler Client downloads it from NVIDIA's GitHub, checked against the
    same SHA-256, and keeps it in its payload folder. Using that copy spares a
    second download; the terminal checks its digest again before using it,
    and HelixSR's setup downloads the DLL itself (after asking) otherwise.
    A game that ships the same DLL, found by the last game search, counts too.
    """
    from .bc250_opticlient import opticlient_records

    candidates = [opticlient_records() / "BC250" / "payload" / DLSS_DLL]
    scan = _read_json(_scan_path(), {})
    found = str(scan.get("dlss") or "") if isinstance(scan, dict) else ""
    if found:
        candidates.append(Path(found))
    return [path for path in candidates if path.is_file() and not path.is_symlink()]


def _shader_progress(work: str) -> str:
    """A line each time the setup compiles more shaders.

    Upstream compiles them through Wine, for several minutes on a BC-250; its
    temporary folder (TMPDIR, ours) holds a .cso per finished shader, so
    counting them shows the build is moving. How many there are depends on
    the release and the GPU (wave32 only, or wave64 as well), so no total.
    """
    return f'''( bc250_last=0; bc250_first=0
  # The sleep keeps no hold on the terminal: killed with the loop, it would
  # otherwise keep the output open (and the workflow unfinished) until it ends.
  while sleep 15 </dev/null >/dev/null 2>&1; do
    kill -0 "$$" 2>/dev/null || exit 0
    bc250_done=$(find {work} -name '*.cso' 2>/dev/null | wc -l)
    if [ "$bc250_done" -gt "$bc250_last" ]; then
      [ "$bc250_first" -gt 0 ] || bc250_first=$SECONDS
      bc250_elapsed=$((SECONDS - bc250_first))
      printf '[bc250] shaders compiled: %s (%d min %02d s)\\n' "$bc250_done" $((bc250_elapsed / 60)) $((bc250_elapsed % 60))
      bc250_last=$bc250_done
    fi
  done ) &
bc250_progress=$!'''


def _setup_block(target: str) -> str:
    """Build the network with upstream's setup, and nothing else.

    With system numpy present the setup uses it. Without it the setup would
    offer ``sudo <package manager>``; HELIXSR_FORCE_PORTABLE makes it use its
    portable Python in ~/.local/share/HelixSR instead, as it does on SteamOS.

    NVIDIA's DLSS DLL is always handed over with ``--dlss``: a copy already
    on this PC (OptiScaler Client's, or a game's) when its SHA-256 matches,
    otherwise the one this terminal downloads from NVIDIA's GitHub after the
    user says yes, checked the same way. ``--yes`` is never passed.

    Since 1.7 the setup goes on to its own list of games once the network is
    built. Control Center adds HelixSR to games itself and records every
    change, so the setup runs with no input: its list stops at the first
    question (end of input) and changes no game.
    """
    candidates = " ".join(shlex.quote(str(path)) for path in local_dlss_candidates())
    version = helixsr_release()["version"]
    return f'''bc250_portable=1
if command -v python3 >/dev/null 2>&1 && python3 -c 'import numpy, sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
  bc250_portable=0
fi
bc250_dlss_dir="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr-dlss.XXXXXX")"
bc250_dlss_args=()
for bc250_candidate in {candidates}; do
  test -f "$bc250_candidate" -a ! -L "$bc250_candidate" || continue
  cp -- "$bc250_candidate" "$bc250_dlss_dir/nvngx_dlss.dll" || continue
  if printf '%s  %s\\n' {DLSS_DLL_SHA256} "$bc250_dlss_dir/nvngx_dlss.dll" | sha256sum -c --status -; then
    echo "Using the copy of NVIDIA's DLSS 310.7.0 DLL already on this PC (checked by SHA-256):"
    echo "  $bc250_candidate"
    bc250_dlss_args=(--dlss "$bc250_dlss_dir/nvngx_dlss.dll")
    break
  fi
  echo "Skipping $bc250_candidate: it is not NVIDIA's DLSS 310.7.0 DLL."
  rm -f -- "$bc250_dlss_dir/nvngx_dlss.dll"
done
if test "${{#bc250_dlss_args[@]}}" -eq 0; then
  echo
  echo "HelixSR builds its network from NVIDIA's DLSS 310.7.0 DLL ({DLSS_DLL_SIZE / 1_000_000:.0f} MB), from NVIDIA's own GitHub."
  echo "License: {DLSS_LICENSE}"
  bc250_answer=""
  printf 'Download it now? [y/N] '
  read -r bc250_answer || bc250_answer=""
  case "$bc250_answer" in
    y|Y|yes|YES) ;;
    *)
      rm -rf -- "$bc250_dlss_dir"
      echo "Nothing was downloaded. HelixSR is installed; use Build network files when you want the network."
      exit 1 ;;
  esac
  bc250_fetch "$bc250_dlss_dir/nvngx_dlss.dll" {shlex.quote(DLSS_DLL_URL)}
  printf '%s  %s\\n' {DLSS_DLL_SHA256} "$bc250_dlss_dir/nvngx_dlss.dll" | sha256sum -c - || {{
    rm -rf -- "$bc250_dlss_dir"; echo "ERROR: the download is not NVIDIA's DLSS 310.7.0 DLL."; exit 29; }}
  bc250_dlss_args=(--dlss "$bc250_dlss_dir/nvngx_dlss.dll")
fi
echo
echo "Building HelixSR's network on this PC. The DLL stays under NVIDIA's license: {DLSS_LICENSE}"
echo "The network ends up inside HelixSR's DLL: it is for this PC only, never share or upload it."
echo "The shaders compile through Wine, for several minutes on a BC-250. The count below shows it is moving."
echo
# Upstream looks for Proton only in native Steam's folders, then for wine on
# PATH: the one found above (Flatpak or Snap Steam, another library) is that.
# A fixed place, kept: the setup writes this wine's path into dxc-wine.sh,
# which Build frame generation runs later. A temporary folder was gone by
# then, and frame generation failed with "wine: No such file or directory".
bc250_shim="${{XDG_DATA_HOME:-$HOME/.local/share}}/HelixSR/wine-shim"
mkdir -p -- "$bc250_shim"
ln -sfn -- "$bc250_wine" "$bc250_shim/wine"
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr-build.XXXXXX")"
# 2.0 would go on to DLSS frame generation, downloading NVIDIA's Streamline
# SDK and driver package after asking; with no input it would stop there.
# Build frame generation runs that part on its own (build_helixsr_fg_command).
bc250_fg_args=()
test ! -d {target}/{HELIXSR_BUILD_FOLDER} || bc250_fg_args=(--no-fg)
{_shader_progress('"$bc250_work"')}
if ! TMPDIR="$bc250_work" PATH="$bc250_shim:$PATH" HELIXSR_FORCE_PORTABLE="$bc250_portable" bash {target}/{HELIXSR_SETUP} "${{bc250_dlss_args[@]}}" "${{bc250_fg_args[@]}}" </dev/null; then
  kill "$bc250_progress" 2>/dev/null || true
  rm -rf -- "$bc250_dlss_dir" "$bc250_work"
  echo
  echo "The network was not built. HelixSR is installed; use Build network files to try again."
  exit 1
fi
kill "$bc250_progress" 2>/dev/null || true
rm -rf -- "$bc250_dlss_dir" "$bc250_work"
echo
echo "(The setup's own list of games above stops by design: Control Center adds HelixSR to games itself.)"
# 1.8 and newer append the network to the DLL (2.0 the one in its build
# folder); older releases write two files.
bc250_built={target}
test ! -f {target}/{HELIXSR_BUILD_FOLDER}/{HELIXSR_DLL} || bc250_built={target}/{HELIXSR_BUILD_FOLDER}
test "$(tail -c {_EMBED_FOOTER} "$bc250_built/{HELIXSR_DLL}" | head -c {len(HELIXSR_EMBED_MAGIC)})" = {HELIXSR_EMBED_MAGIC.decode()} \\
  || {{ test -s {target}/{HELIXSR_NETWORK_FILES[0]} && test -s {target}/{HELIXSR_NETWORK_FILES[1]}; }} || {{
  echo "ERROR: the setup finished without building the network."; exit 1; }}
echo
echo "OK: HelixSR {version} is ready. Add it to a game from Additional settings > Upscaling."'''


def _fetch_check() -> str:
    """``bc250_fetch FILE URL`` with curl or wget, and the tools both need."""
    return '''for bc250_command in sha256sum mktemp; do
  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }
done
if command -v curl >/dev/null 2>&1; then
  bc250_fetch() { curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$1" "$2"; }
elif command -v wget >/dev/null 2>&1; then
  bc250_fetch() { wget -q --show-progress -O "$1" "$2"; }
else
  echo "ERROR: curl or wget is required to download HelixSR."; exit 69
fi'''


def build_helixsr_install_command() -> str:
    """Download, verify and unpack the picked release, then build the network."""
    release = helixsr_release()
    root = shlex.quote(str(helixsr_root()))
    target = shlex.quote(str(helixsr_directory()))
    python = shlex.quote(sys.executable or "python3")
    label = " (pre-release)" if release["prerelease"] else ""
    if release["reviewed"]:
        check = f'''printf '%s  %s\\n' {release['dll_sha256']} "$bc250_dll" | sha256sum -c - >/dev/null || {{
  echo "ERROR: the HelixSR DLL in the archive is not the reviewed one."; exit 29; }}'''
        source = "Checking the reviewed SHA-256..."
    else:
        # Not reviewed here: the archive is the one GitHub lists for the
        # release. The DLL's digest is kept so games given it stay known.
        check = f'''test -f "$bc250_dll" || {{ echo "ERROR: the archive has no {HELIXSR_DLL}."; exit 29; }}
echo "This release is newer than the ones Control Center was reviewed with."'''
        source = "Checking the SHA-256 GitHub published for this release..."
    return f'''set -Eeuo pipefail
echo "== HelixSR {release['version']}{label} · DLSS Model E for FSR 3.1 games =="
echo "Source: {HELIXSR_REPOSITORY} ({release['tag']})"
echo "HelixSR is an independent project, not affiliated with NVIDIA or AMD."
test "$(uname -m)" = x86_64 || {{ echo "ERROR: HelixSR's setup runs on x86_64 Linux only."; exit 64; }}
{_fetch_check()}
bc250_python="$(command -v python3 || echo {python})"
{_wine_check()}
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
bc250_archive="$bc250_work/{release['archive']}"
echo "Downloading {release['archive']} ({release['size'] / 1_000_000:.1f} MB)..."
bc250_fetch "$bc250_archive" {shlex.quote(helixsr_url(release))}
echo "{source}"
printf '%s  %s\\n' {release['sha256']} "$bc250_archive" | sha256sum -c -
echo "Checking the archive layout and unpacking..."
# Every entry sits in one HelixSR-* folder (1.9.0.2's archive holds
# HelixSR-1.9.0), with no links and no way out of it.
bc250_top="$("$bc250_python" -I - "$bc250_archive" "$bc250_work" <<'BC250_UNZIP'
import re, stat, sys, zipfile
archive, destination = sys.argv[1:3]
with zipfile.ZipFile(archive) as bundle:
    tops = {{item.filename.split("/")[0] for item in bundle.infolist()}}
    if len(tops) != 1 or not re.fullmatch(r"HelixSR-[0-9][0-9A-Za-z._-]*", next(iter(tops))):
        sys.exit("ERROR: the archive is not one HelixSR folder.")
    for item in bundle.infolist():
        name = item.filename
        parts = name.split("/")
        if ".." in parts or name.startswith("/") or "\\\\" in name:
            sys.exit(f"ERROR: unexpected archive entry: {{name}}")
        if stat.S_ISLNK(item.external_attr >> 16):
            sys.exit(f"ERROR: the archive contains a link: {{name}}")
    bundle.extractall(destination)
print(next(iter(tops)))
BC250_UNZIP
)"
bc250_stage="$bc250_work/$bc250_top"
# 2.0 keeps the DLL in {HELIXSR_BUILD_FOLDER}; earlier releases at the top.
bc250_dll="$bc250_stage/{HELIXSR_DLL}"
test ! -f "$bc250_stage/{HELIXSR_BUILD_FOLDER}/{HELIXSR_DLL}" || bc250_dll="$bc250_stage/{HELIXSR_BUILD_FOLDER}/{HELIXSR_DLL}"
{check}
chmod +x "$bc250_stage/{HELIXSR_SETUP}"
test ! -f "$bc250_stage/setup/lib/model/launch_synth" || chmod +x "$bc250_stage/setup/lib/model/launch_synth"
printf '%s\\n' {release['sha256']} > "$bc250_stage/{HELIXSR_MARKER}"
sha256sum "$bc250_dll" | cut -d' ' -f1 > "$bc250_stage/{HELIXSR_DLL_MARKER}"
mkdir -p {root}
if test -L {target}; then echo "ERROR: refusing to replace a symlink at {target}."; exit 29; fi
bc250_previous=""
if test -e {target}; then
  bc250_previous="$(mktemp -d {root}/.previous.XXXXXX)"
  rmdir "$bc250_previous"
  mv -- {target} "$bc250_previous"
fi
mv -- "$bc250_stage" {target}
test -z "$bc250_previous" || rm -rf -- "$bc250_previous"
cat {target}/{HELIXSR_DLL_MARKER} >> {root}/{_digests_path().name}
for bc250_old in {root}/*; do
  test -d "$bc250_old" || continue
  test "$bc250_old" = {target} && continue
  echo "Removing the HelixSR $(basename "$bc250_old") copy it replaces."
  rm -rf -- "$bc250_old"
done
echo "OK: the HelixSR {release['version']} release is installed in {helixsr_directory()}."
{_setup_block(target)}
'''


def build_helixsr_network_command() -> str:
    """Build (or rebuild) the network of the installed release."""
    target = shlex.quote(str(helixsr_directory()))
    return f'''set -Eeuo pipefail
echo "== HelixSR {helixsr_release()['version']} · network =="
test -f {target}/{HELIXSR_SETUP} || {{ echo "ERROR: install HelixSR first."; exit 66; }}
{_fetch_check()}
{_wine_check()}
{_setup_block(target)}
'''


def build_helixsr_releases_command() -> str:
    """Save GitHub's list of HelixSR releases, for the version picker.

    Nothing is installed: the list only adds releases newer than the reviewed
    ones (pre-releases included) and drops the ones upstream withdrew. Only
    the tag, the pre-release flag and each asset's name, size and digest are
    kept.
    """
    root = shlex.quote(str(helixsr_root()))
    python = shlex.quote(sys.executable or "python3")
    return f'''set -Eeuo pipefail
echo "== HelixSR · releases =="
echo "Source: {HELIXSR_REPOSITORY}/releases"
{_fetch_check()}
bc250_python="$(command -v python3 || echo {python})"
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr-releases.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
if command -v curl >/dev/null 2>&1; then
  curl -fsSL --connect-timeout 20 --max-filesize {_RELEASES_LIMIT} -H 'Accept: application/vnd.github+json' \\
    -o "$bc250_work/releases.json" {shlex.quote(HELIXSR_RELEASES_API)}
else
  bc250_fetch "$bc250_work/releases.json" {shlex.quote(HELIXSR_RELEASES_API)}
fi
mkdir -p {root}
"$bc250_python" -I - "$bc250_work/releases.json" {root}/releases.json {_RELEASES_LIMIT} {shlex.quote(_RELEASE_ARCHIVE.pattern)} <<'BC250_RELEASES'
import json, os, re, sys, time
source, destination, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
archive = re.compile(sys.argv[4])
if os.path.getsize(source) > limit:
    sys.exit("ERROR: GitHub's answer is larger than expected.")
listed = json.load(open(source, encoding="utf-8"))
if not isinstance(listed, list):
    sys.exit("ERROR: GitHub did not answer with a list of releases.")
kept = []
for entry in listed:
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
    if not entry["draft"]:
        found = sum(1 for a in entry["assets"] if archive.fullmatch(a["name"]))
        print("  " + entry["tag_name"] + ("  (pre-release)" if entry["prerelease"] else "")
              + ("" if found == 1 else "  (no single HelixSR archive: not offered)"))
BC250_RELEASES
echo "OK: the version list is up to date. Pick a version in the HelixSR section, then Install or Update."
'''


def build_helixsr_remove_command() -> str:
    """Remove the release and upstream's cache. Games must be restored first."""
    root = shlex.quote(str(helixsr_root()))
    cache = shlex.quote(str(helixsr_cache()))
    return f'''set -Eeuo pipefail
echo "== Removing HelixSR =="
rm -rf -- {root}
if test -d {cache}; then
  echo "Removing HelixSR's setup cache (portable Python and shader compiler) in {helixsr_cache()}."
  rm -rf -- {cache}
fi
echo "OK: HelixSR was removed. Your games use their own FSR files."
'''


# ---------------------------------------------------------------- per game


def _game(appid: str) -> dict:
    appid = str(appid or "").strip()
    folder = _folders().get(appid)
    if folder is not None:
        path = Path(str(folder["path"]))
        if not path.is_dir():
            raise RuntimeError("That folder does not exist.")
        return {"appid": appid, "name": str(folder.get("name") or path.name), "path": str(path)}
    if appid.startswith(SHORTCUT_PREFIX):
        for game in steam_shortcut_game_folders():
            if game["appid"] == appid:
                return game
        raise RuntimeError("This game is no longer in Steam's non-Steam games.")
    if not appid.isdigit():
        raise ValueError("Invalid Steam app id.")
    for game in installed_steam_game_folders():
        if game["appid"] == appid:
            return game
    raise RuntimeError("This game is not installed in Steam.")


def install_helixsr_game(appid: str) -> dict:
    """Put HelixSR in a game: the original DLL is kept as ``*.original.dll``.

    All or nothing: if any step fails, every file already changed is put back.
    """
    state = helixsr_state()
    if not state["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    game = _game(appid)
    install = Path(game["path"])
    records = _records()
    if str(appid) in records:
        raise ActionNeeded("HelixSR is already recorded for this game. Remove it first, then add it again.")
    _refuse_running(install)
    targets = _fsr_folders(install)
    if not targets:
        raise ActionNeeded("No FSR 3.1 DLL was found in this game. HelixSR replaces amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_dx12.dll.")
    for target in targets:
        if _is_helixsr(target):
            raise ActionNeeded("HelixSR is already in this game, copied there by hand. Use Steam > Verify integrity of game files to put the game's own file back first.")
        if _backup_for(target).exists():
            raise ActionNeeded("This game already has an *.original.dll backup from an earlier manual install. Remove it by hand, or keep that install as it is.")
    source = helixsr_dll_folder()
    undo: list = []
    files: list[dict] = []
    try:
        for target in targets:
            folder = target.parent
            staged = folder / f".{target.name}.bc250-helixsr"
            shutil.copyfile(source / HELIXSR_DLL, staged)
            undo.append(lambda staged=staged: staged.unlink(missing_ok=True))
            backup = _backup_for(target)
            os.rename(target, backup)
            undo.append(lambda target=target, backup=backup: os.rename(backup, target))
            os.replace(staged, target)
            undo.append(lambda target=target: target.unlink(missing_ok=True))
            created = []
            for name in _network_files(source):
                destination = folder / name
                if not destination.exists():
                    created.append(name)
                shutil.copyfile(source / name, destination)
                if name in created:
                    undo.append(lambda destination=destination: destination.unlink(missing_ok=True))
            # The settings from the Upscaling tab. A helixsr.ini already
            # there (an earlier manual install) is left as it is.
            if not (folder / HELIXSR_INI).exists():
                _write_settings(folder, helixsr_settings())
                created.append(HELIXSR_INI)
                undo.append(lambda folder=folder: (folder / HELIXSR_INI).unlink(missing_ok=True))
            files.append({
                "path": str(target),
                "backup": str(backup),
                "created": created,
            })
        records[str(appid)] = {
            "name": game["name"], "install": str(install), "files": files,
            "version": helixsr_release()["version"],
        }
        _write_json(_records_path(), records)
    except Exception:
        for step in reversed(undo):
            try:
                step()
            except OSError:
                pass
        raise
    return {"game": game["name"], "files": [entry["path"] for entry in files]}


def remove_helixsr_game(appid: str) -> dict:
    """Put the game's own DLL back and remove what HelixSR added."""
    appid = str(appid or "").strip()
    records = _records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR is not recorded for this game.")
    files = [Path(str(entry.get("path") or "")) for entry in record["files"]]
    if record.get("install"):
        _refuse_running(Path(str(record["install"])))
    elif files:
        _refuse_running(Path(os.path.commonpath([str(path.parent) for path in files])))
    entries = []
    for entry in record["files"]:
        target = Path(str(entry.get("path") or ""))
        backup = Path(str(entry.get("backup") or _backup_for(target)))
        ours = _is_helixsr(target)
        # Checked for every folder before any is touched, so a refusal
        # leaves the game exactly as it was.
        if ours and not backup.is_file():
            raise RuntimeError("The game's original FSR file is missing. Use Steam > Verify integrity of game files instead.")
        entries.append((entry, target, backup, ours))
    kept: list[str] = []
    for entry, target, backup, ours in entries:
        if ours:
            os.replace(backup, target)
        elif backup.is_file():
            # The game already put its own file back (an update or a file
            # check); the old backup is left for the user to judge.
            kept.append(str(backup))
        for name in (*entry.get("created", ()), HELIXSR_LOG):
            if name in (*HELIXSR_NETWORK_FILES, HELIXSR_LOG, HELIXSR_INI):
                (target.parent / name).unlink(missing_ok=True)
    del records[appid]
    _write_json(_records_path(), records)
    return {"game": str(record.get("name") or appid), "kept": kept}


def _replace_file(source: Path, destination: Path) -> None:
    staged = destination.parent / f".{destination.name}.bc250-helixsr"
    shutil.copyfile(source, staged)
    os.replace(staged, destination)


def _update_network(source: Path, folder: Path) -> tuple[str, ...]:
    """The network beside HelixSR in ``folder`` as the release keeps it.

    A release whose DLL carries the network gets no separate files: the ones
    an earlier release left there are removed (HelixSR reads its own copy
    first, and an old kernel file is only dead weight), as upstream's own
    installer does. Returns the network files now in ``folder``.
    """
    names = _network_files(source)
    for name in HELIXSR_NETWORK_FILES:
        if name in names:
            _replace_file(source / name, folder / name)
        else:
            (folder / name).unlink(missing_ok=True)
    return names


def update_helixsr_game(appid: str) -> dict:
    """Give a game the HelixSR release installed here, in place.

    A game keeps the DLL it was given when the release is updated, and it
    keeps working. Updating replaces the DLL together with the network (1.3
    changed the kernel format, 1.7 moved the network into the DLL). The
    game's own FSR backup and OptiScaler.ini are not touched.
    """
    if not helixsr_state()["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    appid = str(appid or "").strip()
    source = helixsr_dll_folder()
    version = helixsr_release()["version"]
    records = _records()
    record = records.get(appid)
    if record is not None:
        targets = [Path(str(entry.get("path") or "")) for entry in record["files"]]
        if record.get("install"):
            _refuse_running(Path(str(record["install"])))
        elif targets:
            _refuse_running(Path(os.path.commonpath([str(path.parent) for path in targets])))
        # Checked for every folder before any is touched.
        if not targets or not all(_is_helixsr(target) for target in targets):
            raise RuntimeError("The game put its own FSR file back. Remove HelixSR from it, then add it again.")
        for entry, target in zip(record["files"], targets):
            _replace_file(source / HELIXSR_DLL, target)
            kept = _update_network(source, target.parent)
            # Network files this game no longer has are no longer ours to remove.
            entry["created"] = [
                name for name in entry.get("created", ())
                if name not in HELIXSR_NETWORK_FILES or name in kept
            ]
        record["version"] = version
        _write_json(_records_path(), records)
        return {"game": str(record.get("name") or appid), "version": version}
    records = _optiscaler_records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR is not recorded for this game.")
    root = Path(str(record.get("root") or ""))
    _refuse_running(root)
    if _optiscaler_state(record) != "installed":
        raise RuntimeError("OptiScaler in this game no longer uses HelixSR. Remove HelixSR from it, then add it again.")
    folder = root / OPTISCALER_FOLDER
    for name in (LOADER_DLL, UPSCALER_DLL):
        _replace_file(source / HELIXSR_DLL, folder / name)
    _update_network(source, folder)
    record["version"] = version
    _write_json(_optiscaler_path() / "games.json", records)
    return {"game": str(record.get("name") or appid), "version": version}


# ---------------------------------------------------------------- HelixSR Scaler
#
# HelixSR 2.0's own build of OptiScaler (GPL-3.0, shipped in the release) is
# the only way to its DLSS frame generation: OptiScaler Client's build does
# not know HelixSR as a frame-generation provider. Control Center drives it
# through the release's bridge, the command line HelixSR's own app uses, so
# the files and the records in each game are upstream's and either side can
# update or remove what the other installed. A game has one OptiScaler only:
# HelixSR Scaler is never put over OptiScaler Client's, nor next to HelixSR
# added as the FSR drop-in or through OptiScaler.

HELIXSR_BRIDGE = "setup/helixsr_bridge.py"
HELIXSR_SCALER = "helixsr-scaler"
HELIXSR_FG_FOLDER = "helixsr-fg"
#: What HelixSR Scaler's install leaves in the game's .exe folder.
SCALER_FILES = "HelixSR-Scaler.files"
#: NVIDIA's NGX core, the last file the frame-generation build adds.
_FG_BUILT = "_nvngx.dll"
#: Installing or removing copies a few hundred megabytes into a game folder.
_BRIDGE_TIMEOUT = 900


def _scaler_records_path() -> Path:
    return helixsr_root() / "scaler.json"


def _scaler_records() -> dict[str, dict]:
    records = _read_json(_scaler_records_path(), {})
    return records if isinstance(records, dict) else {}


def helixsr_scaler_supported(directory: Path | None = None) -> bool:
    """The installed release ships HelixSR Scaler and the bridge (2.0 and newer)."""
    directory = helixsr_directory() if directory is None else directory
    return bool(
        (directory / HELIXSR_BRIDGE).is_file()
        and (directory / HELIXSR_SCALER / "OptiScaler.dll").is_file()
        and (directory / HELIXSR_BUILD_FOLDER / HELIXSR_DLL).is_file()
    )


def helixsr_fg_ready(directory: Path | None = None) -> bool:
    """HelixSR's setup built DLSS frame generation into the release."""
    folder = helixsr_dll_folder(directory) / HELIXSR_FG_FOLDER
    return (folder / _FG_BUILT).is_file()


def _run_bridge(*arguments: str) -> dict:
    """One bridge command; its JSON answer, or its own error as RuntimeError."""
    directory = helixsr_directory()
    bridge = directory / HELIXSR_BRIDGE
    if not bridge.is_file():
        raise RuntimeError("This HelixSR release has no HelixSR Scaler. Install HelixSR 2.0 or newer.")
    python = shutil.which("python3") or sys.executable or "python3"
    try:
        result = subprocess.run(
            [python, "-I", str(bridge), str(directory), *arguments],
            capture_output=True, text=True, timeout=_BRIDGE_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("HelixSR's bridge did not finish in time.") from None
    answers = [line for line in result.stdout.splitlines() if line.lstrip().startswith("{")]
    try:
        payload = json.loads(answers[-1]) if answers else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict) or not payload.get("ok"):
        error = payload.get("error") if isinstance(payload, dict) else ""
        raise RuntimeError(str(error or result.stderr.strip() or "HelixSR's bridge failed."))
    return payload


def _steam_game(appid: str) -> dict:
    game = next((g for g in installed_steam_game_folders() if str(g["appid"]) == str(appid)), None)
    if game is None:
        raise RuntimeError("This Steam game was not found.")
    return game


def _scaler_state(record: dict) -> str:
    exe = Path(str(record.get("exe_folder") or ""))
    if not str(exe) or not exe.parent.is_dir():
        return "missing"
    return "installed" if (exe / SCALER_FILES).is_file() else "restored"


def helixsr_scaler_rows() -> list[dict]:
    """Every installed Steam game, with HelixSR Scaler's state in it.

    Read from Control Center's own record and the file HelixSR Scaler leaves
    in the game: the bridge, which scans every library, runs only on a click.
    """
    if not helixsr_scaler_supported():
        return []
    records = _scaler_records()
    rows: list[dict] = []
    seen: set[str] = set()
    for game in installed_steam_game_folders():
        appid = str(game["appid"])
        seen.add(appid)
        record = records.get(appid)
        rows.append({
            "appid": appid,
            "name": str(game["name"]),
            "state": _scaler_state(record) if record else "available",
            "frame_generation": bool(record and record.get("frame_generation") == "on"),
            "fg_possible": record.get("fg_possible") if record else None,
            "launch_options": str(record.get("launch_options") or "") if record else "",
            **_scaler_versions(record),
        })
    for appid, record in records.items():
        if appid not in seen:
            rows.append({"appid": appid, "name": str(record.get("name") or appid), "state": "missing",
                         "frame_generation": False, "fg_possible": None, "launch_options": ""})
    return rows


def _scaler_versions(record: dict | None) -> dict:
    """The release a game's HelixSR Scaler has, against the installed one,
    and the one its last update kept for going back."""
    if not record:
        return {"version": "", "outdated": False, "older": False, "previous": ""}
    given = str(record.get("version") or "")
    version = helixsr_release()["version"]
    return {"version": given, "outdated": given != version, "older": _older(given, version),
            "previous": str(record.get("previous") or "")}


def _recorded_scaler_rows() -> list[dict]:
    """Games given HelixSR Scaler, listed while the release cannot add it."""
    return [
        {"appid": appid, "name": str(record.get("name") or appid), "state": _scaler_state(record),
         "frame_generation": record.get("frame_generation") == "on", "fg_possible": record.get("fg_possible"),
         "launch_options": str(record.get("launch_options") or ""), **_scaler_versions(record)}
        for appid, record in _scaler_records().items()
    ]


def _refuse_native_game(folder: Path) -> None:
    """HelixSR Scaler goes next to a Windows .exe that runs through Proton.

    A native Linux game (Counter-Strike 2, Dota 2) has none, and the bridge
    only said "no game (.exe) found".
    """
    if not folder.is_dir():
        return
    has_exe = any(
        name.lower().endswith(".exe") for _root, _dirs, names in os.walk(folder) for name in names
    )
    if not has_exe:
        raise ActionNeeded(
            "This game runs natively on Linux: it has no Windows .exe. "
            "HelixSR only works with games that run through Proton."
        )


def _refuse_other_helixsr(appid: str, folder: Path) -> None:
    """One OptiScaler and one HelixSR per game."""
    if appid in _records():
        raise ActionNeeded("HelixSR is already in this game as the FSR drop-in. Remove it first.")
    if appid in _optiscaler_records():
        raise ActionNeeded("HelixSR is already in this game through its OptiScaler. Remove it first.")
    if _optiscaler_ini_folders(folder):
        raise ActionNeeded(
            "This game already has OptiScaler (OptiScaler Client's, for FSR4, or one added by hand). "
            "A game can only have one: remove that one first."
        )


def _scaler_result(appid: str, name: str, folder: Path, payload: dict) -> dict:
    game = payload.get("game") if isinstance(payload.get("game"), dict) else {}
    record = {
        "name": name,
        "folder": str(folder),
        "exe_folder": str(game.get("exe_folder") or ""),
        "scaler_dll": str(game.get("scaler_dll") or ""),
        "frame_generation": str(game.get("frame_generation") or "off"),
        "fg_possible": game.get("fg_possible"),
        "launch_options": str(game.get("launch_options") or ""),
        "version": str(game.get("version") or ""),
        # What the bridge keeps from the last update, for going back.
        "previous": str((game.get("previous") or {}).get("version") or "")
        if isinstance(game.get("previous"), dict) else "",
    }
    records = _scaler_records()
    records[appid] = record
    _write_json(_scaler_records_path(), records)
    return record


def install_helixsr_scaler(appid: str, *, frame_generation: bool = False) -> dict:
    """HelixSR Scaler into a Steam game, through the release's bridge."""
    appid = str(appid).strip()
    game = _steam_game(appid)
    folder = Path(game["path"])
    directory = helixsr_directory()
    if not helixsr_scaler_supported(directory):
        raise ActionNeeded("Install HelixSR 2.0 or newer first: earlier releases have no HelixSR Scaler.")
    if appid not in _scaler_records():
        _refuse_other_helixsr(appid, folder)
    if frame_generation and not helixsr_fg_ready(directory):
        raise ActionNeeded("Build HelixSR's frame generation first (Build frame generation, on the HelixSR card).")
    _refuse_native_game(folder)
    _refuse_running(folder)
    payload = _run_bridge(
        "install", "--game", str(folder), "--way", "scaler",
        "--scaler", str(directory / HELIXSR_SCALER), "--fg", "on" if frame_generation else "off",
    )
    record = _scaler_result(appid, str(game["name"]), folder, payload)
    result = {"game": str(game["name"]), "frame_generation": record["frame_generation"],
              "messages": list(payload.get("messages") or ()), "launch_options": record["launch_options"],
              "launch_option_added": False, "launch_option_error": ""}
    # Proton loads dxgi.dll from the game folder by itself; any other name
    # HelixSR Scaler had to take needs Steam's override for it.
    if record["launch_options"] and record["scaler_dll"]:
        try:
            add_dll_override(appid, Path(record["scaler_dll"]).stem)
            result["launch_option_added"] = True
        except (OSError, RuntimeError, ValueError) as error:
            result["launch_option_error"] = str(error)
    return result


def set_helixsr_scaler_frame_generation(appid: str, enabled: bool) -> dict:
    appid = str(appid).strip()
    record = _scaler_records().get(appid)
    if record is None or _scaler_state(record) != "installed":
        raise RuntimeError("HelixSR Scaler is not installed in this game.")
    if enabled and not helixsr_fg_ready():
        raise ActionNeeded("Build HelixSR's frame generation first (Build frame generation, on the HelixSR card).")
    folder = Path(str(record["folder"]))
    _refuse_running(folder)
    payload = _run_bridge("scaler-fg", "--game", str(folder), "--on", "true" if enabled else "false")
    record = _scaler_result(appid, str(record.get("name") or appid), folder, payload)
    return {"game": record["name"], "frame_generation": record["frame_generation"]}


def update_helixsr_scaler(appid: str) -> dict:
    """The installed release into a game that has HelixSR Scaler from another.

    The bridge's own install, which keeps the game's current version in
    HelixSR-previous.zip (Go back puts it back). Frame generation stays as
    the game has it.
    """
    appid = str(appid).strip()
    record = _scaler_records().get(appid)
    if record is None or _scaler_state(record) != "installed":
        raise RuntimeError("HelixSR Scaler is not installed in this game.")
    directory = helixsr_directory()
    if not helixsr_scaler_supported(directory):
        raise ActionNeeded("Install HelixSR 2.0 or newer first: earlier releases have no HelixSR Scaler.")
    folder = Path(str(record["folder"]))
    _refuse_running(folder)
    fg = "on" if record.get("frame_generation") == "on" and helixsr_fg_ready(directory) else "off"
    payload = _run_bridge(
        "install", "--game", str(folder), "--way", "scaler",
        "--scaler", str(directory / HELIXSR_SCALER), "--fg", fg,
    )
    record = _scaler_result(appid, str(record.get("name") or appid), folder, payload)
    return {"game": record["name"], "version": record["version"], "previous": record["previous"]}


def rollback_helixsr_scaler(appid: str) -> dict:
    """Back to the version the game's last update kept; the bridge keeps the
    current one in its place, so this can be undone the same way."""
    appid = str(appid).strip()
    record = _scaler_records().get(appid)
    if record is None or _scaler_state(record) != "installed":
        raise RuntimeError("HelixSR Scaler is not installed in this game.")
    if not record.get("previous"):
        raise RuntimeError("This game has no earlier HelixSR version kept. One is kept from its next update on.")
    folder = Path(str(record["folder"]))
    _refuse_running(folder)
    payload = _run_bridge("rollback", "--game", str(folder))
    record = _scaler_result(appid, str(record.get("name") or appid), folder, payload)
    return {"game": record["name"], "version": record["version"], "previous": record["previous"]}


def update_all_helixsr_games() -> dict:
    """Every game with another HelixSR release than the installed one, updated.

    A game that is running, or that fails, is skipped and named; the rest
    still go through.
    """
    state = helixsr_state()
    if not state["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    updated: list[str] = []
    skipped: list[str] = []
    for game in state["games"]:
        if game.get("state") != "installed" or not game.get("outdated"):
            continue
        try:
            update_helixsr_game(str(game["appid"]))
            updated.append(str(game.get("name") or game["appid"]))
        except (OSError, RuntimeError, ValueError):
            skipped.append(str(game.get("name") or game["appid"]))
    for row in state["scaler_games"]:
        if row.get("state") != "installed" or not row.get("outdated"):
            continue
        try:
            update_helixsr_scaler(str(row["appid"]))
            updated.append(str(row.get("name") or row["appid"]))
        except (OSError, RuntimeError, ValueError):
            skipped.append(str(row.get("name") or row["appid"]))
    return {"updated": updated, "skipped": skipped, "version": state["version"]}


def remove_helixsr_scaler(appid: str) -> dict:
    """Upstream's own removal: every file it replaced comes back."""
    appid = str(appid).strip()
    records = _scaler_records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR Scaler is not recorded for this game.")
    folder = Path(str(record["folder"]))
    name = str(record.get("name") or appid)
    if _scaler_state(record) == "installed":
        _refuse_running(folder)
        _run_bridge("remove", "--game", str(folder))
    records.pop(appid, None)
    _write_json(_scaler_records_path(), records)
    return {"game": name}


def _helixsr_python() -> str:
    """The setup's way to find Python 3 with numpy, for the frame-generation build."""
    return '''bc250_data="${XDG_DATA_HOME:-$HOME/.local/share}/HelixSR"
bc250_py=""
for bc250_candidate in "$bc250_data/python/bin/python3" python3; do
  if command -v "$bc250_candidate" >/dev/null 2>&1 \\
     && "$bc250_candidate" -c 'import numpy, sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    bc250_py="$(command -v "$bc250_candidate")"; break
  fi
done
test -n "$bc250_py" || { echo "ERROR: build HelixSR's network first: it sets up the Python this build uses."; exit 66; }
test -x "$bc250_data/dxc-wine.sh" || { echo "ERROR: build HelixSR's network first: it sets up the shader compiler this build uses."; exit 66; }'''


def build_helixsr_fg_command() -> str:
    """Build DLSS frame generation into the installed release, in the terminal.

    HelixSR's setup asks before each download from NVIDIA (the frame
    generation DLLs from the Streamline SDK and the NGX core from NVIDIA's
    Linux driver package) and from Intel; answering no to one leaves
    upscaling exactly as it was. Nothing in any game changes.
    """
    target = shlex.quote(str(helixsr_directory()))
    built = shlex.quote(str(helixsr_directory() / HELIXSR_BUILD_FOLDER))
    return f'''set -Eeuo pipefail
echo "== HelixSR {helixsr_release()['version']} · DLSS frame generation =="
echo "HelixSR's setup builds NVIDIA's DLSS frame generation on this PC, for HelixSR Scaler."
echo "It asks before each download: NVIDIA's frame-generation DLLs (from NVIDIA's Streamline SDK on GitHub,"
echo "only those files) and NVIDIA's NGX core (from NVIDIA's Linux driver package, about 400 MB, only that"
echo "file is kept). Answer no to any of them and upscaling stays exactly as it is."
echo "The files built hold NVIDIA's software: they are for this PC only, never share or upload them."
echo
test -f {built}/{HELIXSR_DLL} || {{ echo "ERROR: HelixSR 2.0 or newer is not installed."; exit 66; }}
{_helixsr_python()}
if ! "$bc250_py" -c 'import compression.zstd' >/dev/null 2>&1 && ! command -v zstd >/dev/null 2>&1; then
  echo "ERROR: NVIDIA's NGX core comes out of a zstd package: install the zstd program first, then retry."
  exit 69
fi
bc250_dxc="$bc250_data/dxc-wine.sh"
bc250_dxc_fix=""
# Networks built before the wine shim had a fixed place point dxc-wine.sh at a
# temporary folder that no longer exists: give this build a copy that uses
# the wine found now.
bc250_old_wine="$(grep -m1 -o '/[^ "]*bc250-helixsr-wine\\.[A-Za-z0-9]*/wine' "$bc250_dxc" || true)"
if test -n "$bc250_old_wine" && test ! -x "$bc250_old_wine"; then
{_wine_check()}
  bc250_dxc_fix="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr-dxc.XXXXXX")"
  sed "s|$bc250_old_wine|$bc250_wine|g" "$bc250_dxc" > "$bc250_dxc_fix/dxc-wine.sh"
  chmod +x "$bc250_dxc_fix/dxc-wine.sh"
  bc250_dxc="$bc250_dxc_fix/dxc-wine.sh"
  echo "[helixsr-fg] the shader compiler pointed at a removed Wine folder; using $bc250_wine"
fi
bc250_rc=0
"$bc250_py" -I {target}/setup/helixsr_setup.py {built} --dxc "$bc250_dxc" --fg-only || bc250_rc=$?
test -z "$bc250_dxc_fix" || rm -rf -- "$bc250_dxc_fix"
rm -rf -- "$bc250_data/wineprefix"
test -f {built}/{HELIXSR_FG_FOLDER}/{_FG_BUILT} || {{
  echo
  echo "Frame generation was not built (exit $bc250_rc). Upscaling works as before; run this again to retry."
  exit 1
}}
echo
echo "OK: DLSS frame generation is ready. Turn it on per game, in a game with HelixSR Scaler."'''

