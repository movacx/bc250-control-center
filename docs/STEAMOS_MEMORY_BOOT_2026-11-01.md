# SteamOS memory and boot controls — 1 November 2026

SteamOS 3.9.5 with Python 3.14 hid the kernel options panel and disabled TTM
because the unprivileged inventory could not inspect the root-only EFI boot
menu. Python 3.14's Path.is_file suppresses PermissionError and returns False,
so the existing permission handler never ran. Explicit stat now distinguishes
inaccessible from missing menus. Privileged apply still checks the real menu
and validates regenerated entries before replacing it. An actually missing
menu or an unsupported GRUB remains unsupported.

This restores access to the existing SteamOS mitigations, SMT and loglevel=0
controls and the shared 8/10/12 GiB TTM backend. The SteamOS allowlist remains
separate from CachyOS's kernel-specific CU unlock; the latter is not offered on
SteamOS. Existing external boot arguments are preserved.

The SteamOS memory selector now offers the full implemented policy set:
preserve, disk swap 16/32 GiB, half-RAM ZRAM, ZSWAP with 16/32 GiB backing swap,
and restore. Disk swap defaults to /home. Runtime capability checks continue
to protect foreign ZRAM managers, require explicit takeover where supported,
and require restoration before incompatible policy switches. A disk swap
profile no longer claims to create ZRAM when it merely preserves existing
compression settings. The new ZRAM label is translated in the interface catalog.

Validation: 20 targeted existing/new memory, TTM and boot test functions ran
against temporary filesystems and command simulators, invoked directly because
pytest is absent. Two unittest cases exercised real Qt controls offscreen,
including selectable swap32/ZRAM/TTM and disabled unsupported configurations.
A read-only source inventory on the real host now recognizes steamos-grub and
TTM support. No memory policy, boot file, sysfs parameter or live cache was
modified during this work. Applying the packaged controls and rebooting still
requires host validation.
