"""Headless diagnostics and planning CLI for BC250 Control Center.

Mutating dependency application is deliberately double-gated. Hardware write
operations are not exposed here; they must continue through typed privileged
helpers and their subsystem-specific safety workflows.
"""

from __future__ import annotations

import argparse
import json
import shutil

# The argv is fixed; generated commands come only from repository strategies.
import subprocess  # nosec B404
from pathlib import Path

from bc250cc.application.headless_dispatch import dispatch_safe
from bc250cc.infrastructure.persistence.config_paths import app_data_dir
from bc250cc.platform.packages.strategies.detector import (
    detect_os_info,
    read_os_release,
)
from bc250cc.platform.packages.strategies.factory import create_os_repository
from bc250cc.shared.version import __version__


class HeadlessHost:
    def _os_release(self):
        return read_os_release()

    def _command_path(self, name: str) -> str:
        return shutil.which(name) or ""

    def _tool_dir(self) -> Path:
        return app_data_dir() / "ResourceTools"

    def _home(self) -> Path:
        return Path.home()

    @staticmethod
    def _execute_readonly(command, timeout=2):
        try:
            completed = subprocess.run(  # nosec B603
                command,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return completed.returncode, completed.stdout or "", completed.stderr or ""
        except (OSError, subprocess.SubprocessError) as error:
            return 1, "", str(error)


def _emit(payload, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bc250-control-center-cli",
        description="BC250 Control Center safe headless interface",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("system", help="Show detected Linux strategy")
    commands.add_parser("components", help="Show preparation component capabilities")
    integrations = commands.add_parser("integrations", help="Audit external-tool contracts and checkouts")
    integrations.add_argument(
        "--runtime", action="store_true",
        help="Include read-only local checkout origin/revision/worktree evidence",
    )
    commands.add_parser(
        "quick-access",
        help="Inspect optional Decky Quick Access deployment without changing it",
    )
    integrations.add_argument(
        "--tool", default="",
        help="Limit output to one declared integration key",
    )
    release_gates = commands.add_parser(
        "release-gates",
        help="Show static, legal and supervised hardware release blockers",
    )
    release_gates.add_argument(
        "--evidence", action="append", default=[], metavar="PATH",
        help="Validate and include a supervised qualification evidence manifest",
    )
    qualification = commands.add_parser(
        "qualification",
        help="Render or validate supervised hardware qualification evidence",
    )
    qualification.add_argument(
        "action", choices=("template", "validate", "export", "validate-bundle")
    )
    qualification.add_argument("path", nargs="?")
    qualification.add_argument(
        "--output", help="Destination for a portable verified qualification ZIP"
    )
    qualification.add_argument(
        "--section",
        choices=("cpu_smu", "gpu_governors", "compute_units", "fan_pwm", "core_unlock_and_boot"),
    )

    dependency = commands.add_parser("dependencies", help="Plan, check or explicitly apply dependencies")
    dependency.add_argument("--component", choices=("all", "runtime", "governor", "stress", "sensors", "umr"), default="all")
    dependency.add_argument("--mode", choices=("plan", "check", "apply"), default="plan")
    dependency.add_argument("--cu-manager-script", default="")
    dependency.add_argument("--allow-system-changes", action="store_true")
    dependency.add_argument("--yes", action="store_true")
    dependency.add_argument("--render-command", action="store_true")

    log = commands.add_parser("parse-log", help="Parse structured evidence from a workflow log")
    log.add_argument("path")
    log.add_argument("--exit-code", type=int)

    recovery = commands.add_parser("recovery", help="Create, list, verify or inspect a recovery bundle")
    recovery.add_argument("action", choices=("create", "list", "verify", "plan", "export"))
    recovery.add_argument("snapshot", nargs="?")
    recovery.add_argument("--label", default="manual-before-change")
    recovery.add_argument("--output", help="Destination for a portable verified recovery ZIP")

    profiles = commands.add_parser("profiles", help="Export, preview or import portable profiles")
    profiles.add_argument("action", choices=("export", "preview", "import"))
    profiles.add_argument("path")
    profiles.add_argument("--yes", action="store_true", help="Confirm replacement during import")

    metrics = commands.add_parser("metrics", help="Read or export recorded runtime metrics")
    metrics.add_argument("action", choices=("list", "export"))
    metrics.add_argument("--path")
    metrics.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    metrics.add_argument("--limit", type=int, default=1000)
    metrics.add_argument("--since", type=float)
    return parser


def _run_dependencies(args, host, runner) -> int:
    if (
        args.mode == "apply"
        and not args.render_command
        and not (args.allow_system_changes and args.yes)
    ):
        raise SystemExit(
            "Refusing apply: pass both --allow-system-changes and --yes "
            "after reviewing --mode plan."
        )
    repository = create_os_repository(host)
    command = repository.prepare_dependencies_command(
        args.component, cu_manager_script=args.cu_manager_script, mode=args.mode
    )
    if args.render_command:
        _emit({"mode": args.mode, "command": command}, as_json=args.json)
        return 0
    completed = runner(["bash", "-lc", command], check=False)
    return int(completed.returncode)


def main(argv: list[str] | None = None, *, host=None, runner=subprocess.run) -> int:
    args = _parser().parse_args(argv)
    host = host or HeadlessHost()
    os_info = detect_os_info(
        host._os_release(), has_rpm_ostree=bool(host._command_path("rpm-ostree"))
    )
    result = dispatch_safe(args, os_info, host=host)
    if result is not None:
        _emit(result.payload, as_json=args.json)
        return result.exit_code
    return _run_dependencies(args, host, runner)
if __name__ == "__main__":
    raise SystemExit(main())
