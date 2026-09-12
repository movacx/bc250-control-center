"""Use-case dispatch for the safe headless interface.

Handlers return data and exit status; argument parsing, presentation and the
only subprocess boundary remain in the CLI frontend.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType

from bc250cc.application.preparation.component_engine import component_capabilities
from bc250cc.application.recovery.release_gates import (
    build_qualification_template,
    build_release_gate_report,
    qualification_requirements,
)
from bc250cc.application.recovery.service import RecoveryRepository
from bc250cc.infrastructure.external_tools.catalog import (
    EXTERNAL_TOOL_LIFECYCLES,
    EXTERNAL_TOOLS,
    GitCheckoutReader,
    build_external_checkout_inventory,
    validate_external_tool_manifest,
)
from bc250cc.infrastructure.external_tools.quick_access_inventory import (
    quick_access_inventory,
)
from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal
from bc250cc.infrastructure.persistence.profile_bundle import (
    ProfileBundleError,
    ProfileBundleRepository,
)
from bc250cc.infrastructure.persistence.qualification_evidence import (
    QualificationEvidenceError,
    export_qualification_bundle,
    validate_qualification_bundle,
    validate_qualification_evidence,
)
from bc250cc.infrastructure.persistence.recovery_engine import (
    RecoverySnapshotRepository,
)
from bc250cc.shared.operation_contract import parse_operation_log


@dataclass(frozen=True)
class DispatchResult:
    payload: object
    exit_code: int = 0


def telemetry_result(_args, _os_info):
    from bc250cc.infrastructure.apu_telemetry import collect_apu_telemetry

    return DispatchResult(collect_apu_telemetry())


def system_result(_args, os_info) -> DispatchResult:
    return DispatchResult(asdict(os_info))


def components_result(_args, os_info) -> DispatchResult:
    return DispatchResult(component_capabilities(os_info))


def integrations_result(args, _os_info, host=None) -> DispatchResult:
    issues = validate_external_tool_manifest()
    selected = str(getattr(args, "tool", "") or "")
    if selected and selected not in EXTERNAL_TOOLS:
        raise SystemExit(f"Unknown external integration: {selected}")
    keys = (selected,) if selected else tuple(EXTERNAL_TOOLS)
    payload = {
        "valid": not issues,
        "issues": {key: issues[key] for key in keys if key in issues},
        "tools": {
            key: {**spec.to_dict(), "lifecycle": EXTERNAL_TOOL_LIFECYCLES[key].to_dict()}
            for key, spec in EXTERNAL_TOOLS.items() if key in keys
        },
    }
    if getattr(args, "runtime", False):
        if host is None:
            raise SystemExit("Runtime integration inventory requires a headless host")
        runner = getattr(host, "_execute_readonly", None)
        if not callable(runner):
            raise SystemExit("Runtime integration inventory runner is unavailable")
        runtime = build_external_checkout_inventory(
            host._tool_dir(), GitCheckoutReader(runner)
        )
        payload["runtime"] = {key: runtime[key] for key in keys}
    return DispatchResult(payload, 0 if payload["valid"] else 3)


def quick_access_result(_args, os_info, host=None) -> DispatchResult:
    home_provider = getattr(host, "_home", None)
    home = home_provider() if callable(home_provider) else None
    return DispatchResult(
        quick_access_inventory(os_family=os_info.family, home=home).to_dict()
    )


def release_gates_result(args, _os_info) -> DispatchResult:
    return DispatchResult(
        build_release_gate_report(tuple(getattr(args, "evidence", ()) or ()))
    )


def qualification_result(args, _os_info) -> DispatchResult:
    if args.action == "template":
        if not args.section:
            raise SystemExit("qualification template requires --section")
        try:
            return DispatchResult(build_qualification_template(args.section))
        except QualificationEvidenceError as error:
            raise SystemExit(f"Qualification evidence error: {error}") from error
    if not args.path:
        raise SystemExit(f"qualification {args.action} requires an evidence path")
    try:
        if args.action == "export":
            if not getattr(args, "output", None):
                raise SystemExit("qualification export requires --output")
            return DispatchResult(
                export_qualification_bundle(
                    args.path, args.output, qualification_requirements()
                )
            )
        if args.action == "validate-bundle":
            return DispatchResult(
                validate_qualification_bundle(
                    args.path, qualification_requirements()
                )
            )
        return DispatchResult(
            validate_qualification_evidence(args.path, qualification_requirements())
        )
    except (OSError, QualificationEvidenceError) as error:
        raise SystemExit(f"Qualification evidence error: {error}") from error


def log_result(args, _os_info) -> DispatchResult:
    report = parse_operation_log(args.path, exit_code=args.exit_code)
    return DispatchResult({
        "exit_code": report.exit_code,
        "successful": report.successful,
        "verified_success": report.verified_success,
        "has_structured_evidence": report.has_structured_evidence,
        "reboot_required": report.reboot_required,
        "safe_next_action": report.safe_next_action,
        "events": [asdict(event) for event in report.events],
    })


def recovery_result(args, _os_info) -> DispatchResult:
    if args.action == "create":
        return DispatchResult(RecoveryRepository().create_recovery_snapshot(args.label))
    if args.action == "list":
        return DispatchResult(RecoveryRepository().recovery_inventory())
    if not args.snapshot:
        raise SystemExit(f"recovery {args.action} requires a snapshot path")
    if args.action == "export":
        if not getattr(args, "output", None):
            raise SystemExit("recovery export requires --output")
        return DispatchResult(
            RecoverySnapshotRepository.export_portable_bundle(
                args.snapshot, args.output
            )
        )
    if args.action == "verify":
        verified = RecoverySnapshotRepository.verify(args.snapshot)
        return DispatchResult(
            {"snapshot": args.snapshot, "verified": verified}, 0 if verified else 4
        )
    plan = RecoverySnapshotRepository.build_restore_plan(args.snapshot)
    current_state = RecoverySnapshotRepository.inspect_current_state(args.snapshot)
    return DispatchResult({
        "snapshot": plan.snapshot,
        "verified": plan.verified,
        "blocked": plan.blocked,
        "actions": [asdict(action) for action in plan.actions],
        "current_state": [asdict(item) for item in current_state],
    }, 0 if plan.verified else 4)


def profiles_result(args, _os_info) -> DispatchResult:
    bundles = ProfileBundleRepository(ConfiguracionLocal())
    try:
        if args.action == "export":
            return DispatchResult({"exported": str(bundles.export(args.path))})
        if args.action == "preview":
            return DispatchResult(asdict(bundles.preview(args.path)))
        if not args.yes:
            raise SystemExit(
                "Refusing profile import without --yes; run profiles preview first."
            )
        backup = bundles.import_bundle(args.path)
        return DispatchResult({"imported": args.path, "backup": str(backup)})
    except ProfileBundleError as error:
        raise SystemExit(f"Profile bundle error: {error}") from error


def metrics_result(args, _os_info) -> DispatchResult:
    configuration = ConfiguracionLocal()
    if args.action == "list":
        return DispatchResult({
            "metrics": configuration.leer_metricas_runtime(args.limit, args.since)
        })
    if not args.path:
        raise SystemExit("metrics export requires --path")
    destination = configuration.exportar_metricas_runtime(
        args.path, formato=args.format, limite=args.limit, desde=args.since
    )
    return DispatchResult({"exported": str(destination), "format": args.format})


SAFE_HANDLERS = MappingProxyType({
    "system": system_result,
    "telemetry": telemetry_result,
    "components": components_result,
    "integrations": integrations_result,
    "quick-access": quick_access_result,
    "release-gates": release_gates_result,
    "qualification": qualification_result,
    "parse-log": log_result,
    "recovery": recovery_result,
    "profiles": profiles_result,
    "metrics": metrics_result,
})


def dispatch_safe(args, os_info, *, host=None) -> DispatchResult | None:
    """Dispatch non-hardware commands, including explicit user-data writes."""
    if args.command == "integrations":
        return integrations_result(args, os_info, host)
    if args.command == "quick-access":
        return quick_access_result(args, os_info, host)
    handler = SAFE_HANDLERS.get(args.command)
    return handler(args, os_info) if handler else None
