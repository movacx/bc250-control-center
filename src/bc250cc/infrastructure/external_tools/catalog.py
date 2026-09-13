"""Executable integration manifest for reviewed third-party BC250 tools.

The manifest describes trust and lifecycle boundaries.  It never downloads,
executes or updates a tool; adapters provide read-only checkout evidence only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

_PAYLOAD_DISTRIBUTION_MODES = frozenset({
    "bundled-reviewed-snapshot",
    "runtime-fetch-reviewed-revision",
    "runtime-fetch-upstream-main",
    "reference-only",
})


@dataclass(frozen=True)
class ExternalToolSpec:
    key: str
    upstream: str
    license: str
    reviewed_revision: str
    privilege_class: str
    hardware_writes: bool
    automated: bool
    rollback: str
    validation_level: str
    update_strategy: str = "reviewed-revision"
    payload_distribution: str = "runtime-fetch-reviewed-revision"

    def validation_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        parsed = urlparse(self.upstream)
        if parsed.scheme != "https" or not parsed.netloc:
            issues.append("canonical HTTPS upstream is required")
        tracks_upstream = self.payload_distribution == "runtime-fetch-upstream-main"
        if self.automated and self.privilege_class != "userspace" and not tracks_upstream:
            revision = self.reviewed_revision.lower()
            if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
                issues.append("automated privileged integration requires an immutable 40-character revision")
        if tracks_upstream and self.update_strategy != "upstream-branch":
            issues.append("moving upstream payload requires the upstream-branch update strategy")
        if self.automated and self.privilege_class != "userspace":
            if not self.rollback.strip():
                issues.append("automated privileged integration requires rollback documentation")
        if not self.license.strip():
            issues.append("license review is missing")
        if self.payload_distribution not in _PAYLOAD_DISTRIBUTION_MODES:
            issues.append("payload distribution mode is invalid")
        if self.bundled_payload and not self.redistribution_ready:
            issues.append("bundled payload requires a declared upstream license")
        return tuple(issues)

    @property
    def adoption_ready(self) -> bool:
        return not self.validation_issues()

    @property
    def redistribution_ready(self) -> bool:
        normalized = self.license.strip().lower()
        return normalized not in {
            "", "unknown", "not-declared", "not-declared-upstream"
        }

    @property
    def release_gates(self) -> tuple[str, ...]:
        if self.redistribution_ready:
            return ()
        return (
            "upstream license is not declared; keep the integration runtime-fetch-only and do not bundle its payload",
        )

    @property
    def bundled_payload(self) -> bool:
        return self.payload_distribution.startswith("bundled-")

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["adoption_ready"] = self.adoption_ready
        result["redistribution_ready"] = self.redistribution_ready
        result["release_gates"] = list(self.release_gates)
        result["validation_issues"] = list(self.validation_issues())
        return result


class LifecycleAction(StrEnum):
    CHECK = "check"
    INSTALL = "install"
    APPLY = "apply"
    ROLLBACK = "rollback"
    UNINSTALL = "uninstall"


@dataclass(frozen=True)
class ExternalToolLifecycle:
    """Uniform lifecycle metadata without hiding tool-specific hardware logic."""

    install_contract: str
    health_contract: str
    uninstall_contract: str
    known_conflicts: tuple[str, ...]
    maintainer_note: str
    user_vocabulary: str
    deprecation_owner: str
    actions: frozenset[LifecycleAction]

    def validation_issues(self) -> tuple[str, ...]:
        fields = {
            "install contract": self.install_contract,
            "health contract": self.health_contract,
            "uninstall contract": self.uninstall_contract,
            "maintainer note": self.maintainer_note,
            "user vocabulary": self.user_vocabulary,
            "deprecation owner": self.deprecation_owner,
        }
        issues = [f"{name} is missing" for name, value in fields.items() if not value.strip()]
        if LifecycleAction.CHECK not in self.actions:
            issues.append("read-only check action is required")
        if LifecycleAction.ROLLBACK in self.actions and not self.uninstall_contract.strip():
            issues.append("rollback requires an uninstall/recovery contract")
        return tuple(issues)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["actions"] = sorted(action.value for action in self.actions)
        return result


EXTERNAL_TOOLS: dict[str, ExternalToolSpec] = {
    "cyan_smu": ExternalToolSpec(
        key="cyan_smu",
        upstream="https://github.com/filippor/cyan-skillfish-governor",
        license="MIT",
        reviewed_revision="964524d74ba6b69364be39f0e8fa484eb915779e",
        privilege_class="service-config",
        hardware_writes=True,
        automated=True,
        rollback="Disable/remove the managed service overlay and restore the previous TOML/range.",
        validation_level="code-reviewed-and-mocked",
    ),
    "cpu_smu_oc": ExternalToolSpec(
        key="cpu_smu_oc",
        upstream="https://github.com/bc250-collective/bc250_smu_oc",
        license="MIT",
        reviewed_revision="43d6b4c6e38c57bc9ec8908c44675ce7d5fd3d2f",
        privilege_class="live-hardware",
        hardware_writes=True,
        automated=True,
        rollback="Temporary settings end on reboot; persistent state has an explicit disable/restore action.",
        validation_level="code-reviewed-mocked-hardware-gate-pending",
        payload_distribution="bundled-reviewed-snapshot",
    ),
    "core_unlock": ExternalToolSpec(
        key="core_unlock",
        upstream="https://github.com/rw-r-r-0644/bc250-core-unlock",
        license="MIT",
        reviewed_revision="fb7e5bceab0e38369006cd1a0e53b768517f6030",
        privilege_class="live-hardware-reboot",
        hardware_writes=True,
        automated=True,
        rollback="Full power removal restores the factory core mask; physical recovery gate remains mandatory.",
        validation_level="code-reviewed-mocked-hardware-gate-pending",
    ),
    "cu_manager_standard": ExternalToolSpec(
        key="cu_manager_standard",
        upstream="https://github.com/WinnieLV/bc250-cu-live-manager",
        license="not-declared-upstream",
        reviewed_revision="a929085d791f126ce76a60eb609610820fb08066",
        privilege_class="live-hardware-service-reboot",
        hardware_writes=True,
        automated=True,
        rollback=(
            "Restore factory 24-CU routing and uninstall the persistence service; "
            "a cold power cycle restores the optional volatile CPU-core mask."
        ),
        validation_level="code-reviewed-mocked-hardware-gate-pending",
    ),
    "cu_manager_steamos": ExternalToolSpec(
        key="cu_manager_steamos",
        upstream="https://github.com/F5GO/bc250-cu-live-manager-SteamOS",
        license="not-declared-upstream",
        reviewed_revision="c4e91184e4cd194b9c7be0862b34e317faca6393",
        privilege_class="live-hardware-service",
        hardware_writes=True,
        automated=True,
        rollback="Restore the factory 24-CU route and uninstall the persistent service.",
        validation_level="code-reviewed-mocked-hardware-gate-pending",
    ),
    "steamos_amdgpu": ExternalToolSpec(
        key="steamos_amdgpu",
        upstream="https://github.com/keyboardspecialist/bc250-steamos",
        license="mixed-per-subproject",
        # v0.21.2. Earlier revisions had no patch variant for the Valve 7.2
        # kernel, so build.sh aborted on SteamOS 7.2 before this bump.
        reviewed_revision="1f4f3266d7f0e3dc0e8c760592bd63871d2c53c3",
        privilege_class="boot-kernel-initramfs",
        hardware_writes=False,
        automated=True,
        rollback="Upstream AMDGPU and RADV transactions provide independent uninstall/rollback paths; physical boot recovery is still required.",
        validation_level="code-reviewed-field-tested-single-host",
    ),
    # Per-user FSR4 runtime. Registered here so the shared manifest validator
    # and checkout inventory can see it; it was previously pinned only inside
    # bc250_fsr4.py and was therefore invisible to both.
    "fsr4_runtime": ExternalToolSpec(
        key="fsr4_runtime",
        upstream="https://github.com/dmorazasanchez/bc250-fsr4",
        # Upstream publishes no LICENSE file, so redistribution stays gated and
        # the integration remains runtime-fetch only.
        license="not-declared-upstream",
        reviewed_revision="6173651fa3a5a557cba2c2ff802e2d6f49881bc1",
        privilege_class="userspace",
        hardware_writes=False,
        automated=True,
        rollback="Remove the per-user prefix under ~/.local/share/bc250-fsr4 and drop the Steam launch option.",
        validation_level="code-reviewed-field-tested-single-host",
    ),
    "nct6687": ExternalToolSpec(
        key="nct6687",
        upstream="https://github.com/Fred78290/nct6687d",
        license="GPL-2.0",
        reviewed_revision="163ffdcc3928a2bb04acdf9607e45f98eeb46b8a",
        privilege_class="kernel-module-live-hardware",
        hardware_writes=True,
        automated=True,
        rollback="Unload nct6687, remove its persistence unit/module and restore the prior module preference.",
        validation_level="code-reviewed-field-tested-single-host",
    ),
    "oberon_governor": ExternalToolSpec(
        key="oberon_governor",
        upstream="https://gitlab.com/mothenjoyer69/oberon-governor",
        license="MIT",
        reviewed_revision="7e13da6c2cb9f1e0519242b1cb084ef767631a5c",
        privilege_class="service-config-live-hardware",
        hardware_writes=True,
        automated=True,
        rollback="Disable/remove the managed service and binary; preserve the existing YAML unless explicitly removed.",
        validation_level="code-reviewed-and-mocked",
    ),
    "gfx1013_direct": ExternalToolSpec(
        key="gfx1013_direct",
        upstream="https://github.com/DryhoppedIPA/bc250-gfx1013-fix",
        license="GPL/MIT components",
        reviewed_revision="5bb0dac39d094fe9cbd10d2b34868837125d9c39",
        privilege_class="boot-kernel-mesa",
        hardware_writes=False,
        automated=True,
        rollback="Use the official upstream uninstall action; the stock Fedora boot entry remains the recovery path.",
        validation_level="reviewed-upstream-commit-with-local-host-and-hardware-gates",
        update_strategy="reviewed-commit",
        payload_distribution="runtime-fetch-reviewed-revision",
    ),
    "gddr6_memory_temp": ExternalToolSpec(
        key="gddr6_memory_temp",
        upstream="https://github.com/pan-Rijovich/bc250-memory-temperature",
        license="MIT",
        reviewed_revision="b7e6bffcb5d592fc03edde375b7598ddc79aa846",
        privilege_class="live-hardware-firmware",
        hardware_writes=True,
        automated=True,
        rollback=(
            "The SMU patch lives in volatile SMU RAM only; a full power cycle "
            "restores the factory Queue 3 / Message 5 handler. No persistent "
            "or flash state is written."
        ),
        validation_level="reverse-engineered-community-reported-hardware-gate-pending",
    ),
}


def _lifecycle(
    install: str,
    health: str,
    uninstall: str,
    *,
    conflicts: tuple[str, ...] = (),
    vocabulary: str,
    actions: tuple[LifecycleAction, ...],
    maintainer: str = "BC250 Control Center maintainers review pinned upstream changes.",
) -> ExternalToolLifecycle:
    return ExternalToolLifecycle(
        install_contract=install,
        health_contract=health,
        uninstall_contract=uninstall,
        known_conflicts=conflicts,
        maintainer_note=maintainer,
        user_vocabulary=vocabulary,
        deprecation_owner="BC250 Control Center maintainers",
        actions=frozenset(actions),
    )


EXTERNAL_TOOL_LIFECYCLES: dict[str, ExternalToolLifecycle] = {
    "cyan_smu": _lifecycle(
        "Install the reviewed governor and managed service/config overlay.",
        "Verify binary revision, service state, D-Bus range and telemetry overlay.",
        "Disable the service, remove managed overlay and restore prior configuration.",
        conflicts=("oberon-governor.service",),
        vocabulary="GPU governor and frequency range",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "cpu_smu_oc": _lifecycle(
        "Prepare the pinned userspace detector; privileged execution stays in the packaged helper.",
        "Verify exact source revision, detector binding and boot/session identity.",
        "Disable persistent CPU tuning and remove only Control Center-owned state.",
        vocabulary="CPU frequency, scale and temperature limit",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "fsr4_runtime": _lifecycle(
        "Build or stage the pinned per-user FSR4 RADV runtime under the user prefix.",
        "Verify the checked-out revision and that the ICD manifest matches the reviewed build.",
        "Remove the per-user prefix and stop offering the Steam launch option.",
        vocabulary="per-game FSR4 RADV runtime",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.UNINSTALL),
    ),
    "core_unlock": _lifecycle(
        "Prepare the exact reviewed revision and SHA-256 payload for descriptor-bound execution.",
        "Verify origin, pinned revision, payload digest, helper ownership and CPU topology.",
        "Power removal restores factory cores; remove the prepared checkout only when idle.",
        conflicts=("cyan-skillfish-governor-smu.service", "oberon-governor.service"),
        vocabulary="Temporary CPU core unlock",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "cu_manager_standard": _lifecycle(
        "Stage the exact reviewed userspace manager; privileged actions remain locked in Control Center.",
        "Verify exact source revision; live status remains unavailable until a root-owned backend exists.",
        "Restore factory routing before removing boot persistence; cold power restores its optional CPU-core mask.",
        conflicts=("unreviewed CU persistence services", "independent CPU core-unlock workflows"),
        vocabulary="GPU compute units; upstream also contains an independent volatile CPU core unlock",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "cu_manager_steamos": _lifecycle(
        "Prepare the pinned SteamOS CU backend and reconciled UMR database.",
        "Verify UMR selector, live CU routing, saved target and service synchronization.",
        "Restore factory 24-CU routing before removing the persistence service.",
        vocabulary="GPU compute units and factory restore",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "steamos_amdgpu": _lifecycle(
        "Build the pinned kernel-matched override first, then the matched Mesa/RADV runtime in an explicit second stage.",
        "Verify AMDGPU capabilities, scheduler policy, RADV ownership and optional per-game FSR4 independently.",
        "Use the pinned AMDGPU rollback and RADV/FSR4 uninstall paths after recovery-path validation.",
        conflicts=("unreviewed amdgpu overrides",),
        vocabulary="SteamOS AMDGPU, telemetry, async-compute RADV and optional FSR4 compatibility",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "nct6687": _lifecycle(
        "Build and install the reviewed driver for the exact running kernel.",
        "Verify module vermagic, loaded driver, NCT hwmon and writable PWM capability.",
        "Restore module preference, unload/remove the module and disable its loader service.",
        conflicts=("nct6683",),
        vocabulary="Fan sensor and PWM driver",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "oberon_governor": _lifecycle(
        "Build the exact reviewed source and exact yaml-cpp dependency, then install the managed service.",
        "Verify binary, YAML endpoints, service ownership/state and conflicts.",
        "Disable/remove the service and managed binary while preserving user YAML by default.",
        conflicts=("cyan-skillfish-governor-smu.service",),
        vocabulary="Alternative GPU governor and two operating points",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
    ),
    "gfx1013_direct": _lifecycle(
        "Update the official main branch and run its combined kernel + Mesa/RADV installer after explicit confirmation.",
        "Report kernel and Mesa/RADV halves independently; reject Atomic/Bazzite and defer Fedora/kernel compatibility checks to upstream.",
        "Run the official upstream uninstall action and retain the stock Fedora boot entry as the recovery default.",
        conflicts=("legacy mesh/task RADV patch",),
        vocabulary="GFX1013 async-compute compatibility",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.ROLLBACK, LifecycleAction.UNINSTALL),
        maintainer="DryhoppedIPA maintains the installer and patch series; Control Center only maintains safety gates and invocation.",
    ),
    "gddr6_memory_temp": _lifecycle(
        "Prepare the pinned upstream checkout (SMU payload + read/patch scripts); privileged execution stays in the packaged helper.",
        "Verify exact source revision and read the last per-chip average/hotspot sample, best-effort and read-only.",
        "Power-cycle the board to discard the runtime SMU patch; Control Center holds no persistent state for this integration.",
        vocabulary="GDDR6 per-chip memory temperature (average and hotspot)",
        actions=(LifecycleAction.CHECK, LifecycleAction.INSTALL, LifecycleAction.APPLY, LifecycleAction.UNINSTALL),
        maintainer=(
            "pan-Rijovich (bc250-collective) maintains the SMU/UMC reverse "
            "engineering; Control Center only maintains safety gates and "
            "invocation. Author's own note: the implementation is reverse-"
            "engineered and not fully verified — incorrect SMU/UMC state, DQ "
            "mapping, timing or firmware addresses could interfere with "
            "normal GDDR6 traffic and cause memory corruption, instability or "
            "crashes. Use at your own risk."
        ),
    ),
}


@dataclass(frozen=True)
class CheckoutEvidence:
    tool: str
    path: str
    present: bool
    git_checkout: bool
    origin_matches: bool
    revision_matches: bool
    dirty: bool | None

    @property
    def verified(self) -> bool:
        return all((self.present, self.git_checkout, self.origin_matches, self.revision_matches)) and self.dirty is False


@dataclass(frozen=True)
class LifecycleReport:
    tool: str
    checkout: CheckoutEvidence
    health: Mapping[str, object]
    health_error: str = ""

    @property
    def healthy(self) -> bool:
        return self.checkout.verified and not self.health_error and bool(self.health.get("healthy"))


@dataclass(frozen=True)
class LifecyclePlan:
    tool: str
    action: LifecycleAction
    available: bool
    reasons: tuple[str, ...]
    privilege_class: str
    hardware_writes: bool
    requires_confirmation: bool


ReadOnlyProbe = Callable[[], Mapping[str, object]]


class GitCheckoutReader:
    """Small fail-closed adapter around a repository subprocess runner."""

    def __init__(self, runner):
        self.runner = runner
        self._cache: dict[tuple[str, tuple[str, ...]], tuple[int, str]] = {}

    def _run(self, path: Path, *arguments: str) -> tuple[int, str]:
        cache_key = (str(path), tuple(arguments))
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            result = self.runner(
                ["git", "-C", str(path), *arguments], timeout=2
            )
            code, output = int(result[0]), str(result[1] or "")
            result = (code, output.strip())
        except (OSError, RuntimeError, TypeError, ValueError, IndexError):
            result = (1, "")
        self._cache[cache_key] = result
        return result

    def origin(self, path: Path) -> str:
        code, output = self._run(path, "remote", "get-url", "origin")
        return output if code == 0 else ""

    def revision(self, path: Path) -> str:
        code, output = self._run(path, "rev-parse", "--verify", "HEAD")
        return output.splitlines()[0] if code == 0 and output else ""

    def dirty(self, path: Path) -> bool | None:
        code, output = self._run(
            path, "status", "--porcelain", "--untracked-files=all"
        )
        return bool(output) if code == 0 else None

    def status_details(self, path: Path) -> dict[str, object]:
        code, output = self._run(
            path, "status", "--porcelain", "--untracked-files=all"
        )
        if code != 0:
            return {
                "available": False,
                "tracked_dirty": None,
                "untracked_count": None,
            }
        lines = [line for line in output.splitlines() if line]
        untracked = sum(line.startswith("??") for line in lines)
        return {
            "available": True,
            "tracked_dirty": any(not line.startswith("??") for line in lines),
            "untracked_count": untracked,
        }


EXTERNAL_TOOL_DIRECTORIES = {
    "cyan_smu": "cyan-skillfish-governor-smu",
    "cpu_smu_oc": "bc250_smu_oc",
    "core_unlock": "bc250-core-unlock",
    "cu_manager_standard": "bc250-cu-live-manager",
    "cu_manager_steamos": "bc250-cu-live-manager-steamos",
    "steamos_amdgpu": "bc250-steamos",
    "nct6687": "nct6687d",
    "fsr4_runtime": "bc250-fsr4",
    "oberon_governor": "oberon-governor",
    "gfx1013_direct": "bc250-gfx1013-fix",
    "gddr6_memory_temp": "bc250-memory-temperature",
}


class ExternalToolAdapter:
    """Read-only lifecycle adapter; mutation remains in typed tool-specific helpers."""

    def __init__(
        self,
        spec: ExternalToolSpec,
        destination: str | Path,
        git_reader,
        *,
        lifecycle: ExternalToolLifecycle | None = None,
        read_only_probe: ReadOnlyProbe | None = None,
    ):
        self.spec = spec
        self.destination = Path(destination)
        self.git_reader = git_reader
        self.lifecycle = lifecycle or EXTERNAL_TOOL_LIFECYCLES[spec.key]
        self.read_only_probe = read_only_probe

    def inspect(self) -> CheckoutEvidence:
        present = self.destination.is_dir()
        git_checkout = (self.destination / ".git").is_dir() if present else False
        origin = self.git_reader.origin(self.destination) if git_checkout else ""
        revision = self.git_reader.revision(self.destination) if git_checkout else ""
        dirty = self.git_reader.dirty(self.destination) if git_checkout else None
        revision_matches = (
            len(revision) == 40
            and all(char in "0123456789abcdef" for char in revision.lower())
            if self.spec.payload_distribution == "runtime-fetch-upstream-main"
            else revision == self.spec.reviewed_revision
        )
        return CheckoutEvidence(
            tool=self.spec.key,
            path=str(self.destination),
            present=present,
            git_checkout=git_checkout,
            origin_matches=origin.rstrip("/") == self.spec.upstream.rstrip("/"),
            revision_matches=revision_matches,
            dirty=dirty,
        )

    def report(self) -> LifecycleReport:
        evidence = self.inspect()
        if self.read_only_probe is None:
            return LifecycleReport(self.spec.key, evidence, {})
        try:
            health = dict(self.read_only_probe() or {})
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return LifecycleReport(
                self.spec.key,
                evidence,
                {},
                str(error) or error.__class__.__name__,
            )
        return LifecycleReport(self.spec.key, evidence, health)

    def plan(self, action: LifecycleAction | str) -> LifecyclePlan:
        requested = LifecycleAction(action)
        reasons: list[str] = []
        if requested not in self.lifecycle.actions:
            reasons.append(f"{requested.value} is not exposed by this integration")
        reasons.extend(self.spec.validation_issues())
        if requested is LifecycleAction.APPLY and not self.inspect().verified:
            reasons.append("an exact clean reviewed checkout is required before apply")
        high_risk = self.spec.privilege_class != "userspace" or self.spec.hardware_writes
        return LifecyclePlan(
            tool=self.spec.key,
            action=requested,
            available=not reasons,
            reasons=tuple(reasons),
            privilege_class=self.spec.privilege_class,
            hardware_writes=self.spec.hardware_writes,
            requires_confirmation=high_risk and requested is not LifecycleAction.CHECK,
        )


def build_external_checkout_inventory(
    tool_dir: str | Path,
    git_reader: GitCheckoutReader,
) -> dict[str, dict[str, object]]:
    """Build read-only checkout/lifecycle evidence shared by GUI and CLI."""
    base = Path(tool_dir)
    inventory: dict[str, dict[str, object]] = {}
    for key, spec in EXTERNAL_TOOLS.items():
        destination = base / EXTERNAL_TOOL_DIRECTORIES[key]
        evidence = ExternalToolAdapter(
            spec,
            destination,
            git_reader,
            lifecycle=EXTERNAL_TOOL_LIFECYCLES[key],
        ).inspect()
        status = (
            git_reader.status_details(destination)
            if evidence.git_checkout
            else {
                "available": False,
                "tracked_dirty": None,
                "untracked_count": None,
            }
        )
        source_verified = bool(
            evidence.present
            and evidence.git_checkout
            and evidence.origin_matches
            and evidence.revision_matches
            and status["tracked_dirty"] is False
        )
        inventory[key] = {
            "path": evidence.path,
            "present": evidence.present,
            "git_checkout": evidence.git_checkout,
            "origin_matches": evidence.origin_matches,
            "revision_matches": evidence.revision_matches,
            "dirty": evidence.dirty,
            "verified": evidence.verified,
            # This diagnostic ignores untracked build/runtime artifacts. Never
            # use it instead of exact-clean ``verified`` for authorization.
            "source_verified": source_verified,
            "tracked_dirty": status["tracked_dirty"],
            "untracked_count": status["untracked_count"],
            "validation_level": spec.validation_level,
            "redistribution_ready": spec.redistribution_ready,
            "release_gates": list(spec.release_gates),
            "actions": sorted(
                action.value for action in EXTERNAL_TOOL_LIFECYCLES[key].actions
            ),
        }
    return inventory


def validate_external_tool_manifest() -> dict[str, tuple[str, ...]]:
    results: dict[str, tuple[str, ...]] = {}
    for key, spec in EXTERNAL_TOOLS.items():
        issues = list(spec.validation_issues())
        lifecycle = EXTERNAL_TOOL_LIFECYCLES.get(key)
        if lifecycle is None:
            issues.append("lifecycle contract is missing")
        else:
            issues.extend(lifecycle.validation_issues())
        if issues:
            results[key] = tuple(issues)
    for key in EXTERNAL_TOOL_LIFECYCLES.keys() - EXTERNAL_TOOLS.keys():
        results[key] = ("lifecycle has no matching tool specification",)
    return results
