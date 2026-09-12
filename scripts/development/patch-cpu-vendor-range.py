"""Rebuild the audited bc250_smu_oc payload with the two reviewed local patches.

Run from the repository root. Both patches were explicitly approved by the
project owner so that the 3100-4200 MHz range the interface offers is the range
the payload actually executes.
"""

import hashlib
import pathlib
import re
import sys
import zipfile

ZIP = pathlib.Path("privileged/lib/bc250_smu_oc_vendor.zip")
HELPER = pathlib.Path("privileged/helpers/bc250-cpu-smu-helper")
# Patching is done from the unpatched payload, so running this twice is safe.
BACKUP = pathlib.Path("/tmp/claude-1000/bc250-i18n/vendor-original.zip")
ORIGINAL = BACKUP if BACKUP.is_file() else ZIP

NEW_LIMITS = """freq_min = 3100
freq_max = 4500

vid_min = 950
vid_max = 1325

temp_min = 0
temp_max = 100

scale_min = -50
scale_max = 0
"""

PATCH_NOTE = """
Local audited patch:
- Lower freq_min from 3500 to 3100 MHz. Upstream refuses below the stock
  frequency because bc250_detect is an overclocking tool and reads "below
  stock" as a usage mistake. The limit is not a hardware protection: the SMU
  accepts the lower request and bc250_apply needs no other change. BC250
  Control Center offers 3100-4200 MHz so the same board can also be
  underclocked for heat and noise. freq_max stays at the upstream 4500; the
  interface stops at 4200.

Local audited patch:
- Start the detection search at the requested frequency when it is below
  stock. Upstream always starts at 3500 MHz and climbs, and its exit condition
  is "stop once f_safe is no longer below f_target". With a below-stock target
  the very first iteration already satisfies that, so the detector applied
  3500 MHz and wrote it to overclock.conf as if it were the requested result.
  Lowering freq_min without this turns a clear argparse error into a silently
  wrong frequency. At and above 3500 MHz the expression is unchanged.
"""

OLD_START = "    f_start = 3500 + (f_target % f_step)"
NEW_START = (
    "    # BC250CC: a target below stock has nothing to search for, and\n"
    "    # starting at 3500 made the detector apply and record 3500 instead.\n"
    "    f_start = f_target if f_target <= 3500 else 3500 + (f_target % f_step)"
)


def main() -> int:
    with zipfile.ZipFile(ORIGINAL) as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]

    applied = set()
    for index, (info, data) in enumerate(entries):
        if info.filename == "bc250_limits.py":
            entries[index] = (info, NEW_LIMITS.encode())
            applied.add("limits")
        elif info.filename == "BC250CC_PATCHES":
            merged = data.decode().rstrip("\n") + "\n" + PATCH_NOTE
            entries[index] = (info, merged.encode())
            applied.add("patches")
        elif info.filename == "bc250_detect.py":
            text = data.decode()
            if OLD_START not in text:
                print("the upstream search-start line was not found", file=sys.stderr)
                return 1
            entries[index] = (info, text.replace(OLD_START, NEW_START, 1).encode())
            applied.add("detect")

    if applied != {"limits", "patches", "detect"}:
        print(f"only applied {sorted(applied)}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as target:
        for info, data in entries:
            target.writestr(info, data)

    digest = hashlib.sha256(ZIP.read_bytes()).hexdigest()
    text = HELPER.read_text(encoding="utf-8")
    text, count = re.subn(
        r"EXPECTED_VENDOR_SHA256 = '[0-9a-f]{64}'",
        f"EXPECTED_VENDOR_SHA256 = '{digest}'",
        text,
        count=1,
    )
    if count != 1:
        print("the helper SHA-256 pin was not found", file=sys.stderr)
        return 1
    HELPER.write_text(text, encoding="utf-8")

    print("sha256:", digest)
    with zipfile.ZipFile(ZIP) as check:
        source = check.read("bc250_detect.py").decode()
        line = next(row.strip() for row in source.splitlines() if row.startswith("    f_start ="))
        print("detector:", line)
        print("limits  :", check.read("bc250_limits.py").decode().splitlines()[0])
        print("upstream:", check.read("UPSTREAM_COMMIT").decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
