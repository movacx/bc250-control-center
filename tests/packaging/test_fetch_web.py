"""The built web interface is downloaded from the project's releases and verified, or not used at all."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch_web = load("scripts/lib/fetch_web.py")
packer = load("scripts/development/empaquetar_web.py")


def archive(*members):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            data = b"x" if kind == tarfile.REGTYPE else b""
            info.size, info.linkname = len(data), "/etc/passwd"
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue()


GOOD = archive(("webApp.js", tarfile.REGTYPE), ("index.html", tarfile.REGTYPE), ("a/b.xml", tarfile.REGTYPE))


@pytest.fixture
def copy(tmp_path):
    (tmp_path / "frontends/web").mkdir(parents=True)

    def pin(data=GOOD, url=fetch_web.PREFIX + "web-builds/web.tar.gz"):
        (tmp_path / "frontends/web/web-build.json").write_text(
            json.dumps({"url": url, "sha256": hashlib.sha256(data).hexdigest()}), encoding="utf-8")
        return tmp_path

    return pin


def serve(data):
    return lambda request, timeout: io.BytesIO(data)


def never(*_a, **_k):
    raise AssertionError("nothing should be downloaded")


def test_a_clone_gets_the_pinned_build_once(copy):
    root = copy()
    assert fetch_web.fetch(root, serve(GOOD)) is True
    assert (root / "frontends/web/dist/a/b.xml").read_bytes() == b"x"
    assert fetch_web.fetch(root, never) is False


def test_a_new_pin_replaces_a_downloaded_build_but_never_one_built_here(copy):
    root = copy()
    fetch_web.fetch(root, serve(GOOD))
    newer = archive(("webApp.js", tarfile.REGTYPE), ("index.html", tarfile.REGTYPE))
    copy(newer)
    assert fetch_web.fetch(root, serve(newer)) is True
    assert not (root / "frontends/web/dist/a").exists()
    (root / "frontends/web/dist" / fetch_web.MARKER).unlink()
    copy(GOOD)
    assert fetch_web.fetch(root, never) is False


def test_a_different_file_is_refused_and_nothing_changes(copy):
    root = copy()
    with pytest.raises(fetch_web.WebBuildError, match="checksum"):
        fetch_web.fetch(root, serve(GOOD + b"!"))
    assert not (root / "frontends/web/dist").exists()


@pytest.mark.parametrize("member", [("../out", tarfile.REGTYPE), ("/out", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)])
def test_an_archive_cannot_write_outside(copy, member):
    data = archive(("webApp.js", tarfile.REGTYPE), ("index.html", tarfile.REGTYPE), member)
    root = copy(data)
    with pytest.raises(fetch_web.WebBuildError, match="unexpected"):
        fetch_web.fetch(root, serve(data))
    assert [path.name for path in (root / "frontends/web").iterdir()] == ["web-build.json"]


def test_only_the_projects_own_releases(copy):
    root = copy(url="https://example.com/web.tar.gz")
    with pytest.raises(fetch_web.WebBuildError, match="not the project"):
        fetch_web.fetch(root, never)


def test_the_package_is_the_same_bytes_every_time_and_can_be_fetched(tmp_path, copy):
    dist = tmp_path / "built"
    (dist / "x").mkdir(parents=True)
    for name in ("webApp.js", "index.html", "x/y.xml"):
        (dist / name).write_text("hi", encoding="utf-8")
    data = packer.empaquetar(dist)
    assert data == packer.empaquetar(dist)
    root = copy(data)
    assert fetch_web.fetch(root, serve(data)) is True


def test_this_copy_names_a_valid_build():
    assert fetch_web.pinned(ROOT)["url"].endswith(".tar.gz")


def test_the_built_files_are_not_in_git():
    assert "!frontends/web/dist/" not in (ROOT / ".gitignore").read_text(encoding="utf-8")
