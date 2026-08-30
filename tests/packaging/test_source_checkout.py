import os
import subprocess
import tarfile

import pytest

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.source_checkout import (
    SourceCheckoutError,
    clone_or_update,
    clone_or_update_branch,
    clone_or_update_commit,
    clone_or_update_commit_with_archive,
    clone_or_update_with_archive,
)

URL = "https://github.com/example/project"
COMMIT = "a" * 40


@pytest.mark.parametrize(
    ("builder", "args"),
    (
        (clone_or_update, ()),
        (clone_or_update_branch, ("feature/safe",)),
        (clone_or_update_commit, (COMMIT,)),
        (clone_or_update_commit_with_archive, (COMMIT,)),
        (clone_or_update_with_archive, ("main",)),
    ),
)
def test_checkout_builders_generate_valid_bash(tmp_path, builder, args):
    command = builder(URL, tmp_path / "tool with spaces", *args)
    completed = subprocess.run(
        ["bash", "-n", "-c", command], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_repository_checkout_methods_delegate_without_output_change(tmp_path):
    repository = DependenciasRepository()
    destination = tmp_path / "tool"
    assert repository._clone_or_update_command(URL, destination) == clone_or_update(URL, destination)
    assert repository._clone_or_update_branch_command(URL, destination, "main") == clone_or_update_branch(URL, destination, "main")
    assert repository._clone_or_update_commit_command(URL, destination, COMMIT) == clone_or_update_commit(URL, destination, COMMIT)
    assert repository._clone_or_update_commit_with_archive_command(URL, destination, COMMIT) == clone_or_update_commit_with_archive(URL, destination, COMMIT)
    assert repository._clone_or_update_with_archive_command(URL, destination) == clone_or_update_with_archive(URL, destination)


def test_hardware_checkout_fails_closed_for_unregistered_upstream(tmp_path):
    repository = DependenciasRepository()
    repository._clone_or_update_command = lambda *_args: pytest.fail(
        "mutable checkout must never be used for hardware source"
    )
    with pytest.raises(ValueError, match="immutable reviewed revision"):
        repository._hardware_source_checkout_command(URL, tmp_path / "tool")


def test_hardware_checkout_uses_manifest_revision_on_every_distribution(tmp_path):
    from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS

    repository = DependenciasRepository()
    observed = []
    repository._clone_or_update_commit_command = (
        lambda upstream, destination, revision: observed.append(
            (upstream, destination, revision)
        ) or "pinned"
    )
    fake_os = type("OS", (), {"info": type("Info", (), {"family": "ubuntu"})()})()
    spec = EXTERNAL_TOOLS["cu_manager_standard"]
    result = repository._hardware_source_checkout_command(
        spec.upstream, tmp_path / "cu", fake_os
    )
    assert result == "pinned"
    assert observed == [(spec.upstream, tmp_path / "cu", spec.reviewed_revision)]


@pytest.mark.parametrize("destination", ("relative", "/"))
def test_destructive_destinations_fail_before_shell_generation(destination):
    with pytest.raises(SourceCheckoutError, match="safe absolute"):
        clone_or_update(URL, destination)


@pytest.mark.parametrize(
    "url", ("http://example.test/tool", "file:///tmp/tool", "https://user:pass@example.test/tool")
)
def test_noncanonical_or_credentialed_urls_are_rejected(tmp_path, url):
    with pytest.raises(SourceCheckoutError, match="canonical HTTPS"):
        clone_or_update(url, tmp_path / "tool")


def test_commit_and_branch_are_strictly_validated(tmp_path):
    with pytest.raises(SourceCheckoutError, match="40-character"):
        clone_or_update_commit(URL, tmp_path / "tool", "main")
    with pytest.raises(SourceCheckoutError, match="unsupported"):
        clone_or_update_branch(URL, tmp_path / "tool", "../../escape")


def test_reviewed_commit_checkout_discards_interrupted_tracked_build_edits(tmp_path):
    command = clone_or_update_commit(URL, tmp_path / "tool", COMMIT)

    assert "checkout --detach --force FETCH_HEAD" in command


def test_moving_branch_checkout_reasserts_official_origin_and_upstream_head(tmp_path):
    command = clone_or_update_branch(URL, tmp_path / "tool", "main")

    assert f"remote set-url origin {URL}" in command
    assert "fetch --depth 1 origin main" in command
    assert "checkout -B main FETCH_HEAD" in command
    assert "reset --hard FETCH_HEAD" in command
    assert "remote get-url origin" in command


def test_exact_commit_archive_fallback_records_reviewed_provenance(tmp_path):
    archive_root = tmp_path / "archive-root" / f"project-{COMMIT}"
    archive_root.mkdir(parents=True)
    (archive_root / "payload.py").write_text("reviewed\n", encoding="utf-8")
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(archive_root, arcname=archive_root.name)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    for command in ("find", "gzip", "mkdir", "mktemp", "mv", "rm", "tar"):
        (bindir / command).symlink_to(f"/usr/bin/{command}")
    curl = bindir / "curl"
    curl.write_text(
        '#!/usr/bin/bash\ncp "$BC250_TEST_ARCHIVE" "${@: -1}"\n', encoding="utf-8"
    )
    curl.chmod(0o755)
    (bindir / "cp").symlink_to("/usr/bin/cp")
    destination = tmp_path / "prepared tool"
    command = clone_or_update_commit_with_archive(URL, destination, COMMIT)

    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": str(bindir),
            "BC250_TEST_ARCHIVE": str(archive),
            "TMPDIR": str(tmp_path),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (destination / "payload.py").read_text(encoding="utf-8") == "reviewed\n"
    assert (destination / ".bc250-source-url").read_text(encoding="utf-8").strip() == URL
    assert (destination / ".bc250-source-revision").read_text(encoding="utf-8").strip() == COMMIT


def test_exact_commit_archive_failure_preserves_previous_checkout(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for command in ("find", "mkdir", "mktemp", "mv", "rm", "tar"):
        (bindir / command).symlink_to(f"/usr/bin/{command}")
    curl = bindir / "curl"
    curl.write_text(
        '#!/usr/bin/bash\nprintf "not-a-tar" > "${@: -1}"\n', encoding="utf-8"
    )
    curl.chmod(0o755)
    destination = tmp_path / "prepared-tool"
    destination.mkdir()
    (destination / "keep.txt").write_text("known-good\n", encoding="utf-8")
    command = clone_or_update_commit_with_archive(URL, destination, COMMIT)

    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": str(bindir)},
    )

    assert result.returncode != 0
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "known-good\n"
    assert not list(tmp_path.glob(".bc250-source.*"))


def test_exact_commit_archive_fallback_rejects_non_github_provider(tmp_path):
    with pytest.raises(SourceCheckoutError, match="GitHub"):
        clone_or_update_commit_with_archive(
            "https://gitlab.com/example/project", tmp_path / "tool", COMMIT
        )
