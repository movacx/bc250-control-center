#!/usr/bin/env python3
"""Stage the BC250-owned high-OC telemetry overlay into a reviewed toolkit.

This changes only the protected, root-owned staged toolkit supplied by the
explicit AMDGPU compatibility workflow.  It never invokes sudo itself, builds
a module, edits /boot, or writes hardware registers.  The generated build fragment changes the *read-only*
GFX-clock telemetry validation range from the stock 1000–2000 MHz to the
reviewed BC250 range of 500–2400 MHz.  It deliberately does not change the
kernel's frequency-control ceiling.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

OVERLAY_MARKER = "# BC250_CONTROL_CENTER_OC_TELEMETRY_OVERLAY_V1"
TELEMETRY_OC_MIN_MHZ = 500
TELEMETRY_OC_MAX_MHZ = 2400
BUILD_RELATIVE_PATH = Path("bc250-audio-fix/build.sh")
UPSTREAM_GFXCLK_SHA = "572014e03cff22fb57f21121e8e8722f11d3d99822ee86e60fbfe50ed6e76f30"
LEGACY_OVERLAY_RESULT_SHA = "083f4da83fb349c8eb5a739b0e64add653c63a7057f20b536c5b41f4a1265ad3"
OVERLAY_RESULT_SHA = "a50ff2e02a6bcf38e12d947eb8d76db3cfdc9322a4579e32b5fdbe5f627c8b98"
# Valve's 24.5 integration commit changed the otherwise supported 6.16 source
# composition.  The upstream patches still apply cleanly, but the toolkit's
# older 6.16 final hash rejects it.  Accept only this exact kernel commit and
# both independently measured post-patch hashes; every other 6.16 tree keeps
# the original fail-closed composition guard.
STEAMOS_24_5_KERNEL_COMMIT = "b2f7cfe85e45b7e1ddb04ca8b280aca19add1100"
STEAMOS_24_5_SCLK_SOURCE_SHA = "16578119d29855f47bec42b772d2ad03b8f3d690aa3df1106ad1411a04ca7d94"
STEAMOS_24_5_OVERLAY_RESULT_SHA = "32b553a07f073881521c508ad9f40f7b86a91d7f8cbea032b084b3c998a62f19"
LEGACY_616_SCLK_SOURCE_SHA = "fdb9c3fff8a9ff813cdc37907dace041f89f6db15158c56a4bd8f238352b6e42"
ANCHOR = 'step "apply GFX1013 compute-queue lifecycle patches"'
SCLK_HASH_ASSIGNMENT = f"        SCLK_SOURCE_SHA={LEGACY_616_SCLK_SOURCE_SHA}"


def _regular_file(path: Path) -> None:
    info = path.stat(follow_symlinks=False)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Refusing non-regular overlay target: {path}")
    if info.st_mode & 0o022:
        raise RuntimeError(f"Refusing group/other-writable overlay target: {path}")


def _fragment() -> str:
    return f'''{OVERLAY_MARKER}
# The upstream query patch intentionally validates 1000-2000 MHz.  That
# rejects gpu_metrics at a valid 500 MHz idle point or an explicitly selected
# 2050-2400 MHz BC250 safe-point, making MangoHud report 0% and hiding the
# live clock. This range exactly matches Control Center's reviewed points.
# This is telemetry-only: Cyan remains the sole frequency controller.
if [ "${{BC250_CONTROL_CENTER_OC_TELEMETRY:-0}}" = "1" ]; then
    BC250_TELEMETRY_SOURCE="$METRICS_SOURCE"
    grep -Fq '*value < CYAN_SKILLFISH_SCLK_MIN' "$BC250_TELEMETRY_SOURCE" || \\
        die "BC250 telemetry OC overlay expected the reviewed GFX clock floor"
    grep -Fq '*value > CYAN_SKILLFISH_SCLK_MAX' "$BC250_TELEMETRY_SOURCE" || \\
        die "BC250 telemetry OC overlay expected the reviewed GFX clock guard"
    grep -Fq 'static int cyan_skillfish_get_gfxclk_frequency' "$BC250_TELEMETRY_SOURCE" || \\
        die "BC250 telemetry OC overlay expected the reviewed GFX clock query"
    sed -i 's/\\*value < CYAN_SKILLFISH_SCLK_MIN/\\*value < BC250_TELEMETRY_GFXCLK_MIN/; s/\\*value > CYAN_SKILLFISH_SCLK_MAX/\\*value > BC250_TELEMETRY_GFXCLK_MAX/' "$BC250_TELEMETRY_SOURCE"
    sed -i '/^static int cyan_skillfish_get_gfxclk_frequency/i#define BC250_TELEMETRY_GFXCLK_MIN\\t\\t\\t{TELEMETRY_OC_MIN_MHZ}\\n#define BC250_TELEMETRY_GFXCLK_MAX\\t\\t\\t{TELEMETRY_OC_MAX_MHZ}\\n' "$BC250_TELEMETRY_SOURCE"
    BC250_TELEMETRY_SHA="$(sha256sum "$BC250_TELEMETRY_SOURCE" | cut -d' ' -f1)"
    case "$FULLSHA" in
        {STEAMOS_24_5_KERNEL_COMMIT}) BC250_TELEMETRY_EXPECTED_SHA={STEAMOS_24_5_OVERLAY_RESULT_SHA} ;;
        *) BC250_TELEMETRY_EXPECTED_SHA={OVERLAY_RESULT_SHA} ;;
    esac
    [ "$BC250_TELEMETRY_SHA" = "$BC250_TELEMETRY_EXPECTED_SHA" ] || \\
        die "BC250 telemetry OC overlay produced an unexpected kernel source"
    echo "BC250 Control Center: enabled read-only GFX telemetry for {TELEMETRY_OC_MIN_MHZ}-{TELEMETRY_OC_MAX_MHZ} MHz"
fi

'''


def apply_overlay(toolkit_root: Path) -> bool:
    root = Path(toolkit_root).resolve(strict=True)
    build = root / BUILD_RELATIVE_PATH
    _regular_file(build)
    text = build.read_text(encoding="utf-8", errors="strict")
    steamos_24_5_hash_block = f'''        if [ "$FULLSHA" = "{STEAMOS_24_5_KERNEL_COMMIT}" ]; then
            SCLK_SOURCE_SHA={STEAMOS_24_5_SCLK_SOURCE_SHA}
        else
            SCLK_SOURCE_SHA={LEGACY_616_SCLK_SOURCE_SHA}
        fi'''
    if steamos_24_5_hash_block not in text:
        if text.count(SCLK_HASH_ASSIGNMENT) != 1:
            raise RuntimeError(
                "The reviewed SteamOS SCLK composition guard has drifted."
            )
        text = text.replace(SCLK_HASH_ASSIGNMENT, steamos_24_5_hash_block, 1)
    if OVERLAY_MARKER in text:
        if (
            OVERLAY_RESULT_SHA in text
            and STEAMOS_24_5_OVERLAY_RESULT_SHA in text
        ):
            return False
        # R181 initially covered only the high end. Upgrade that exact,
        # attested fragment in place, while refusing any unknown local edit.
        if LEGACY_OVERLAY_RESULT_SHA not in text or text.count(ANCHOR) != 1:
            raise RuntimeError("Existing telemetry OC overlay has an unexpected integrity hash.")
        start = text.index(OVERLAY_MARKER)
        end = text.index(ANCHOR)
        updated = text[:start] + _fragment() + text[end:]
    else:
        if text.count(ANCHOR) != 1 or UPSTREAM_GFXCLK_SHA not in text:
            raise RuntimeError(
                "The reviewed SteamOS build script has drifted; telemetry OC overlay was not staged."
            )
        updated = text.replace(ANCHOR, _fragment() + ANCHOR, 1)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{build.name}.", suffix=".tmp", dir=str(build.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, build.stat(follow_symlinks=False).st_mode & 0o777)
        os.replace(temporary, build)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <bc250-steamos-toolkit-root>", file=sys.stderr)
        return 2
    try:
        changed = apply_overlay(Path(argv[1]))
    except (OSError, RuntimeError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("[OK] SteamOS high-OC telemetry overlay staged" if changed else "[OK] SteamOS high-OC telemetry overlay already staged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
