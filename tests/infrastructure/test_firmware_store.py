"""The firmware cache: nothing reaches a USB unless its SHA-256 matches.

Downloads go through a fake opener, so no test touches the network. Archives
are built on the fly with the standard library (zip) or with whatever 7-Zip
tool the machine has (7z, skipped when there is none).
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import zipfile

import pytest

from bc250cc.domain.firmware.catalog import ArchivedFile, RemoteFile
from bc250cc.infrastructure.firmware.store import (
    DownloadCancelled,
    FirmwareIntegrityError,
    FirmwareStore,
    default_cache_root,
    sha256_of,
)

PAYLOAD = b"BC250 firmware image " * 40_000  # ~840 kB: several chunks


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _remote(data: bytes = PAYLOAD, *, name: str = "IMAGE.ROM", sha256: str | None = None, size=None):
    return RemoteFile(
        url=f"https://example.invalid/0123456789abcdef0123456789abcdef01234567/{name}",
        sha256=sha256 or _sha(data),
        size=len(data) if size is None else size,
        name=name,
    )


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


class _Opener:
    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request.full_url, request.get_header("User-agent"), timeout))
        return _Response(self.files[request.full_url])


def test_the_cache_lives_under_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_cache_root() == tmp_path / "bc250-control-center" / "firmware"


def test_a_download_is_verified_and_cached_by_content(tmp_path):
    source = _remote()
    opener = _Opener({source.url: PAYLOAD})
    store = FirmwareStore(tmp_path, opener=opener)
    seen = []
    path = store.ensure(source, progress=lambda done, total: seen.append((done, total)))
    assert path == tmp_path / source.sha256 / "IMAGE.ROM"
    assert path.read_bytes() == PAYLOAD
    assert store.is_cached(source)
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert len(seen) > 1
    url, agent, timeout = opener.requests[0]
    assert url == source.url and "BC250" in agent and timeout > 0
    assert not list(path.parent.glob(".part-*"))


def test_a_cached_file_is_hashed_again_and_not_downloaded_twice(tmp_path):
    source = _remote()
    opener = _Opener({source.url: PAYLOAD})
    store = FirmwareStore(tmp_path, opener=opener)
    store.ensure(source)
    store.ensure(source)
    assert len(opener.requests) == 1


def test_a_damaged_cached_file_is_fetched_again(tmp_path):
    source = _remote()
    opener = _Opener({source.url: PAYLOAD})
    store = FirmwareStore(tmp_path, opener=opener)
    path = store.ensure(source)
    path.write_bytes(b"x" * len(PAYLOAD))
    assert store.ensure(source).read_bytes() == PAYLOAD
    assert len(opener.requests) == 2


def test_a_file_with_the_wrong_hash_never_enters_the_cache(tmp_path):
    source = _remote(sha256=_sha(b"the reviewed file"))
    store = FirmwareStore(tmp_path, opener=_Opener({source.url: PAYLOAD}))
    with pytest.raises(FirmwareIntegrityError, match="does not match the reviewed file"):
        store.ensure(source)
    assert not store.path_for(source).exists()
    assert not list((tmp_path / source.sha256).glob("*"))


def test_a_download_larger_than_the_reviewed_file_stops_early(tmp_path):
    source = _remote(size=1000)
    store = FirmwareStore(tmp_path, opener=_Opener({source.url: PAYLOAD}))
    with pytest.raises(FirmwareIntegrityError, match="larger than the reviewed file"):
        store.ensure(source)
    assert not list((tmp_path / source.sha256).glob("*"))


def test_cancelling_a_download_leaves_no_partial_file(tmp_path):
    source = _remote()
    store = FirmwareStore(tmp_path, opener=_Opener({source.url: PAYLOAD}))
    calls = iter([False, False, True])
    with pytest.raises(DownloadCancelled):
        store.ensure(source, cancelled=lambda: next(calls))
    assert not list((tmp_path / source.sha256).glob("*"))


def _zip_with(member: str, data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(member, data)
        bundle.writestr("README.txt", b"other files are ignored")
    return buffer.getvalue()


def test_a_zip_member_is_unpacked_and_verified(tmp_path):
    archive_bytes = _zip_with("Kit/BIOS EFI/Robin5.00", PAYLOAD)
    archive = _remote(archive_bytes, name="kit.zip")
    rom = ArchivedFile(archive=archive, member="Kit/BIOS EFI/Robin5.00",
                       sha256=_sha(PAYLOAD), size=len(PAYLOAD), name="Robin5.00")
    store = FirmwareStore(tmp_path, opener=_Opener({archive.url: archive_bytes}))
    assert store.can_unpack(rom)
    assert store.ensure(rom).read_bytes() == PAYLOAD
    assert store.is_cached(archive) and store.is_cached(rom)


def test_a_missing_zip_member_is_reported(tmp_path):
    archive_bytes = _zip_with("Kit/other", PAYLOAD)
    archive = _remote(archive_bytes, name="kit.zip")
    rom = ArchivedFile(archive=archive, member="Kit/BIOS EFI/Robin5.00",
                       sha256=_sha(PAYLOAD), size=len(PAYLOAD), name="Robin5.00")
    store = FirmwareStore(tmp_path, opener=_Opener({archive.url: archive_bytes}))
    with pytest.raises(FirmwareIntegrityError, match="is missing from kit.zip"):
        store.ensure(rom)


def test_a_zip_member_of_the_wrong_size_is_refused(tmp_path):
    archive_bytes = _zip_with("Kit/rom", PAYLOAD)
    archive = _remote(archive_bytes, name="kit.zip")
    rom = ArchivedFile(archive=archive, member="Kit/rom", sha256=_sha(PAYLOAD),
                       size=len(PAYLOAD) - 1, name="rom")
    store = FirmwareStore(tmp_path, opener=_Opener({archive.url: archive_bytes}))
    with pytest.raises(FirmwareIntegrityError, match="unexpected size"):
        store.ensure(rom)


def test_a_7z_archive_without_a_tool_asks_for_one(tmp_path):
    archive = _remote(b"7z bytes", name="Firmware.7z")
    rom = ArchivedFile(archive=archive, member="Firmware/X", sha256=_sha(PAYLOAD),
                       size=len(PAYLOAD), name="X")
    store = FirmwareStore(tmp_path, opener=_Opener({archive.url: b"7z bytes"}), seven_zip=lambda: "")
    assert not store.can_unpack(rom)
    with pytest.raises(RuntimeError, match="needs 7-Zip"):
        store.ensure(rom)


@pytest.mark.parametrize("tool", ["7z", "bsdtar"])
def test_a_7z_member_is_unpacked_with_the_installed_tool(tmp_path, tool):
    creator = shutil.which("7z") or shutil.which("7za")
    extractor = shutil.which(tool)
    if not creator or not extractor:
        pytest.skip(f"needs 7z and {tool}")
    staging = tmp_path / "staging" / "Firmware"
    staging.mkdir(parents=True)
    (staging / "BC250_3.00_MeiMeiDXEv3-CachyOS").write_bytes(PAYLOAD)
    archive_path = tmp_path / "Firmware.7z"
    subprocess.run([creator, "a", "-bd", str(archive_path), "Firmware"],
                   cwd=staging.parent, check=True, capture_output=True)
    archive_bytes = archive_path.read_bytes()
    archive = _remote(archive_bytes, name="Firmware.7z")
    rom = ArchivedFile(archive=archive, member="Firmware/BC250_3.00_MeiMeiDXEv3-CachyOS",
                       sha256=_sha(PAYLOAD), size=len(PAYLOAD),
                       name="BC250_3.00_MeiMeiDXEv3-CachyOS")
    store = FirmwareStore(tmp_path / "cache", opener=_Opener({archive.url: archive_bytes}),
                          seven_zip=lambda: extractor)
    path = store.ensure(rom)
    assert sha256_of(path) == rom.sha256


def test_a_7z_tool_that_fails_reports_its_error(tmp_path):
    archive = _remote(b"not really 7z", name="Firmware.7z")
    rom = ArchivedFile(archive=archive, member="Firmware/X", sha256=_sha(PAYLOAD),
                       size=len(PAYLOAD), name="X")
    false = shutil.which("false")
    if not false:
        pytest.skip("needs false(1)")
    store = FirmwareStore(tmp_path, opener=_Opener({archive.url: b"not really 7z"}),
                          seven_zip=lambda: false)
    with pytest.raises(RuntimeError, match="Could not unpack X"):
        store.ensure(rom)
