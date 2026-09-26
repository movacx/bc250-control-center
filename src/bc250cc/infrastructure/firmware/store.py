"""Downloads the pinned firmware files and keeps a verified cache of them.

Nothing leaves this module unverified: a download is written to a temporary
file, hashed while it streams, and only moved into the cache when its SHA-256
is the one the catalog pins. A cached file is hashed again every time it is
used, so a file damaged on disk is fetched again rather than copied onto a
USB that will flash it.

Archives are unpacked member by member into the same cache: ``zip`` with the
standard library, ``7z`` with whichever of 7-Zip or bsdtar is installed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from bc250cc.domain.firmware.catalog import ArchivedFile, RemoteFile, Source

CHUNK_BYTES = 256 * 1024
USER_AGENT = "BC250-Control-Center (firmware kit)"
#: Seconds a stalled connection may stay silent before the download fails.
READ_TIMEOUT_SECONDS = 30
#: Tools able to stream one member of a 7z archive to stdout, most specific
#: first. bsdtar ships with libarchive, which pacman itself depends on.
SEVEN_ZIP_TOOLS = ("7z", "7za", "7zz", "bsdtar")

#: (bytes done, bytes expected) for the file being fetched.
Progress = Callable[[int, int], None]


class DownloadCancelled(Exception):
    """The user stopped the preparation while a file was downloading."""


class FirmwareIntegrityError(RuntimeError):
    """A file did not have the SHA-256 the catalog pins for it."""


def default_cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bc250-control-center" / "firmware"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seven_zip_tool() -> str:
    """The first installed tool that can unpack a 7z member, or ""."""
    for name in SEVEN_ZIP_TOOLS:
        path = shutil.which(name)
        if path:
            return path
    return ""


class FirmwareStore:
    def __init__(
        self,
        root: Path | None = None,
        *,
        opener: Callable[..., object] = urllib.request.urlopen,
        seven_zip: Callable[[], str] = seven_zip_tool,
    ) -> None:
        self.root = Path(root) if root is not None else default_cache_root()
        self._opener = opener
        self._seven_zip = seven_zip

    # ------------------------------------------------------------- queries

    def path_for(self, source: Source) -> Path:
        """Content-addressed: a new upstream revision can never be mistaken
        for the one already cached."""
        return self.root / source.sha256 / source.name

    def is_cached(self, source: Source) -> bool:
        """Cheap check for the interface; ``ensure`` still verifies the hash."""
        try:
            return self.path_for(source).stat().st_size == source.size
        except OSError:
            return False

    def can_unpack(self, source: Source) -> bool:
        if isinstance(source, ArchivedFile) and source.archive_format == "7z":
            return self.is_cached(source) or bool(self._seven_zip())
        return True

    # ----------------------------------------------------------- fetching

    def ensure(
        self,
        source: Source,
        *,
        progress: Progress | None = None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Path:
        """The verified local copy of ``source``, fetched if needed."""
        target = self.path_for(source)
        if target.is_file() and sha256_of(target) == source.sha256:
            if progress is not None:
                progress(source.size, source.size)
            return target
        if isinstance(source, ArchivedFile):
            archive = self.ensure(source.archive, progress=progress, cancelled=cancelled)
            self._unpack(source, archive, target)
        else:
            self._download(source, target, progress, cancelled)
        return target

    def _download(
        self,
        source: RemoteFile,
        target: Path,
        progress: Progress | None,
        cancelled: Callable[[], bool],
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
        digest = hashlib.sha256()
        received = 0
        descriptor, temporary = tempfile.mkstemp(prefix=".part-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as output, self._opener(
                request, timeout=READ_TIMEOUT_SECONDS
            ) as response:
                while True:
                    if cancelled():
                        raise DownloadCancelled()
                    chunk = response.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > source.size:
                        raise FirmwareIntegrityError(
                            f"{source.name} is larger than the reviewed file."
                        )
                    output.write(chunk)
                    digest.update(chunk)
                    if progress is not None:
                        progress(received, source.size)
                output.flush()
                os.fsync(output.fileno())
            self._accept(Path(temporary), target, digest.hexdigest(), source)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _unpack(self, source: ArchivedFile, archive: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".part-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                if source.archive_format == "zip":
                    self._unpack_zip(source, archive, output)
                else:
                    self._unpack_7z(source, archive, output)
                output.flush()
                os.fsync(output.fileno())
            self._accept(Path(temporary), target, sha256_of(Path(temporary)), source)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _unpack_zip(source: ArchivedFile, archive: Path, output) -> None:
        with zipfile.ZipFile(archive) as bundle:
            try:
                member = bundle.getinfo(source.member)
            except KeyError as error:
                raise FirmwareIntegrityError(
                    f"{source.member} is missing from {source.archive.name}."
                ) from error
            if member.file_size != source.size:
                raise FirmwareIntegrityError(f"{source.name} has an unexpected size.")
            with bundle.open(member) as stream:
                shutil.copyfileobj(stream, output, CHUNK_BYTES)

    def _unpack_7z(self, source: ArchivedFile, archive: Path, output) -> None:
        tool = self._seven_zip()
        if not tool:
            raise RuntimeError(
                "Unpacking this firmware needs 7-Zip (p7zip) or bsdtar. Install "
                "one of them and try again."
            )
        if Path(tool).name == "bsdtar":
            command = [tool, "-xOf", str(archive), source.member]
        else:
            command = [tool, "e", "-so", str(archive), source.member]
        result = subprocess.run(
            command, stdout=output, stderr=subprocess.PIPE, check=False, timeout=300
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"Could not unpack {source.name}: {detail or 'unknown error'}")

    @staticmethod
    def _accept(temporary: Path, target: Path, digest: str, source: Source) -> None:
        if digest != source.sha256:
            raise FirmwareIntegrityError(
                f"{source.name} does not match the reviewed file (SHA-256 mismatch). "
                "It was not used."
            )
        os.replace(temporary, target)
