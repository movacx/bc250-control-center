# SteamOS integration · verification status

Status: **in progress; physical validation missing**. This is a requirement
audit of the current worktree, not a release/support-completion declaration.
The integration remains uncommitted after the requested baseline commit.

Baseline: `6940210` — searchable support handbook and report fixes.
Main provider: rpf16rj/bc250-steamos-real-toolkit 1.12.0,
`88abd200170c8855f45cc6883e72d243151ceb7a`.
The user's later instruction retains keyboardspecialist as an explicit
alternative; it supersedes the original request to remove it altogether.

## Requirement audit

| Requirement | Current evidence | What remains unproven |
| --- | --- | --- |
| Commit the existing work first | Baseline commit `6940210` exists. | Nothing for this baseline requirement. |
| Real Toolkit is the primary SteamOS flow | Primary dependency, graphics, Proton and GPU-dialog routes use the closed Real Toolkit launcher; fixture routing tests pass. | Execution of these routes on actual SteamOS. |
| Expose every upstream option | 66 unique operational actions in 33 native component rows; 109 recorded menu entries; root options mapped individually, with Help/What's new as desktop links and native/upstream return handling. | Exercising every nested menu and component with its required devices/software. |
| Preserve working native controls | Core GPU/CPU/CU repository code and native Decky plugin remain unchanged; ownership checks cover nine component families; bidirectional fan and VA-API coexistence tests pass. | Real GPU, CPU OC/persistence, CU, fans, monitoring, BIOS, Blackbox, remote access and both Decky plugins across install/reboot/recovery. Unchanged code alone does not prove this. |
| Maintain keyboardspecialist as an alternative | 11 explicit lifecycle actions; separate status/install/remove routes; protected current-kernel stock rollback; no fallback after primary failure. | Physical upgrade, repair and cleanup of current and older installations. |
| Preserve provider ownership and rollback | Graphics prefixes/selections and kernel-only markers checked; native overlap rejected; interrupted rollback markers retained; bulk recovery scans all kernels; individual actions stay scoped. | Actual module selection, initramfs regeneration, recovery boot and mixed-provider cleanup. |
| Consume reviewed source and preserve interaction | Whole archive digest verified; preparation covers 3790 files and seven vendored projects; all 52 shell scripts parse; 33 guarded functions; AUTO=0; allowlisted dispatch. | Upstream installers' live downloads/builds, device behavior and all interactive decisions on supported SteamOS. Source attestation does not validate future downloaded dependencies. |
| Root/user boundaries and cancellation | Canonical UID lookup, OS/hardware preflight, protected runtime/cache, archive/workspace/lock lifecycle, original child status and signal forwarding tested. | Real sudo, writable-root windows, terminal teardown, detached descendants, power loss and physical recovery. |
| Source and package installation | Same protected helper/runtime layout; source-install and package staging/isolation tests pass; cached checker imports after global helper removal. | Real install/update/uninstall on SteamOS and already-installed external Decky/recovery workflows afterward. |
| Native UI and localization | Existing Additional Settings row/More renderer reused; search/categories and language refresh tested; complete 30-language catalogs validated; Spanish Qt render inspected. | Actual SteamOS display scale, keyboard/controller navigation and live status refresh during operations. |
| Leave credits unchanged | README and THIRD_PARTY_NOTICES have no diff from the baseline. | User will update credits after their tests, as requested. |
| Fully validated SteamOS support | Software evidence below is available. | Not achieved: no physical SteamOS lifecycle result exists in this worktree. |

## Evidence and reproducibility

The latest combined regression run covered 51 test files: **821 tests and
10 subtests passed**. It includes SteamOS/provider routing, actual fixture
process cancellation, coexistence, native fan/video behavior, UI/presenter,
30-language catalog integrity, local install layout and privileged packaging.
These results have different scopes and must not be treated as hardware tests.

The complete pinned source archive was separately prepared and syntax checked
with [validate-steamos-toolkit-source.py](../scripts/qa/validate-steamos-toolkit-source.py).
The tool records archive/revision and adapter hashes, checked paths and counts;
it never executes upstream installers. Actual attested Decky methods were
also checked against a temporary refusing checker before configuration/PWM
access, without loading a real Decky session.

Before physical tests, run the source validator against the pinned archive,
`scripts/qa/validate-install-source.sh .`, and
`python3 scripts/development/generate_steamos_toolkit_runtime.py --check`.
Do not edit bundled runtime sources without regenerating their archive.

## Physical test gate

The inspected development host is `ID=arch`, kernel
`7.3.4-1.425-cachyos-bc250`. It cannot supply SteamOS boot/driver evidence.
No real Toolkit installer, kernel/module/initramfs mutation or root-mode
change was performed during this integration verification.

Use [STEAMOS_HARDWARE_VALIDATION.md](STEAMOS_HARDWARE_VALIDATION.md) for the
full matrix, including clean/native/alternative installations, every component,
reboot, rollback and emergency recovery. Every row requires real recorded
results. Unsupported or absent peripherals remain untested; they do not pass
by omission. The known upstream minimum kernel gate is not proof that every
newer kernel is supported.

The chronological implementation/source review is in
[STEAMOS_REAL_TOOLKIT_MIGRATION.md](STEAMOS_REAL_TOOLKIT_MIGRATION.md).
