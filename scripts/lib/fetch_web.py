#!/usr/bin/env python3
"""Put the built web interface in frontends/web/dist, downloading it when this copy does not have it.

The repository carries its source. The built files are an asset of the releases page, and
frontends/web/web-build.json names the exact one that belongs to this copy with its SHA-256: anything
else is refused. A build made here (scripts/development/build-web.sh) is never replaced.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "https://github.com/movacx/bc250-control-center/releases/download/"
MAX_BYTES = 64 * 1024 * 1024
#: Names the downloaded build; a copy without it was built on this machine.
MARKER = ".web-build"


class WebBuildError(RuntimeError):
    pass


def pinned(root: Path) -> dict:
    try:
        pin = json.loads((root / "frontends/web/web-build.json").read_text(encoding="utf-8"))
        url, digest = str(pin["url"]), str(pin["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        raise WebBuildError("frontends/web/web-build.json does not name a web build.") from None
    if not url.startswith(PREFIX) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise WebBuildError("frontends/web/web-build.json names a web build that is not the project's.")
    return {"url": url, "sha256": digest}


def present(root: Path, digest: str) -> bool:
    dist = root / "frontends/web/dist"
    if not (dist / "webApp.js").is_file():
        return False
    try:
        return (dist / MARKER).read_text(encoding="ascii").strip() == digest
    except OSError:
        return True  # built here


def download(url: str, opener=urllib.request.urlopen) -> bytes:
    try:
        with opener(urllib.request.Request(url, headers={"User-Agent": "bc250-control-center-installer"}), timeout=60) as answer:
            data = answer.read(MAX_BYTES + 1)
    except OSError as error:
        raise WebBuildError(f"The web interface could not be downloaded: {error}") from None
    if len(data) > MAX_BYTES:
        raise WebBuildError("The web interface download is larger than expected.")
    return data


def unpack(data: bytes, target: Path) -> None:
    """Regular files only, inside the target, with ordinary permissions."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if member.isdir():
                    continue
                if not member.isfile() or name.is_absolute() or ".." in name.parts or member.size > MAX_BYTES:
                    raise WebBuildError("The web interface archive contains something unexpected.")
                path = target.joinpath(*name.parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output)
                path.chmod(0o644)
    except (tarfile.TarError, EOFError, OSError) as error:
        raise WebBuildError(f"The web interface archive could not be read: {error}") from None
    if not (target / "webApp.js").is_file() or not (target / "index.html").is_file():
        raise WebBuildError("The web interface archive is not complete.")


def fetch(root: Path = ROOT, opener=urllib.request.urlopen) -> bool:
    """True when it was downloaded, False when it was already here."""
    pin = pinned(root)
    if present(root, pin["sha256"]):
        return False
    data = download(pin["url"], opener)
    if hashlib.sha256(data).hexdigest() != pin["sha256"]:
        raise WebBuildError("The downloaded web interface does not match its recorded checksum; nothing was changed.")
    web = root / "frontends/web"
    staging = Path(tempfile.mkdtemp(prefix=".dist-", dir=web))
    try:
        unpack(data, staging)
        (staging / MARKER).write_text(pin["sha256"] + "\n", encoding="ascii")
        staging.chmod(0o755)
        shutil.rmtree(web / "dist", ignore_errors=True)
        staging.rename(web / "dist")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return True


def main() -> int:
    try:
        print("Web interface downloaded and verified." if fetch() else "Web interface: already present.")
    except WebBuildError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
