"""Take OptiScaler Client's files out of a game, keeping them, when the client cannot.

OptiScaler Client (BC250 build) records every game it patches in
``~/.config/OptiscalerClient-BC250/BC250/games/<key>/``: ``receipt.json`` lists
each file it put in the game with the SHA-256 it wrote, and, for a file that
replaced one of the game's own, that original's SHA-256 and a copy under
``originals/``. Its own Restore uses exactly that, but it walks the folder as
the receipt spelled it and refuses any symlink on the way. A game added by
hand through ``~/.steam/steam`` (a link to ``~/.local/share/Steam``) is
installed fine and then can never be restored: "Use a regular game folder and
files; linked path". A user reported it, and the maintainer's own Forza
Horizon 6 hit it.

This module does the same restore from the same receipt, through the real
folder, for every game the client recorded (Steam, added by hand, Heroic,
Lutris -- the receipt is all it needs), and never deletes anything:

* each file the client wrote is checked against the receipt and moved into
  a dated backup folder under Control Center's data directory; a game file
  it had replaced comes back from the client's own copy, checked first;
* the client's record moves into the same backup, so the client sees the
  game as clean and can install it again from its regular entry;
* "Put back" returns both exactly, while the game still matches what was
  taken out.

Nothing is touched unless every file still matches the receipt, the client
is closed and holds no operation lock, and the game is not running. A file
that changed (a game update, a HelixSR route through this OptiScaler) stops
the whole operation; nothing half-done stays behind.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from .bc250_opticlient import _data_home, _running, opticlient_records

#: The client's per-game records and its operation lock (``Bc250RouteService``).
_GAME_KEY = re.compile(r"[0-9a-f]{64}")
_BACKUP_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,80}")
_RECEIPT_SCHEMA = 1
_MANIFEST = "manifest.json"
_FILES = "files"
_RECORD = "client-record"
_PART = ".bc250-part"


def opticlient_backups_root() -> Path:
    return _data_home() / "bc250-control-center" / "opticlient-backups"


def _client_state() -> Path:
    return opticlient_records() / "BC250"


def _client_games() -> Path:
    return _client_state() / "games"


# ------------------------------------------------------------------ digests

#: SHA-256 by (device, inode, size, mtime, ctime): the dashboard reads every
#: game on each refresh, and one OptiScaler install is a quarter gigabyte.
_DIGESTS: dict[tuple, str] = {}


def _sha256(path: Path, *, fresh: bool = False) -> str | None:
    """The file's SHA-256, or None when there is no regular file there."""
    try:
        info = path.lstat()
    except OSError:
        return None
    if not path.is_file() or path.is_symlink():
        return None
    key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if not fresh and key in _DIGESTS:
        return _DIGESTS[key]
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        return None
    if len(_DIGESTS) > 4096:
        _DIGESTS.clear()
    _DIGESTS[key] = digest.hexdigest()
    return _DIGESTS[key]


# ------------------------------------------------------------------ paths


def _relative(text: object) -> Path:
    """A receipt path, refused unless it stays inside the game folder."""
    value = str(text or "").replace("\\", "/")
    path = Path(value)
    if (not value or path.is_absolute() or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError(f"Unsafe path in the installation record: {value!r}")
    return path


def _inside(root: Path, relative: Path) -> Path:
    """``root/relative``, refused if any folder on the way is a link."""
    target = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"Game folder {current} is a link; it was not touched.")
    return target


def _remove_empty_folders(root: Path, relatives: list[Path]) -> None:
    """The folders the client created and left empty, deepest first."""
    folders = {root / parent for relative in relatives for parent in relative.parents
               if parent != Path(".")}
    for folder in sorted(folders, key=lambda path: len(path.parts), reverse=True):
        try:
            if folder.is_dir() and not folder.is_symlink() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            continue


def _move_verified(source: Path, target: Path, digest: str) -> None:
    """Move one file whose SHA-256 is ``digest``; across drives, copy and check."""
    if _sha256(source, fresh=True) != digest:
        raise RuntimeError(f"Game file {source} changed; it was not moved.")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
    staged = target.with_name(target.name + _PART)
    shutil.copy2(source, staged)
    if _sha256(staged, fresh=True) != digest:
        staged.unlink(missing_ok=True)
        raise RuntimeError(f"The copy of game file {source} did not verify; it was not moved.")
    _fsync(staged)
    os.replace(staged, target)
    source.unlink()


def _fsync(path: Path) -> None:
    """On disk before the original goes: a power cut keeps one good copy."""
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _copy_verified(source: Path, target: Path, digest: str) -> None:
    if _sha256(source, fresh=True) != digest:
        raise RuntimeError(f"The client's copy of game file {target.name} changed; it was not used.")
    staged = target.with_name(target.name + _PART)
    shutil.copy2(source, staged)
    if _sha256(staged, fresh=True) != digest:
        staged.unlink(missing_ok=True)
        raise RuntimeError(f"The copy of game file {target.name} did not verify.")
    _fsync(staged)
    os.replace(staged, target)


def _move_folder(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"Game file {target} already exists; it was not replaced.")
    shutil.move(str(source), str(target))


def _write_json(path: Path, value: object) -> None:
    staged = path.with_name(path.name + ".tmp")
    with staged.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=1, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(staged, path)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ guards


class _ClientLock:
    """The client's own operation lock, held while Control Center works.

    The client opens ``BC250/operation.lock`` exclusively for every install
    and restore (.NET takes ``flock`` for that on Linux); holding it here
    keeps the two from ever changing one game at the same time.
    """

    def __init__(self) -> None:
        self._stream = None

    def __enter__(self):
        if _running():
            raise RuntimeError("Close OptiScaler Client first.")
        path = _client_state() / "operation.lock"
        if not path.parent.is_dir():
            return self
        self._stream = path.open("a+b")
        try:
            fcntl.flock(self._stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._stream.close()
            self._stream = None
            raise RuntimeError("An OptiScaler Client operation is still running. Try again when it finishes.") from None
        return self

    def __exit__(self, *_exc) -> None:
        if self._stream is not None:
            fcntl.flock(self._stream, fcntl.LOCK_UN)
            self._stream.close()


def _refuse_running(*folders: Path) -> None:
    from .helixsr import _refuse_running as refuse

    for folder in folders:
        refuse(folder)


def _helixsr_route(real_root: Path) -> bool:
    """HelixSR points this OptiScaler at itself (its OptiScaler route)."""
    try:
        from .helixsr import _optiscaler_records
        records = _optiscaler_records()
    except Exception:  # noqa: BLE001 - HelixSR's records are optional here
        return False
    for record in records.values():
        root = str(record.get("root") or "")
        if root and Path(os.path.realpath(root)) == real_root:
            return True
    return False


# ------------------------------------------------------------------ reading


def _game_names() -> list[tuple[Path, str, str]]:
    """(real folder, name, id) for every game in the client's list, Steam first."""
    records = _read_json(opticlient_records() / "games.json")
    games = []
    for record in records if isinstance(records, list) else ():
        if not isinstance(record, dict):
            continue
        install = str(record.get("InstallPath") or "").strip()
        if not install:
            continue
        games.append((
            Path(os.path.realpath(install)),
            str(record.get("Name") or "").strip(),
            str(record.get("AppId") or "").strip(),
        ))
    # Steam's own id before a "Manual_..." one for the same folder.
    games.sort(key=lambda game: not game[2].isdigit())
    return games


def _name_for(real_root: Path, games: list[tuple[Path, str, str]]) -> tuple[str, str]:
    """The client's name and id for the game whose folder holds ``real_root``."""
    best: tuple[Path, str, str] | None = None
    for folder, name, appid in games:
        if real_root == folder or folder in real_root.parents:
            if best is None or len(folder.parts) > len(best[0].parts):
                best = (folder, name, appid)
    if best is None:
        return real_root.name, ""
    return best[1] or real_root.name, best[2]


def _linked_component(path: str) -> str:
    """The first linked folder on the way to the game, below the home folder.

    ``/home`` itself is a link on Bazzite and Fedora Atomic (to ``/var/home``);
    that one is the system's and never the reason the client's Restore fails.
    """
    current = Path(path)
    home = Path.home()
    system = {home, *home.parents}
    try:
        system |= {home.resolve(), *home.resolve().parents}
    except OSError:
        pass
    for candidate in (current, *current.parents):
        try:
            if candidate in system or candidate.resolve() in system:
                continue
            if candidate.is_symlink():
                return str(candidate)
        except OSError:
            continue
    return ""


def _installation(folder: Path, games: list[tuple[Path, str, str]], *, fresh: bool = False) -> dict | None:
    """One client record, read and checked against the game folder."""
    key = folder.name
    if not _GAME_KEY.fullmatch(key) or folder.is_symlink() or not folder.is_dir():
        return None
    receipt_path = folder / "receipt.json"
    pending = (folder / "pending.json").exists()
    if not receipt_path.is_file() and not pending:
        return None
    entry: dict = {"key": key, "name": "", "appid": "", "root": "", "real_root": "",
                   "linked_path": "", "release": "", "files": 0, "replaced": 0,
                   "changed": [], "state": "unsupported", "removable": False}
    if pending:
        entry["state"] = "pending"
        receipt = _read_json(folder / "pending.json")
        root = str(receipt.get("Root") or "") if isinstance(receipt, dict) else ""
        if root:
            entry["root"] = root
            entry["real_root"] = os.path.realpath(root)
            entry["name"], entry["appid"] = _name_for(Path(entry["real_root"]), games)
        return entry
    receipt = _read_json(receipt_path)
    files = receipt.get("Files") if isinstance(receipt, dict) else None
    if (not isinstance(receipt, dict) or receipt.get("Schema") != _RECEIPT_SCHEMA
            or not str(receipt.get("Root") or "").startswith("/") or not isinstance(files, list)):
        return entry
    root = str(receipt["Root"])
    real_root = Path(os.path.realpath(root))
    entry.update(
        root=root, real_root=str(real_root), linked_path=_linked_component(root),
        release=str(receipt.get("Release") or ""),
    )
    entry["name"], entry["appid"] = _name_for(real_root, games)
    if not real_root.is_dir():
        entry["state"] = "missing"
        return entry
    checked = []
    try:
        for item in files:
            if not isinstance(item, dict):
                return entry
            relative = _relative(item.get("Path"))
            installed = str(item.get("Installed") or "")
            original = item.get("Original")
            original = str(original) if original else None
            backup = str(item.get("Backup") or "")
            # Every digest the moves will check must be one: a record without
            # them is one this code does not understand, not one to act on.
            if not _GAME_KEY.fullmatch(installed):
                return entry
            if original is not None and not (_GAME_KEY.fullmatch(original) and _GAME_KEY.fullmatch(backup)):
                return entry
            checked.append((relative, installed, original, backup))
    except ValueError:
        return entry
    entry["files"] = len(checked)
    entry["replaced"] = sum(1 for item in checked if item[2])
    # Each file is as the client wrote it, as it was before (absent, or the
    # game's own file back), or something else: only the last stops us.
    installed_count, changed = 0, []
    for relative, installed, original, backup in checked:
        try:
            current = _sha256(_inside(real_root, relative), fresh=fresh)
        except RuntimeError:
            current = "link"
        if current == installed:
            installed_count += 1
        elif current != original:
            changed.append(str(relative))
        if original is not None and _sha256(folder / "originals" / backup, fresh=fresh) != original:
            entry["state"] = "backup-broken"
            entry["changed"] = [str(relative)]
            return entry
    entry["changed"] = changed[:8]
    if _helixsr_route(real_root):
        entry["state"] = "helixsr"
    elif changed:
        entry["state"] = "changed"
    elif installed_count == len(checked):
        entry["state"] = "intact"
    elif installed_count:
        # Some files were deleted by hand; the rest are still the client's.
        entry["state"] = "partial"
    else:
        # Every file is already gone (or back to the game's own): only the
        # client's record is left, and it makes the client refuse the game.
        entry["state"] = "removed"
    entry["removable"] = entry["state"] in {"intact", "partial", "removed"}
    return entry


def opticlient_installations(*, fresh: bool = False) -> list[dict]:
    """Every game OptiScaler Client recorded an installation for, checked.

    ``state`` is ``intact`` (every file as the client wrote it: it can be
    taken out), ``partial`` (some were deleted by hand; the rest can be),
    ``removed`` (its files are already gone; only the record is left),
    ``changed`` (files differ: a game update or a hand edit; nothing
    is touched), ``helixsr`` (HelixSR's OptiScaler route uses it: remove that
    first), ``pending`` (the client was interrupted: its own Restore /
    recover finishes that), ``backup-broken``, ``interrupted`` (a removal by
    Control Center was cut short; ``backup`` names the backup to put back),
    ``missing`` (the folder is gone) or ``unsupported``. ``linked_path`` names the link in the recorded
    folder that stops the client's own Restore.
    """
    root = _client_games()
    try:
        folders = sorted(root.iterdir())
    except OSError:
        return []
    games = _game_names()
    interrupted = {backup["key"]: backup["id"] for backup in opticlient_backups()
                   if backup["state"] == "interrupted"}
    rows = [_installation(folder, games, fresh=fresh) for folder in folders]
    for row in rows:
        if row is not None and row["key"] in interrupted:
            # Part of its files are in that backup: put them back before anything else.
            row.update(state="interrupted", removable=False, backup=interrupted[row["key"]])
    return [row for row in rows if row is not None]


def _backup_folder(backup_id: str) -> Path:
    if not _BACKUP_ID.fullmatch(str(backup_id or "")):
        raise RuntimeError("Unknown backup.")
    folder = opticlient_backups_root() / backup_id
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("That backup is no longer there.")
    return folder


def _backup(folder: Path) -> dict | None:
    manifest = _read_json(folder / _MANIFEST)
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        return None
    files = [item for item in manifest.get("files") or () if isinstance(item, dict)]
    real_root = Path(str(manifest.get("real_root") or "/nonexistent"))
    entry = {
        "id": folder.name,
        "name": str(manifest.get("name") or folder.name),
        "appid": str(manifest.get("appid") or ""),
        "key": str(manifest.get("key") or ""),
        "real_root": str(real_root),
        "created": str(manifest.get("created") or ""),
        "files": sum(1 for item in files if item.get("moved")),
        "path": str(folder),
        "state": "incomplete",
        "restorable": False,
    }
    if manifest.get("state") != "complete":
        return _interrupted(entry, folder, files, real_root)
    if not any(item.get("moved") for item in files):
        entry["state"] = "record-only"
        return entry
    if not real_root.is_dir():
        entry["state"] = "missing"
        return entry
    if (_client_games() / entry["key"]).exists():
        entry["state"] = "client-record"
        return entry
    for item in files:
        try:
            relative = _relative(item.get("path"))
            target = _inside(real_root, relative)
        except (ValueError, RuntimeError):
            entry["state"] = "game-changed"
            return entry
        saved = folder / _FILES / relative
        if item.get("moved") and _sha256(saved) != item.get("installed"):
            entry["state"] = "backup-broken"
            return entry
        expected = item.get("original") or None
        if _sha256(target) != expected:
            entry["state"] = "game-changed"
            return entry
    entry["state"] = "ready"
    entry["restorable"] = True
    return entry


def _interrupted(entry: dict, folder: Path, files: list[dict], real_root: Path) -> dict:
    """A removal cut short (power cut, crash): can its moved files go back?

    The manifest is written after every file, so it names exactly what
    left the game. Put back returns those while each spot in the game is
    still empty (or holds the game's own file again) and every saved copy
    verifies; the client's record is still in place, or in the backup if the
    cut came at the very end.
    """
    if not real_root.is_dir():
        return entry
    if (folder / _RECORD).is_dir() and (_client_games() / entry["key"]).exists():
        return entry
    for item in files:
        if not item.get("moved"):
            continue
        try:
            relative = _relative(item.get("path"))
            target = _inside(real_root, relative)
        except (ValueError, RuntimeError):
            return entry
        if _sha256(folder / _FILES / relative) != item.get("installed"):
            return entry
        if _sha256(target) not in {None, item.get("original") or None}:
            return entry
    entry["state"] = "interrupted"
    entry["restorable"] = True
    return entry


def opticlient_backups() -> list[dict]:
    """The backups Control Center took, newest first.

    ``state`` is ``ready`` (Put back would return them), ``game-changed``
    (the game has files there again, or a different original),
    ``client-record`` (the client recorded this game again: use the client),
    ``interrupted`` (a removal was cut short; Put back finishes undoing it),
    ``missing`` (game folder gone), ``record-only`` (only the client's record
    was kept; there are no files to return), ``backup-broken`` or
    ``incomplete`` (interrupted; its files are all inside the folder).
    """
    try:
        folders = [folder for folder in opticlient_backups_root().iterdir()
                   if folder.is_dir() and not folder.is_symlink() and _BACKUP_ID.fullmatch(folder.name)]
    except OSError:
        return []
    rows = [_backup(folder) for folder in folders]
    rows = [row for row in rows if row is not None]
    return sorted(rows, key=lambda row: row["created"], reverse=True)


# ------------------------------------------------------------------ changing


def _new_backup_folder(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "game"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = opticlient_backups_root()
    root.mkdir(parents=True, exist_ok=True)
    for attempt in range(100):
        folder = root / (f"{slug}-{stamp}" + (f"-{attempt}" if attempt else ""))
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            continue
    raise RuntimeError("Could not create a backup folder.")


_REFUSALS = {
    "changed": "Some of OptiScaler's files changed after the client installed them (a game update or a hand edit). Nothing was touched.",
    "helixsr": "HelixSR uses this game's OptiScaler. Remove HelixSR from it first.",
    "pending": "OptiScaler Client was interrupted in this game. Open the client and use Restore / recover selected first.",
    "backup-broken": "OptiScaler Client's copy of a game file changed, so the game's own file could not come back. Nothing was touched.",
    "missing": "The game's folder is gone.",
    "unsupported": "This installation record is not one Control Center can read. Nothing was touched.",
    "interrupted": "Control Center was interrupted while taking OptiScaler out of this game. Put OptiScaler back returns the files it had already moved; then try again.",
}
_NO_SPACE = "There is not enough free space for the backup in your home folder. Nothing was touched."


def _refuse_without_space(real_root: Path, files: list[dict]) -> None:
    """A game on another drive (an SD card, a second disk) is copied, not renamed."""
    root = opticlient_backups_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        if os.stat(real_root).st_dev == os.stat(root).st_dev:
            return
        needed = sum((real_root / item["path"]).stat().st_size for item in files if item["present"])
        free = shutil.disk_usage(root).free
    except OSError:
        return
    if free < needed + 64 * 1024 * 1024:
        raise RuntimeError(_NO_SPACE)


def remove_opticlient_installation(key: str) -> dict:
    """Take the client's files out of one game into a backup; put its originals back."""
    key = str(key or "").strip().lower()
    folder = _client_games() / key
    if not _GAME_KEY.fullmatch(key) or not folder.is_dir():
        raise RuntimeError("OptiScaler Client has no record of this game.")
    with _ClientLock():
        entry = _installation(folder, _game_names(), fresh=True)
        if entry is not None and any(backup["key"] == key and backup["state"] in {"interrupted", "incomplete"}
                                     for backup in opticlient_backups()):
            entry["state"], entry["removable"] = "interrupted", False
        if entry is None or not entry["removable"]:
            state = entry["state"] if entry else "unsupported"
            raise RuntimeError(_REFUSALS.get(state, _REFUSALS["unsupported"]))
        real_root = Path(entry["real_root"])
        _refuse_running(real_root, Path(entry["root"]))
        receipt = _read_json(folder / "receipt.json")
        files = []
        for item in receipt["Files"]:
            original = item.get("Original") or None
            relative = _relative(item.get("Path"))
            present = _sha256(_inside(real_root, relative), fresh=True) == item["Installed"]
            files.append({
                "path": str(relative), "installed": str(item["Installed"]),
                "original": original, "backup": str(item.get("Backup") or ""),
                "moved": False, "present": present,
            })
        _refuse_without_space(real_root, files)
        backup = _new_backup_folder(entry["name"])
        manifest = {
            "schema": 1, "state": "moving",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "name": entry["name"], "appid": entry["appid"], "key": key,
            "root": entry["root"], "real_root": str(real_root), "release": entry["release"],
            "files": files,
        }
        _write_json(backup / _MANIFEST, manifest)
        try:
            for item in files:
                if not item["present"]:
                    continue
                relative = Path(item["path"])
                target = _inside(real_root, relative)
                _move_verified(target, backup / _FILES / relative, item["installed"])
                item["moved"] = True
                # After every file: a power cut leaves a manifest that says
                # exactly what left the game.
                _write_json(backup / _MANIFEST, manifest)
                if item["original"]:
                    _copy_verified(folder / "originals" / item["backup"], target, item["original"])
            _remove_empty_folders(real_root, [Path(item["path"]) for item in files])
            _move_folder(folder, backup / _RECORD)
        except Exception as error:
            _undo_moves(real_root, backup, files)
            raise RuntimeError(f"{error} Everything was put back as it was.") from error
        manifest["state"] = "complete"
        _write_json(backup / _MANIFEST, manifest)
    moved = sum(1 for item in files if item["moved"])
    return {
        "game": entry["name"], "files": moved,
        "restored": sum(1 for item in files if item["moved"] and item["original"]),
        "backup": str(backup), "record_only": moved == 0,
    }


def _undo_moves(real_root: Path, backup: Path, files: list[dict]) -> None:
    """Return what a failed removal had moved; keep the backup if anything is left."""
    left = False
    for item in reversed(files):
        if not item.get("moved"):
            continue
        relative = Path(item["path"])
        saved = backup / _FILES / relative
        try:
            _move_verified(saved, real_root / relative, item["installed"])
            item["moved"] = False
        except Exception:  # noqa: BLE001 - keep going; the rest still goes back
            left = True
    if left:
        try:
            manifest = _read_json(backup / _MANIFEST)
        except Exception:  # noqa: BLE001 - a broken manifest must not hide the real failure
            manifest = {}
        _write_json(backup / _MANIFEST, {**(manifest if isinstance(manifest, dict) else {}), "files": files})
        return
    (backup / _MANIFEST).unlink(missing_ok=True)
    _remove_empty_tree(backup)


def _remove_empty_tree(folder: Path) -> None:
    for path in sorted(folder.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and not path.is_symlink():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        folder.rmdir()
    except OSError:
        pass


def restore_opticlient_backup(backup_id: str) -> dict:
    """Put a backup's files and the client's record back, as they were."""
    folder = _backup_folder(str(backup_id or "").strip().lower())
    with _ClientLock():
        entry = _backup(folder)
        if entry is None or not entry["restorable"]:
            state = entry["state"] if entry else "incomplete"
            raise RuntimeError({
                "game-changed": "The game's files changed since the backup was taken (OptiScaler or another mod is there again). Nothing was touched.",
                "client-record": "OptiScaler Client has a record of this game again. Use the client to manage it.",
                "missing": "The game's folder is gone.",
                "record-only": "This backup holds only the client's record; there are no files to put back.",
                "backup-broken": "A file in this backup changed. Nothing was touched.",
            }.get(state, "This backup is incomplete. Its files are in the folder shown."))
        manifest = _read_json(folder / _MANIFEST)
        real_root = Path(entry["real_root"])
        _refuse_running(real_root, Path(str(manifest.get("root") or real_root)))
        files = [item for item in manifest["files"] if item.get("moved")]
        done: list[dict] = []
        try:
            for item in files:
                relative = Path(item["path"])
                _move_verified(folder / _FILES / relative, _inside(real_root, relative), item["installed"])
                done.append(item)
            record = folder / _RECORD
            if record.is_dir() and not (_client_games() / entry["key"]).exists():
                _move_folder(record, _client_games() / entry["key"])
        except Exception as error:
            # The record moves last, so on any failure it is still here.
            originals = folder / _RECORD / "originals"
            if not originals.is_dir():
                originals = _client_games() / entry["key"] / "originals"
            stayed: list[str] = []
            for item in reversed(done):
                relative = Path(item["path"])
                target = real_root / relative
                try:
                    _move_verified(target, folder / _FILES / relative, item["installed"])
                    if item.get("original"):
                        _copy_verified(originals / item["backup"], target, item["original"])
                except Exception:  # noqa: BLE001 - put the rest back; say which stayed
                    item["moved"] = False
                    stayed.append(item["path"])
            if stayed:
                # The manifest follows the files, so the backup still lists
                # exactly what it holds and the rest can be finished by hand.
                _write_json(folder / _MANIFEST, {**manifest, "files": manifest["files"]})
                raise RuntimeError(
                    f"{error} These files are still in the game folder: {', '.join(stayed)}. "
                    "The backup keeps the others."
                ) from error
            raise RuntimeError(f"{error} Nothing was touched.") from error
    (folder / _MANIFEST).unlink(missing_ok=True)
    _remove_empty_tree(folder)
    return {"game": entry["name"], "files": len(files)}
