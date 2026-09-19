"""Pure preflight for installing an exact CPU boot-persistence candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PersistenceBlocker:
    title: str
    message: str
    tone: str


@dataclass(frozen=True)
class PlanText:
    template: str
    values: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class CpuPersistencePlan:
    scale_override: int | None
    confirm_scale_jump: bool
    command_frequency: int | None
    command_temperature: int | None
    detection_source: PlanText
    detected_result: str
    boot_candidate: str
    validation_source: PlanText
    scale_summary: PlanText
    #: What the processor is running right now, when it is known and is not
    #: what would be installed. Empty otherwise.
    active_scale: str = ""
    live_notice: PlanText | None = None


def _text(template: str, **values: object) -> PlanText:
    return PlanText(template, tuple(values.items()))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def validate_detection_for_persistence(
    detection: Mapping[str, object],
) -> PersistenceBlocker | None:
    snapshot = _mapping(detection.get("snapshot"))
    current_config = _mapping(detection.get("current_config"))
    if not snapshot and not current_config.get("valid"):
        return PersistenceBlocker(
            "Run CPU detection first",
            "No validated overclock.conf is available to install. Run the temporary CPU detection from this page; Control Center will write and bind the result to the correct user-owned path automatically.",
            "orange",
        )
    if detection.get("recorded") and detection.get("legacy_override_in_detector_config"):
        return PersistenceBlocker(
            "Run bc250-detect once with this version",
            "This detection was created by an older Control Center build that edited overclock.conf in place after a scale override. "
            "The new workflow keeps detector evidence immutable, so run bc250-detect once more before testing a manual scale or enabling boot persistence.",
            "orange",
        )
    if detection.get("recorded") and not detection.get("matches_current_config"):
        return PersistenceBlocker(
            "CPU detection result changed",
            "The current overclock.conf no longer matches the last completed bc250-detect run. "
            "Run the temporary CPU detection again before enabling persistence.",
            "red",
        )
    return None


def plan_cpu_persistence(
    detection: Mapping[str, object],
    *,
    scale_override: int | None,
    candidate_frequency: int,
    candidate_temperature: int,
    scale_analysis: Mapping[str, object] | None = None,
    live_state: Mapping[str, object] | None = None,
) -> CpuPersistencePlan | PersistenceBlocker:
    blocker = validate_detection_for_persistence(detection)
    if blocker is not None:
        return blocker
    detection_run = _mapping(detection.get("snapshot"))
    current_config = _mapping(detection.get("current_config"))
    analysis = scale_analysis or {}
    live = live_state or {}
    live_test = _mapping(live.get("test"))
    if scale_override is not None and not live.get("valid_for_persistence"):
        return PersistenceBlocker(
            "Apply this scale temporarily first",
            "Boot persistence will not use a manual scale that has not first been applied live against the current bc250-detect run. "
            "Use the main temporary apply button, test the machine under your real workload, then return here if it remains stable.",
            "orange",
        )

    run_frequency = detection_run.get("frequency", current_config.get("frequency", "--"))
    run_scale = detection_run.get("scale", current_config.get("scale", "--"))
    run_temperature = detection_run.get(
        "temperature", current_config.get("max_temperature", "--")
    )
    if detection_run:
        detection_source = _text(
            "Recorded bc250-detect run {run_id}",
            run_id=detection_run.get("run_id", "--"),
        )
    else:
        detection_source = _text("Current external overclock.conf (not recorded by this app)")

    if scale_override is not None:
        exact_scale: object = scale_override
        boot_frequency: object = int(candidate_frequency)
        boot_temperature: object = int(candidate_temperature)
        validation_source = _text(
            "Live test {test_id}", test_id=live_test.get("test_id", "--")
        )
        scale_summary = _text(
            "Live-tested override: {scale} (estimated VID ~{vid} mV)",
            scale=scale_override,
            vid=analysis.get("requested_estimated_vid", "--"),
        )
        command_frequency = int(candidate_frequency)
        command_temperature = int(candidate_temperature)
    else:
        exact_scale = run_scale
        boot_frequency = run_frequency
        boot_temperature = run_temperature
        validation_source = _text(
            "bc250-detect stress result"
            if detection_run
            else "External config — stress run not recorded by Control Center"
        )
        scale_summary = _text("Detected scale {scale}", scale=run_scale)
        command_frequency = None
        command_temperature = None

    # A manual scale can be live and still be ineligible for boot: the rule is
    # that only a value tested against the current detector run may be
    # installed. Saying nothing in that case left the dialog promising the
    # detected scale while the processor was running another one.
    active_scale = ""
    live_notice = None
    if scale_override is None and live.get("active_in_current_session"):
        live_scale = live_test.get("scale")
        if live_scale is not None and str(live_scale) != str(exact_scale):
            active_scale = f"{live_scale}"
            live_notice = _text(
                "Keep testing this temporary manual OC. Run automatic "
                "detection before saving any CPU configuration for boot."
            )

    return CpuPersistencePlan(
        scale_override=scale_override,
        confirm_scale_jump=bool(analysis.get("requires_extra_confirmation")),
        command_frequency=command_frequency,
        command_temperature=command_temperature,
        detection_source=detection_source,
        detected_result=f"{run_frequency} MHz | scale {run_scale} | {run_temperature} °C",
        boot_candidate=f"{boot_frequency} MHz | scale {exact_scale} | {boot_temperature} °C",
        validation_source=validation_source,
        scale_summary=scale_summary,
        active_scale=active_scale,
        live_notice=live_notice,
    )
