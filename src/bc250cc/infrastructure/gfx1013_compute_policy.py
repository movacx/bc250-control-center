from __future__ import annotations

from dataclasses import asdict, dataclass

from .external_tools.catalog import EXTERNAL_TOOLS

GFX1013_UPSTREAM = EXTERNAL_TOOLS["gfx1013_direct"].upstream
GFX1013_REVIEWED_COMMIT = EXTERNAL_TOOLS["gfx1013_direct"].reviewed_revision
GFX1013_REVIEWED_VERSION = "0.2.0-alpha"
GFX1013_TESTED_DISTRO_ID = "fedora"
GFX1013_TESTED_VERSION_ID = "43"
GFX1013_TESTED_KERNEL = "7.1.5-101.fc43.x86_64"
STEAMOS_GFX1013_BACKEND = EXTERNAL_TOOLS["steamos_amdgpu"].upstream
STEAMOS_REVIEWED_DRYHOPPED_COMMIT = "d3e6dc062c34d2523db0abe5741d1f5b0dea00d9"
STEAMOS_GFX1013_SAFE_RADV_REFERENCE = "https://github.com/rpf16rj/bc250-steamos-real-toolkit"
STEAMOS_GFX1013_SAFE_RADV_REVIEWED_COMMIT = "681b8703588b61bb82893a9359bdab841e618010"
STEAMOS_GFX1013_SAFE_RADV_VERSION = "1.1.0"


@dataclass(frozen=True)
class Gfx1013Compatibility:
    mode: str
    status: str
    direct_installer_allowed: bool
    automatic_install_allowed: bool
    exact_upstream_validated_host: bool
    reason_key: str
    upstream: str = GFX1013_UPSTREAM
    reviewed_commit: str = GFX1013_REVIEWED_COMMIT
    reviewed_version: str = GFX1013_REVIEWED_VERSION
    tested_kernel: str = GFX1013_TESTED_KERNEL
    steamos_backend: str = STEAMOS_GFX1013_BACKEND

    def to_dict(self) -> dict:
        return asdict(self)


def classify_gfx1013_support(
    *,
    family: str,
    distro_id: str = "",
    version_id: str = "",
    kernel: str = "",
    immutable: bool = False,
) -> dict:
    """Return the conservative Control Center support policy for GFX1013.

    This deliberately separates *upstream can be applied manually* from
    *Control Center is allowed to automate it*.  The latter remains false:
    the project is an alpha boot/kernel/initramfs/Mesa integration and our
    hardware release gate requires dedicated physical rollback validation
    before automation can be enabled.
    """

    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    version_id = str(version_id or "").strip()
    kernel = str(kernel or "").strip()

    if family == "steamos":
        return Gfx1013Compatibility(
            mode="steamos-backend",
            status="managed-separately",
            direct_installer_allowed=False,
            automatic_install_allowed=False,
            exact_upstream_validated_host=False,
            reason_key="steamos-dedicated-backend",
        ).to_dict()

    if family == "bazzite" or immutable:
        return Gfx1013Compatibility(
            mode="blocked-immutable",
            status="blocked",
            direct_installer_allowed=False,
            automatic_install_allowed=False,
            exact_upstream_validated_host=False,
            reason_key="bazzite-not-supported-upstream",
        ).to_dict()

    if family == "fedora" and distro_id == GFX1013_TESTED_DISTRO_ID:
        exact = (
            version_id == GFX1013_TESTED_VERSION_ID
            and kernel == GFX1013_TESTED_KERNEL
        )
        return Gfx1013Compatibility(
            mode="fedora-upstream",
            status="upstream-validated" if exact else "outside-validated-host",
            direct_installer_allowed=exact,
            automatic_install_allowed=False,
            exact_upstream_validated_host=exact,
            reason_key=(
                "fedora-exact-upstream-host"
                if exact
                else "fedora-outside-upstream-validation"
            ),
        ).to_dict()

    if family in {"arch", "manjaro", "cachyos"}:
        return Gfx1013Compatibility(
            mode="manual-experimental",
            status="manual-untested",
            direct_installer_allowed=False,
            automatic_install_allowed=False,
            exact_upstream_validated_host=False,
            reason_key="arch-family-manual-untested",
        ).to_dict()

    return Gfx1013Compatibility(
        mode="manual-only",
        status="not-integrated",
        direct_installer_allowed=False,
        automatic_install_allowed=False,
        exact_upstream_validated_host=False,
        reason_key="manual-patches-only",
    ).to_dict()
