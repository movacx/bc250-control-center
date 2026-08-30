"""Validated shell builders for fetching reviewed external source trees."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from urllib.parse import urlparse


class SourceCheckoutError(ValueError):
    pass


def _inputs(repository_url, destination) -> tuple[str, Path, str, str]:
    url = str(repository_url).strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise SourceCheckoutError("Source repository must use a canonical HTTPS URL")
    destination = Path(destination)
    if not destination.is_absolute() or destination in {Path("/"), Path.home()}:
        raise SourceCheckoutError("Source destination must be a safe absolute child directory")
    if ".." in destination.parts:
        raise SourceCheckoutError("Source destination cannot contain parent traversal")
    return url, destination, shlex.quote(url), shlex.quote(str(destination))


def clone_or_update(repository_url, destination) -> str:
    _url, destination, qurl, qdest = _inputs(repository_url, destination)
    qparent = shlex.quote(str(destination.parent))
    return (
        f"mkdir -p {qparent}; "
        f"if [ -d {qdest}/.git ]; then "
        f"git -C {qdest} pull --ff-only; "
        f"else rm -rf {qdest}; git clone --depth 1 {qurl} {qdest}; fi"
    )


def clone_or_update_branch(repository_url, destination, branch) -> str:
    _url, destination, qurl, qdest = _inputs(repository_url, destination)
    branch = str(branch)
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", branch) or ".." in branch.split("/"):
        raise SourceCheckoutError("Source branch contains unsupported characters")
    qparent = shlex.quote(str(destination.parent))
    qbranch = shlex.quote(branch)
    return (
        f"mkdir -p {qparent}; "
        f"if [ -d {qdest}/.git ]; then "
        f"git -C {qdest} remote set-url origin {qurl}; "
        f"git -C {qdest} fetch --depth 1 origin {qbranch}; "
        f"git -C {qdest} checkout -B {qbranch} FETCH_HEAD; "
        f"git -C {qdest} reset --hard FETCH_HEAD; "
        f"else rm -rf {qdest}; "
        f"git clone --depth 1 --branch {qbranch} {qurl} {qdest}; fi; "
        f'test "$(git -C {qdest} remote get-url origin)" = {qurl} || '
        f'{{ echo "ERROR: upstream origin mismatch: {_url}"; exit 29; }}; '
        f'echo "[INFO] Current upstream source: {_url} @ $(git -C {qdest} rev-parse --short=12 HEAD)"'
    )


def clone_or_update_commit(repository_url, destination, commit) -> str:
    url, destination, qurl, qdest = _inputs(repository_url, destination)
    commit = str(commit).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SourceCheckoutError("Reviewed source commit must be a full 40-character SHA-1")
    qparent = shlex.quote(str(destination.parent))
    qcommit = shlex.quote(commit)
    return (
        f"mkdir -p {qparent}; "
        f"if [ ! -d {qdest}/.git ]; then "
        f"rm -rf {qdest}; git clone --depth 1 {qurl} {qdest}; fi; "
        f"git -C {qdest} remote set-url origin {qurl}; "
        f"git -C {qdest} fetch --depth 1 origin {qcommit}; "
        # Builders may deliberately patch a reviewed worktree before
        # compiling it (for example, Oberon's yaml-cpp pin).  A retry after a
        # partial build must start from the exact upstream tree again: plain
        # checkout leaves a tracked local edit intact when HEAD is unchanged.
        f"git -C {qdest} checkout --detach --force FETCH_HEAD; "
        f'test "$(git -C {qdest} rev-parse HEAD)" = {qcommit} || '
        f'{{ echo "ERROR: reviewed source revision was not checked out: {url}"; exit 29; }}; '
        f'echo "[INFO] Reviewed source: {url} @ {commit[:12]}"'
    )


def clone_or_update_commit_with_archive(repository_url, destination, commit) -> str:
    """Fetch one immutable GitHub commit, with a tar fallback for immutable hosts.

    The archive path records both canonical origin and exact revision so health
    checks never confuse a mutable branch archive with reviewed provenance.
    """
    url, destination, qurl, qdest = _inputs(repository_url, destination)
    commit = str(commit).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SourceCheckoutError("Reviewed source commit must be a full 40-character SHA-1")
    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        raise SourceCheckoutError("Immutable archive fallback currently supports canonical GitHub repositories only")
    qparent = shlex.quote(str(destination.parent))
    qcommit = shlex.quote(commit)
    archive_url = shlex.quote(f'{url.rstrip("/")}/archive/{commit}.tar.gz')
    git_checkout = clone_or_update_commit(url, destination, commit)
    return (
        f"if command -v git >/dev/null 2>&1; then {git_checkout}; "
        f"elif command -v tar >/dev/null 2>&1 && "
        f"(command -v curl >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1); then "
        f"mkdir -p {qparent}; tmpdir=\"$(mktemp -d {qparent}/.bc250-source.XXXXXX)\"; "
        f"trap 'rm -rf -- \"$tmpdir\"' EXIT; "
        f"if command -v curl >/dev/null 2>&1; then "
        f"curl --fail --location --retry 3 {archive_url} -o \"$tmpdir/source.tar.gz\"; "
        f"else python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "
        f"{archive_url} \"$tmpdir/source.tar.gz\"; fi; "
        f"stage=\"$tmpdir/tree\"; previous=\"$tmpdir/previous\"; mkdir -p \"$stage\"; "
        f"tar -xzf \"$tmpdir/source.tar.gz\" --strip-components=1 --no-same-owner --no-same-permissions -C \"$stage\"; "
        f"test -n \"$(find \"$stage\" -mindepth 1 -print -quit)\" || "
        f"{{ echo \"ERROR: reviewed source archive was empty: {url}\"; exit 29; }}; "
        f"printf '%s\\n' {qurl} > \"$stage/.bc250-source-url\"; "
        f"printf '%s\\n' {qcommit} > \"$stage/.bc250-source-revision\"; "
        f"if [ -e {qdest} ] || [ -L {qdest} ]; then mv -- {qdest} \"$previous\"; fi; "
        f"if mv -- \"$stage\" {qdest}; then rm -rf -- \"$previous\"; "
        f"else rm -rf -- {qdest}; if [ -e \"$previous\" ] || [ -L \"$previous\" ]; then mv -- \"$previous\" {qdest}; fi; exit 29; fi; "
        f"rm -rf -- \"$tmpdir\"; trap - EXIT; "
        f"else echo \"ERROR: git or tar with curl/python3 is required to fetch reviewed source: {url}\"; exit 29; fi"
    )


def clone_or_update_with_archive(repository_url, destination, branch="main") -> str:
    url, destination, qurl, qdest = _inputs(repository_url, destination)
    branch = str(branch)
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", branch) or ".." in branch.split("/"):
        raise SourceCheckoutError("Source branch contains unsupported characters")
    qparent = shlex.quote(str(destination.parent))
    qbranch = shlex.quote(branch)
    archive_url = shlex.quote(f'{url.rstrip("/")}/archive/refs/heads/{branch}.tar.gz')
    return (
        f"mkdir -p {qparent}; "
        f"if command -v git >/dev/null 2>&1; then "
        f"if [ -d {qdest}/.git ]; then "
        f"git -C {qdest} fetch --depth 1 origin {qbranch}; "
        f"git -C {qdest} checkout {qbranch}; "
        f"git -C {qdest} merge --ff-only FETCH_HEAD; "
        f"else rm -rf {qdest}; git clone --depth 1 --branch {qbranch} {qurl} {qdest}; fi; "
        f"elif command -v tar >/dev/null 2>&1 && (command -v curl >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1); then "
        f'tmpdir="$(mktemp -d)"; '
        f"if command -v curl >/dev/null 2>&1; then curl --fail --location --retry 3 {archive_url} -o \"$tmpdir/source.tar.gz\"; else python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' {archive_url} \"$tmpdir/source.tar.gz\"; fi; "
        f"rm -rf {qdest}; mkdir -p {qdest}; "
        f'tar -xzf "$tmpdir/source.tar.gz" --strip-components=1 -C {qdest}; '
        f"printf '%s\\n' {qurl} > {qdest}/.bc250-source-url; "
        f'rm -rf "$tmpdir"; '
        f'else echo "ERROR: git or tar with curl/python3 is required to fetch {url}"; exit 29; fi'
    )
