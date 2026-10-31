# Report and native-package review — 31 October 2026

The Cloudflare inbox contained 42 reports at this review's final retrieval,
including seven from 1.21.4. Reports and attachments were downloaded intact;
workflow output, error details and diagnostic attachments were compared with
the current development implementation. Repeated journal messages were grouped
for inspection. Some submitted attachments are already truncated; an omitted
outcome cannot be inferred from the report title. No reports were modified or
deleted. Private contacts, machine identifiers and raw attachments stay outside
this repository.

## Corrections

- Package staging normalizes every directory to 0755 even under umask 0002 or
  when an existing staging directory is 0775. Previously intermediate archive
  entries could retain group-write permission.
- Package post-install and the local installer tighten only exact root:root
  0775 ancestors at `/`, `/usr`, `/usr/libexec`, `/etc`, `/var`, `/var/lib`.
  This does not weaken the helper trust check, change ownership recursively,
  or accept writable dependencies. The Mint failure is reproduced with an
  installed helper and an unsafe container root; repair restores its protocol
  response. An upgrade from package revision 1 to 2 also repairs that condition.
  The old archive permissions alone do not prove how the reporter's root
  acquired its permissions: dpkg preserved an existing 0555 root in a separate
  reproduction.
- The local installer also updates the package-maintenance helper inside its
  privileged rollback transaction, with byte comparison and ownership checks.
  The local uninstaller preserves package-owned copies. This prevents a mixed
  source/package update from retaining the older maintenance entry point.
- Helper trust failures outrank argparse's exit status 2 and generic CU/GPU
  context in diagnostics. They no longer incorrectly imply a version mismatch.
- Mesa's source build prepares Meson >=1.4 in a private build environment when
  the distribution's Meson is older. Ubuntu 24.04's real Meson 1.3.2 remains
  installed and unchanged; the isolated Meson configures the build instead.
- Bazzite runtime preparation no longer layers DKMS. The Bazzite fan installer
  already builds a kernel-specific module without DKMS; adding it unnecessarily
  activated an unsatisfiable Logitech TrueForce conditional dependency on 45.
  A shell-level regression executes runtime preparation with this conflict
  modeled and verifies that only the actually missing runtime package is queued.
- Gentoo local installation selects Portage runtime dependencies independently
  of the `cmp` check. The old Portage runtime branch was mistakenly nested in
  diffutils preparation. Diffutils now requests `sys-apps/diffutils`, and a
  regression executes the real installer with `cmp` already present and a
  recording Portage command to verify Python/psutil/Git are still requested.
- CachyOS preparation accepts explicitly configured generic/v4 official layouts
  when `[cachyos-v3]` is absent, preserving repository ordering and retaining
  refusal when no recognized anchor exists.
- Privileged TOML migration also removes an identical repeated compatibility
  table header when all its entries are duplicates. Conflicting/new values are
  refused; entries are never moved into safe-point array tables.
- RPM signature failures receive the existing package-signature diagnosis.
  Signature checks remain enabled. Fan-helper and unsupported GDDR6-firmware
  refusals also have specific diagnostics.

## Report disposition

“Existing fix” means present in development, not proof that an older installed
release contains it. “Host validation” means the supplied evidence is insufficient
to certify the physical kernel, service or device operation in a container.

| Reports | Evidence and disposition |
|---|---|
| R-3163566b, R-590bf979, R-ad63886f, R-9305caee | 1.21.4 Mint helper rejects `/`. Permission repair and corrected diagnostic; native upgrade reproduction passes. |
| R-6cd4c6f7, R-a68c799b | Same 1.21.4 ancestor trust failure affects CU executor/Cyan preflight. Shared repair; no trust bypass. |
| R-a7549131 | 1.21.4 Mint Mesa build uses Meson 1.3.2 against >=1.4 requirement. Isolated build tools verified on Ubuntu 24.04. |
| R-26457f83, R-5079dcd5, R-80c41cb8, R-a60ea60d, R-df49405e, R-ff91f26c | Repeated Cyan `[gpu-usage]`. Existing installer migration merges recognized compatibility tables safely; privileged migration gets additional identical-header coverage. |
| R-4631ede6, R-e6aaeafd | Bazzite 45 TrueForce/DKMS depsolve conflict. Removed unnecessary DKMS request rather than unrelated host packages. |
| R-312525ce | Missing Cyan unit after the same preparation conflict appears in attached workflow logs. DKMS request corrected; existing Cyan runtime repair installs the reviewed service. |
| R-b68ac341 | CachyOS v3-only repository anchor. Explicit generic/v4/core layouts covered by executable shell regressions. Attached Qt shutdown traceback is already fixed. |
| R-6b3d1026, R-8e796dad | User answered `n` to pacman's installation prompt. Respect cancellation; do not auto-approve system upgrades. |
| R-d4d87dbd | Pacman prompt received `yy`, not a valid affirmative response. No evidence of a package/helper mismatch in this transaction. |
| R-18cd85d8, R-6373ea51, R-6ff0c948 | Older release rejected Valve kernel 7.2. Existing development supports the reviewed upstream's real 7.2 patch branch; exact reported release has regression coverage. Physical build/boot remains host validation. |
| R-dce0d0a0 | Active high safe-points exceed the reviewed SteamOS module's 2230 MHz limit. Preserve refusal and user curve. |
| R-7191a2f0 | Scheduler policy remains active in the running kernel after boot options are removed. Existing uninstall retains compatible RADV until reboot and retry. |
| R-c31b77ad | External async-compute release supports Bazzite 44, not the reported 45 image. Preserve reviewed release boundary; no image-version spoofing. |
| R-10c45cc3 | Old Btrfs-only swap restriction. Existing development supports Ext4 too; attached deleted Qt signal traceback already fixed. |
| R-19627eb5 | Insufficient free space for selected swap size plus reserve. Preserve space guard. |
| R-bc2d99b9 | SteamOS `/var` has 78 MB free. Preserve capacity preflight; UMR database/service repair already covered in development. |
| R-a8fc77e6 | SteamOS repository download times out. Existing bounded refresh retries cover transport failure and restore root read-only state. |
| R-1c2419c1 | Pacman database is locked by another transaction. Wait for its owner; no automatic lock deletion. |
| R-7cfcf8d7 | Another preparation is running. Preserve serialization. Attached older missing helper/config/UMR service state requires installation/preparation and host retest. |
| R-ee797682 | Locale-dependent apt candidate parsing. Existing fixed-locale parsing has regression coverage. |
| R-50ff31f2 | Oberon executable belongs to an alternative package. Existing uninstall checks package ownership and removes through pacman. |
| R-4745effe | External 1500 MHz sweet-spot curve lacks required high-frequency points. Preserve explicit refusal; do not manufacture voltages. |
| R-dd9d2016 | Requested frequency is not loaded by Cyan. Existing prerequisite message requires explicit safe-point enable/load. |
| R-5bdaa9a8 | Oberon transition has no trustworthy idle telemetry. Preserve idle guard; physical telemetry needs host validation. Attached Qt shutdown traceback already fixed. |
| R-8b3d9eac | UMR is missing, so four topology rows cannot be read. Existing action-needed diagnosis calls for dependency preparation. |
| R-9dfe6c8f | Cyan kernel-control request fails with remote I/O error 121. Requires host/kernel/SMU validation; do not silently change control backend or compatibility choices. |
| R-60c1e16a | 32-bit VA-API probe inherited a 64-bit Vulkan manifest. Existing process-local environment sanitization covered by regression; real GPU probe still needs host validation. |
| R-f0ed2fdd | Report ends at sudo authentication with no exit status or build result. No basis to assert a compiler/package defect; attached ACPI check correctly refuses an existing external override. |
| R-f80a5fcc | Fedora rejects printer RPM signature. Improved signature diagnosis; repository/key/cache correction belongs to the host. Attached Qt shutdown traceback already fixed. |

Kernel attachments also contain upstream display/EDID/IRQ warnings, unsupported
clock requests, missing UMR/service prerequisites, SMU I/O failures and unrelated
application faults. These do not establish a packaging cause by themselves.
They are retained as host validation evidence, not labelled repaired by a
userspace container test.

## Verification

- Targeted packaging, distributions, unit, diagnostic coverage and privileged
  TOML regressions: **1131 passed, 16 skipped**. Skips require Debian's native
  dpkg or package-host behavior unavailable on the development host.
- Actual native DEB installations: Ubuntu 24.04 (Mint base), Ubuntu 26.04,
  Debian, Devuan, Kali, Parrot, Kubuntu, Xubuntu and Lubuntu.
- Actual native RPM installations: Fedora 44 and Bazzite 44 OCI userspace.
- Actual native pacman installations: Arch, CachyOS, Manjaro and Artix OpenRC.
- Local TUI installer and privileged helper checks: Alpine and Gentoo OpenRC.
  Their prepared dependency environments were reused; no Portage transaction
  is claimed for Gentoo.
- Each helper check compares installed privileged scripts/modules/vendor payload
  against source (allowing RPM's standard Bash interpreter-line normalization), verifies ownership/write permissions, reproduces unsafe-root
  rejection and repair, reads protocol 2 as root and UID 65534, then verifies a
  genuinely writable helper dependency is still rejected.
- Clean-install QA now installs and verifies privileged helpers rather than
  skipping them. The shared container-only check is retained in the repository.
- Final artifacts were also installed with apt, DNF and pacman; the actual source
  archive was installed on Alpine and Gentoo, including a CLI version check.
  Kali's final repeat encountered a slow mirror: the remaining archive was fetched
  separately with the same SHA-256 and apt completed its normal verification.
- Native-package builders default to revision 2 of 1.21.4 so an upgrade orders
  after the previous revision 1 package. Build and native checks run in
  disposable rootless containers, with no host devices or hardware writes.

These checks validate package userspace and the helper trust boundary. They do
not certify cold boots, init services under the real distribution, Secure Boot,
kernel-module loading, stress stability or GPU behavior. Development changes and
local package artifacts are not a public release.
