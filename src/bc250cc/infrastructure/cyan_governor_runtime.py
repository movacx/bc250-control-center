from __future__ import annotations

import hashlib
import re
import shlex
from functools import lru_cache
from pathlib import Path

from bc250cc.platform.init.services import detect_init_manager

CYAN_FREQUENCY_FIX_MARKER = b"GPU frequency fix enabled"
# Upstream versions have emitted both messages.  The bind-mount variant means
# the active kernel lacks the optional gpu_metrics destination and Cyan exits
# before it can publish D-Bus, so it is just as actionable as a write error.
CYAN_METRICS_FIX_FAILURE_MARKERS = (
    "GPU usage metrics fix write failed",
    "patched_gpu_metrics",
)
CYAN_METRICS_FIX_FAILURE_MARKER = CYAN_METRICS_FIX_FAILURE_MARKERS[0]
CYAN_MANAGED_BINARY = Path("/usr/local/bin/cyan-skillfish-governor-smu")
CYAN_PACKAGED_BINARY = Path("/usr/bin/cyan-skillfish-governor-smu")
CYAN_SERVICE = "cyan-skillfish-governor-smu.service"
CYAN_CONFIG = Path("/etc/cyan-skillfish-governor-smu/config.toml")
CYAN_STATE_DIR = Path("/var/lib/bc250-control-center/cyan-governor")
#: The release Prepare installs: upstream's own, unmodified (see
#: install-cyan-upstream-release.sh). Releases before 1.21.2 built it with a
#: Control Center patch and left these files behind; their presence marks
#: that runtime.
CYAN_REVIEWED_RELEASE = "v0.4.14"
CYAN_LEGACY_STATE_FILES = ("runtime-revision", "upstream-commit", "patcher-sha256", "binary-sha256")


def managed_runtime_update_available(
    state_dir: Path = CYAN_STATE_DIR,
    managed_binary: Path = CYAN_MANAGED_BINARY,
) -> bool:
    """Whether Prepare would replace the Cyan binary Control Center manages.

    Read from the files Prepare leaves, without running anything, so the
    dependency snapshot can afford it: an older release, or the patched build
    of a Control Center before 1.21.2. A governor installed only by the
    distribution or by upstream's own installer is never flagged.
    """
    try:
        if not managed_binary.is_file():
            return False
        if any((state_dir / name).exists() for name in CYAN_LEGACY_STATE_FILES):
            return True
        release = (state_dir / "release").read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not release or release == CYAN_REVIEWED_RELEASE:
        return False
    # Only an older release: a newer one built by hand is not "updated" back.
    mine, reviewed = _release_numbers(release), _release_numbers(CYAN_REVIEWED_RELEASE)
    return mine is None or mine < reviewed


def _release_numbers(release: str) -> tuple[int, ...] | None:
    """``v0.4.14`` -> (0, 4, 14); None for anything that is not a plain release."""
    match = re.fullmatch(r"v?(\d{1,4})\.(\d{1,4})(?:\.(\d{1,4}))?", release.strip())
    return tuple(int(part) for part in match.groups() if part is not None) if match else None


@lru_cache(maxsize=8)
def _binary_contains_marker(path: str, size: int, mtime_ns: int) -> bool:
    del size, mtime_ns  # Cache keys invalidate the read after an atomic update.
    candidate = Path(path)
    overlap = b""
    with candidate.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            probe = overlap + chunk
            if CYAN_FREQUENCY_FIX_MARKER in probe:
                return True
            overlap = probe[-len(CYAN_FREQUENCY_FIX_MARKER):]
    return False


def binary_supports_frequency_fix(path: str | Path) -> bool:
    """Return whether a Cyan binary contains the upstream 8-core clock fix.

    ``--version`` cannot distinguish v0.4.11 builds made before the option was
    added from locally rebuilt packages carrying later commits.  The stable log
    marker is part of the actual execution branch, so checking it avoids
    claiming that a TOML key is supported merely because the key was written.
    Reads are bounded to keep health checks cheap and defensive.
    """

    candidate = Path(path)
    try:
        metadata = candidate.stat()
        if not candidate.is_file() or metadata.st_size > 64 * 1024 * 1024:
            return False
        return _binary_contains_marker(
            str(candidate), metadata.st_size, metadata.st_mtime_ns
        )
    except OSError:
        return False


def parse_systemd_exec_path(value: object) -> str:
    """Extract systemd's executable path from ``systemctl show ExecStart``."""

    match = re.search(r"(?:^|[ {;])path=([^ ;}]+)", str(value or ""))
    return match.group(1) if match else ""


def parse_openrc_command_path(value: object) -> str:
    """Read the executable declared by a managed ``openrc-run`` script."""
    match = re.search(r"^\s*command\s*=\s*[\"']?([^\s\"']+)", str(value or ""), re.MULTILINE)
    return match.group(1) if match else ""



def parse_systemd_exec_argv(value: object) -> tuple[str, ...]:
    """Extract argv from systemd's structured ExecStart property."""

    match = re.search(r"(?:^|[ {;])argv\[\]=([^;}]+)", str(value or ""))
    if not match:
        return ()
    try:
        return tuple(shlex.split(match.group(1).strip()))
    except ValueError:
        return ()


def parse_openrc_command_args(value: object) -> tuple[str, ...]:
    match = re.search(
        r"^\s*command_args\s*=\s*(.+?)\s*$", str(value or ""), re.MULTILINE
    )
    if not match:
        return ()
    raw = match.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        raw = raw[1:-1]
    try:
        return tuple(shlex.split(raw))
    except ValueError:
        return ()


@lru_cache(maxsize=8)
def _sha256_cached(path: str, size: int, mtime_ns: int) -> str:
    """Hash one bounded runtime binary and cache by immutable file metadata."""

    del size, mtime_ns  # They intentionally participate in the cache key.
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: str | Path) -> str:
    candidate = Path(path)
    try:
        metadata = candidate.stat()
        if not candidate.is_file() or metadata.st_size > 64 * 1024 * 1024:
            return ""
        return _sha256_cached(
            str(candidate), metadata.st_size, metadata.st_mtime_ns
        )
    except OSError:
        return ""


def detect_cyan_runtime_identity(repository) -> dict[str, object]:
    """Return the executable and TOML actually selected by the active service.

    Control Center's privileged editor intentionally manages one reviewed path.
    This probe prevents a successful edit of that file from being mistaken for
    a successful runtime change when a stale service points at another TOML.
    """

    manager = detect_init_manager().kind
    service_path = ""
    config_path = ""
    raw_exec = ""
    runner = getattr(repository, "_ejecutar", None)

    if manager == "openrc":
        try:
            text = Path("/etc/init.d/cyan-skillfish-governor-smu").read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            text = ""
        service_path = parse_openrc_command_path(text)
        arguments = parse_openrc_command_args(text)
        if arguments:
            config_path = arguments[0]
        raw_exec = text
    elif manager == "systemd" and callable(runner):
        try:
            code, stdout, _stderr = runner(
                ["systemctl", "show", CYAN_SERVICE, "-p", "ExecStart", "--value"],
                timeout=4,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            code, stdout = 1, ""
        if code == 0:
            raw_exec = str(stdout or "")
            service_path = parse_systemd_exec_path(raw_exec)
            argv = parse_systemd_exec_argv(raw_exec)
            if argv:
                if not service_path:
                    service_path = argv[0]
                if len(argv) >= 2:
                    config_path = argv[1]

    if not service_path:
        resolver = getattr(repository, "_command_path", None)
        if callable(resolver):
            try:
                service_path = str(resolver("cyan-skillfish-governor-smu") or "")
            except (OSError, RuntimeError, TypeError, ValueError):
                service_path = ""
    if not config_path:
        config_path = str(CYAN_CONFIG)

    version = ""
    if service_path and callable(runner):
        try:
            code, stdout, stderr = runner([service_path, "--version"], timeout=4)
        except (OSError, RuntimeError, TypeError, ValueError):
            code, stdout, stderr = 1, "", ""
        if code == 0:
            version = (stdout or stderr or "").strip().splitlines()[0] if (stdout or stderr) else ""

    binary_sha256 = _sha256_file(service_path) if service_path else ""

    def read_state(name: str) -> str:
        try:
            return (CYAN_STATE_DIR / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    managed_release = read_state("release")
    legacy_patched = any((CYAN_STATE_DIR / name).exists() for name in CYAN_LEGACY_STATE_FILES)
    managed = service_path == str(CYAN_MANAGED_BINARY)
    return {
        "init_manager": manager,
        "binary_path": service_path,
        "binary_sha256": binary_sha256,
        "version": version,
        "config_path": config_path,
        "config_matches_managed_path": Path(config_path) == CYAN_CONFIG,
        # The service runs the binary Prepare installs, rather than the
        # distribution's package or an upstream install of its own.
        "runtime_managed": managed,
        "runtime_release": managed_release,
        "runtime_legacy_patched": legacy_patched,
        # What Prepare would change: an older release, or the patched build
        # of an earlier Control Center, is still the one the service runs.
        "runtime_update_available": bool(
            managed and (legacy_patched or (managed_release and managed_release != CYAN_REVIEWED_RELEASE))
        ),
        "raw_exec": raw_exec,
    }

def detect_cyan_frequency_fix_runtime(repository) -> dict[str, object]:
    """Describe the binary selected by the active init manager, not ``$PATH``.

    The package and the BC250-managed override may coexist intentionally.  The
    service's prepared ExecStart is therefore authoritative; fixed candidates
    are only fallbacks when systemd is unavailable during tests or staging.
    """

    service_path = ""
    manager = detect_init_manager().kind
    runner = getattr(repository, "_ejecutar", None)
    if manager == "openrc":
        try:
            openrc_script = Path("/etc/init.d/cyan-skillfish-governor-smu")
            stdout = openrc_script.read_text(encoding="utf-8", errors="replace")
            code = 0
        except (OSError, RuntimeError, TypeError, ValueError):
            code, stdout = 1, ""
        if code == 0:
            service_path = parse_openrc_command_path(stdout)
    elif manager == "systemd" and callable(runner):
        try:
            code, stdout, _stderr = runner(
                ["systemctl", "show", CYAN_SERVICE, "-p", "ExecStart", "--value"],
                timeout=4,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            code, stdout = 1, ""
        if code == 0:
            service_path = parse_systemd_exec_path(stdout)

    candidates: list[str] = []
    for candidate in (service_path, str(CYAN_MANAGED_BINARY), str(CYAN_PACKAGED_BINARY)):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    resolver = getattr(repository, "_command_path", None)
    if callable(resolver):
        try:
            resolved = str(resolver("cyan-skillfish-governor-smu") or "")
        except (OSError, RuntimeError, TypeError, ValueError):
            resolved = ""
        if resolved and resolved not in candidates:
            candidates.append(resolved)

    inspected = [
        {"path": candidate, "supports_frequency_fix": binary_supports_frequency_fix(candidate)}
        for candidate in candidates
        if Path(candidate).is_file()
    ]
    authoritative = service_path or (inspected[0]["path"] if inspected else "")
    authoritative_support = binary_supports_frequency_fix(authoritative) if authoritative else False
    return {
        "service_path": service_path,
        "binary_path": authoritative,
        "supports_frequency_fix": authoritative_support,
        "managed_override": service_path == str(CYAN_MANAGED_BINARY),
        "init_manager": manager,
        "candidates": inspected,
    }


def detect_cyan_metrics_fix_runtime(
    repository, *, lookback_seconds: int = 5, whole_boot: bool = False
) -> dict[str, object]:
    """Report a runtime failure from Cyan's optional metrics overlay.

    The configuration flag alone cannot prove that the bind-mounted
    ``gpu_metrics`` overlay is usable on a given kernel.  Cyan emits one
    stable error when its update path fails.  Restricting the journal window
    prevents a repaired service from being reported as broken because of an
    older boot-time record.

    ``whole_boot`` widens the window to the current boot, which is the same
    evidence the startup guard generated in ``gpu_repository`` uses. The two
    must agree: a narrower window here let the interface accept
    ``fix-metrics = true`` while the guard, still seeing the failure, refused
    to start the service — the request was written to config.toml, the restart
    was refused, and the rollback churned the governor.
    """

    try:
        seconds = max(1, min(60, int(lookback_seconds)))
    except (TypeError, ValueError):
        seconds = 5
    result = {
        "metrics_fix_runtime_error": False,
        "metrics_fix_error": "",
        "metrics_fix_journal_checked": False,
    }
    if detect_init_manager().kind != "systemd":
        # Non-systemd managers do not promise journald. Absence of a journal must never
        # be turned into a false "GPU metrics healthy" conclusion.
        result["metrics_fix_log_supported"] = False
        return result
    result["metrics_fix_log_supported"] = True
    runner = getattr(repository, "_ejecutar", None)
    if not callable(runner):
        return result
    try:
        window = (
            ["-n", "120"] if whole_boot else ["--since", f"{seconds} seconds ago"]
        )
        code, stdout, stderr = runner(
            ["journalctl", "-b", "-u", CYAN_SERVICE, *window, "--no-pager", "-o", "cat"],
            timeout=4,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return result
    if code != 0:
        return result
    result["metrics_fix_journal_checked"] = True
    text = f"{stdout or ''}\n{stderr or ''}"
    marker = next(
        (candidate for candidate in CYAN_METRICS_FIX_FAILURE_MARKERS if candidate in text),
        "",
    )
    if marker:
        result["metrics_fix_runtime_error"] = True
        result["metrics_fix_error"] = marker
    return result
