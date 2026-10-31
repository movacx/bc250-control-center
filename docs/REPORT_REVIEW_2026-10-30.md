# Report review — 30 October 2026 (Costa Rica)

Reviewed the 26 reports retained in the maintainer's Cloudflare inbox, including
reports received through 2026-10-31 00:04 UTC. No report was deleted or changed.
Raw reports, contact information, credentials and attachments are not copied here.

## Changes from this review

| Report | Finding | Change and verification |
|---|---|---|
| R-ff91f26c, R-26457f83; older R-df49405e, R-80c41cb8, R-a60ea60d, R-5079dcd5 | Earlier switch completion could leave repeated `[gpu-usage]` tables. Preventing new duplicates did not recover files already damaged. | The Cyan installer merges only the recognized flat compatibility tables, preserves selected values and safe-point arrays, validates the complete TOML before installation, and rejects conflicting values without writing. Regression covers the malformed layout and conflicting copies. |
| R-a8fc77e6 | SteamOS package database transfer was aborted by pacman's low-speed timeout. | Dependency and fan preparation use a shared database refresh that disables the low-speed download timeout and retries transport errors at most three times. Locks and signature failures stop immediately; signature verification and root-state restoration remain in force. Tested with fake failed/successful mirrors and non-retryable failures. |
| R-60c1e16a | The 32-bit VA-API check failed with Vulkan error -9. Its graphics attachment records a forced `VK_ICD_FILENAMES` pointing at an x86_64-only RADV manifest. | The 32-bit probe clears architecture-specific driver/library overrides only for that process and disables implicit overlays. The desktop environment and 64-bit driver are preserved. Test executes the sanitized probe environment with a fake command; actual 32-bit GPU initialization still needs the affected host. |
| R-8b3d9eac | Live manager explicitly reported that UMR was missing; the UI instead suggested an incompatible topology format. | Missing UMR now produces an action-needed notice explaining preparation and a possible Bazzite deployment reboot. Unavailable topology remains unavailable; no fabricated rows or writes. |

## Existing fixes and conditions requiring the test machine

| Reports | Status |
|---|---|
| R-6373ea51, R-6ff0c948 | Development already accepts the pinned backend's 7.2 kernel base, as well as 6.16 and 6.18. Regression checks the exact reported `7.2.7-valve2-2-neptune-72-g31504582a073` release. The reviewed upstream build contains a real 7.2-specific patch branch; no arbitrary-kernel bypass was added. A physical build/boot remains to be tested. |
| R-dce0d0a0 | Expected refusal when active Cyan safe-points exceed the reviewed SteamOS module's 2230 MHz telemetry boundary. Already an action-needed notice. Do not silently raise the kernel limit or modify the user's voltage curve. |
| R-7191a2f0 | Graphics uninstall requires reboot because the scheduler boot option remains active for the current kernel. Existing handling preserves the runtime until safe removal is possible. |
| R-bc2d99b9 | Real insufficient `/var` space. Existing SteamOS guard explains required space; UMR storage repair has regression coverage. It must not delete user data automatically. |
| R-7cfcf8d7 | A second preparation was refused while another owned the lock. Expected coordination; do not remove a live lock. |
| R-312525ce | Missing Cyan unit is covered by the current upstream installer, which installs the official service/policy and reloads systemd/D-Bus. |
| R-9dfe6c8f | Cyan was explicitly configured for kernel control and returned remote I/O error 121. Current code checks the requested backend. Hardware/kernel behavior must be retested; do not silently substitute SMU or change compatibility switches. |
| R-5bdaa9a8 | Oberon transition refused because trustworthy GPU telemetry was unavailable. Preserve the idle-transition guard and retest telemetry on the affected system. |
| R-4631ede6, R-e6aaeafd | rpm-ostree dependency conflict involving a host-installed TrueForce package and DKMS. Do not remove unrelated host packages to force preparation. Requires a compatible image/package set on that host. |
| R-c31b77ad | External async-compute release rejected an unsupported Bazzite image version. Current integration follows the official reviewed lifecycle; no fake version rewrite. |
| R-50ff31f2 | Current uninstall additionally asks pacman which package owns a remaining governor binary, covering alternative AUR package names. |
| R-1c2419c1 | Pacman database lock. Another package transaction must finish; do not delete the lock automatically. |
| R-19627eb5, R-10c45cc3 | Existing memory setup handles supported Ext4/Btrfs layouts and checks remaining disk space. Insufficient free space remains a real prerequisite. |
| R-ee797682 | Existing Mesa PPA candidate parsing runs in a fixed locale; regression covers non-English apt output. |

## Before physical testing

Use `desarrollo/bc250-control-center`, update/reinstall the application and its
privileged helpers from the same revision, and reopen it. A web reload alone
does not update system helpers. Confirm dependency preparation first, then CPU,
CU, GPU, sensors and boot persistence. Keep the workflow log for any failure.
Kernel modules, game workloads, cold boots and SteamOS update persistence require
the actual distributions; passing simulated tests does not certify those paths.

Upstream references: [pinned SteamOS build](https://github.com/keyboardspecialist/bc250-steamos/blob/e1563f2051727702a000b6ff6f6c524e2792aa21/bc250-audio-fix/build.sh),
[pacman options](https://man.archlinux.org/man/pacman.8.en),
[Vulkan driver overrides](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md#overriding-the-default-driver-discovery).

## Validation completed on 31 October 2026

- Report/distribution regression: **572 passed, 14 skipped**. The skipped cases
  require Debian's real `dpkg`, which is unavailable on this Bazzite host.
- Install-source structure, shell/Python syntax and vendor checks passed.
- The full suite initially returned **6542 passed, 150 skipped, 5 failed**.
  Four failures have been addressed: the web adapter now imports host operations
  through application facades; diagnostic coverage again meets the unchanged
  87% minimum; the Debian installer assertion includes the required Cheroot
  package; the lock test retains a complete real `stat_result` instead of
  breaking pytest's own output capture.
- Follow-up checks: **53 passed** for architecture, installer, lock and diagnostic
  coverage; **255 passed** for web, diagnostic behavior and error-catalog
  contracts. Lint passed for the changed Python files.
- One pre-existing full-suite failure remains: 74 Remote access keys are absent
  from the non-Spanish/non-English locale catalogs. English, Spanish and Latin
  American Spanish have the complete key set. This is recorded as unfinished
  localization work, not hidden by adding English placeholders or relaxing the
  completeness test. The entire full suite has not been rerun after the
  follow-up changes; only the affected suites were rerun.

These checks used isolated configuration/state directories and fake hardware
where required. No OC, voltage, CU routing, package installation or SteamOS boot
change was applied to the developer's board by the validation.
