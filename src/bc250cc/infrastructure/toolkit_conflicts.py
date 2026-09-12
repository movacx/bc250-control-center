"""Detect community toolkits that manage the same BC-250 state as this app.

Governor conflicts are already handled in ``governor_conflicts``: that module
answers "is a second GPU governor running". This one answers a broader
question — "did another toolkit already configure the same files and services
Control Center owns" — because several community toolkits install the very
same units and configuration paths.

Detection is passive: it reads paths and asks the init system about units. It
never stops, disables or removes anything, and a detected toolkit is reported,
not treated as an error. Users are entitled to run other tools; they just need
to know when two of them own the same file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Paths and units Control Center writes. A foreign toolkit that owns any of
# these will silently fight with it after the next boot.
SHARED_CONFIGURATION = (
    "/etc/cyan-skillfish-governor-smu/config.toml",
    "/etc/bc250-smu-oc.conf",
    "/etc/bc250-cu-live-manager.conf",
    "/etc/modules-load.d/nct6687.conf",
)

SHARED_UNITS = (
    "cyan-skillfish-governor-smu.service",
    "bc250-smu-oc.service",
    "bc250-cu-live-manager.service",
)


@dataclass(frozen=True)
class ToolkitSpec:
    """A community toolkit that configures BC-250 hardware."""

    identifier: str
    display_name: str
    upstream: str
    # Files only this toolkit creates. Presence is the evidence; shared paths
    # above are deliberately excluded because Control Center writes them too.
    markers: tuple[str, ...] = ()
    # What it takes over, for the message shown to the user.
    overlapping_areas: tuple[str, ...] = ()


KNOWN_TOOLKITS: tuple[ToolkitSpec, ...] = (
    ToolkitSpec(
        identifier="bc250-toolkit",
        display_name="BC250 Toolkit",
        upstream="https://github.com/redbeard1083/bc250-toolkit",
        markers=(
            "/etc/systemd/system/bc250-cu-failure-capture.service",
            "/etc/udev/rules.d/99-bc250-cu-live-manager.rules",
            "/etc/udev/rules.d/91-ac3-audio.rules",
            "/etc/dracut.conf.d/bc250-modules.conf",
            "/etc/plasmalogin.conf.d/zzz-bc250-boot.conf",
        ),
        overlapping_areas=("GPU governor", "CPU tuning", "Compute Units", "Fans"),
    ),
    ToolkitSpec(
        identifier="bc250-steamos-toolkit",
        display_name="BC250 SteamOS Toolkit",
        upstream="https://github.com/keyboardspecialist/bc250-steamos",
        markers=("/usr/local/bin/bc250-toolkit",),
        overlapping_areas=("GPU governor", "Compute Units"),
    ),
    ToolkitSpec(
        identifier="bc250-steamos-real-toolkit",
        display_name="BC250 SteamOS Real Toolkit",
        upstream="https://github.com/rpf16rj/bc250-steamos-real-toolkit",
        # Taken from the upstream installer: these units and paths are unique
        # to it, while bc250-smu-oc/cu-live-manager are shared with this app.
        markers=(
            "/etc/systemd/system/bc250-toolkit-persist.service",
            "/etc/systemd/system/bc250-acpi-heal.service",
            "/etc/systemd/system/bc250-cpufreq.service",
            "/etc/systemd/system/bc250-eac3-backend.service",
            "/etc/bc250-control",
            "/etc/alsa/conf.d/61-bc250-a52.conf",
            "/etc/atomic-update.conf.d/bc250-toolkit.conf",
        ),
        overlapping_areas=(
            "GPU governor", "CPU tuning", "Compute Units", "Audio", "ACPI",
        ),
    ),
    ToolkitSpec(
        identifier="bc250-batocera-tools",
        display_name="BC250 Batocera Tools",
        upstream="https://github.com/tmghd272/bc250-batocera-tools",
        # Batocera keeps its state under /userdata because the root is
        # read-only; those paths exist on no other supported distribution.
        markers=(
            "/userdata/system/bc250-8core",
            "/userdata/system/bc250-cu-manager",
        ),
        overlapping_areas=("CPU tuning", "Compute Units", "GPU governor"),
    ),
)


@dataclass(frozen=True)
class ToolkitDetection:
    identifier: str
    display_name: str
    upstream: str
    evidence: tuple[str, ...] = ()
    overlapping_areas: tuple[str, ...] = ()
    shared_paths: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "display_name": self.display_name,
            "upstream": self.upstream,
            "evidence": list(self.evidence),
            "overlapping_areas": list(self.overlapping_areas),
            "shared_paths": list(self.shared_paths),
        }


def _existing(paths, root: Path) -> tuple[str, ...]:
    found = []
    for raw in paths:
        candidate = root / str(raw).lstrip("/")
        try:
            if candidate.exists() or candidate.is_symlink():
                found.append(str(raw))
        except OSError:
            # An unreadable path is not evidence either way.
            continue
    return tuple(found)


def detect_foreign_toolkits(*, root: Path | str = "/") -> tuple[dict[str, object], ...]:
    """Return evidence for every known toolkit present on this system.

    Passive and side-effect free, so it is safe to call during a status refresh.
    """
    base = Path(root)
    detections = []
    for spec in KNOWN_TOOLKITS:
        evidence = _existing(spec.markers, base)
        if not evidence:
            continue
        detections.append(
            ToolkitDetection(
                identifier=spec.identifier,
                display_name=spec.display_name,
                upstream=spec.upstream,
                evidence=evidence,
                overlapping_areas=spec.overlapping_areas,
                shared_paths=_existing(SHARED_CONFIGURATION, base),
            ).to_dict()
        )
    return tuple(detections)


def describe_toolkit_conflict(detections) -> str:
    """One bounded sentence naming what else manages this hardware."""
    names = ", ".join(str(item.get("display_name") or item.get("identifier")) for item in detections)
    if not names:
        return ""
    return (
        f"Another BC-250 toolkit is installed: {names}. "
        "Both it and Control Center manage the same services and configuration files, "
        "so a change applied here can be replaced at the next boot. "
        "Keep only one of them responsible for each area."
    )
