# SteamOS integration · verification status

Status: **in progress; physical validation missing**. This is a requirement
audit of the current worktree, not a release/support-completion declaration.
The integration remains uncommitted after the requested baseline commit.

Baseline: `6940210` — searchable support handbook and report fixes.
Main provider: rpf16rj/bc250-steamos-real-toolkit 1.12.0,
`88abd200170c8855f45cc6883e72d243151ceb7a`.
The user's later instruction retains keyboardspecialist as an explicit
alternative; it supersedes the original request to remove it altogether.

> **Update 2026-11-17 — the provider is no longer pinned.** Real Toolkit follows the
> newest commit of its `main` branch: each run resolves the commit hash, downloads that
> exact archive and records it in `.bc250cc-provider.json`. Trust is structural, not by
> digest: the entrypoint must keep the one main loop and startup boundary the adapter
> patches, every action function we dispatch and every function we guard; otherwise
> nothing runs. A failed action (exit status 1-127) or a failed preparation clears the
> cache (archive and workspace, never the guard runtime), so the next attempt starts
> from scratch with whatever upstream has published since. Interrupts keep the cache.
> Offline, the last downloaded copy is used. Rows for GPU/CPU/CU, profiles, memory/swap,
> fans/sensors, CoolerControl and the upstream extras are not exposed: Control Center
> offers those natively. Where this note and the sections below disagree on pinned
> revisions or digests, this note wins.

> **Update 2026-11-18 — SteamOS read-only root.** The toolkit lifts the protection itself
> (`steamos-readonly disable`) and turns it back on blindly; Control Center answers for the
> state it leaves behind. `steamos-readonly status` prints the state and exits 1 while the root
> is writable, so the text is read, never the exit status. Before each action the launcher
> reads the state (retrying a slow answer once), refuses with what the command said when it is
> unreadable, refuses below 40 MB free in /var and warns below 250 MB. The state to give back is
> written to `root-session.json` before the toolkit starts, so a power cut, a killed terminal or
> a reboot cannot turn its leftover unlock into the "original" state: the next run, or the
> Preparation panel, sees a note whose process is gone with the root still unlocked, and locks it
> again. Restoring is verified and retried, and prints the exact command when it fails. A root
> the user had already unlocked stays unlocked. The failed action keeps the toolkit's own logs in
> `last-failure/` before the cache is cleared. The launcher also checks that the account has a
> sudo password first, like every other SteamOS workflow.

> **Update 2026-11-18 — pre-delivery review on a real SteamOS 3.9.5 (7.2.7, Spanish locale).**
> Checked against the live commands of that machine and fresh clones of both toolkits
> (rpf16rj `main` = `88abd20`, keyboardspecialist `master` = v0.40.0 `6aee553`):
> * The adapted `start.sh` can no longer hand over to a freshly cloned, unprepared copy:
>   upstream's "standalone" path (`exec bash "$TOOLKIT_REPO_DIR/start.sh"`, taken when the tree
>   has neither `.git` nor `external/bc250_smu_oc`) is replaced by a refusal, and an archive
>   without that vendored tree is refused before anything runs.
> * An ownership refusal (checker status 79) keeps the toolkit cache; only real failures clear it.
> * The preflight also warns when `/` (5 GB, nearly full on SteamOS) has less than 300 MB.
> * `update-local.sh` matched pacman's English "is owned by"; on a Spanish system it missed a
>   pacman install and would have overwritten package files. Ownership is now read from exit
>   statuses (`pacman -Qoq`). `install-local.sh` warns before overlaying a package's helpers.
> * `uninstall-local.sh` now opens and restores the SteamOS root around helper removal.
> * The TUI read-only "Status" no longer reports a writable root as a failure (exit 1).
> * keyboardspecialist (pinned `e1563f2`, v0.30.0): its `install.sh` deliberately leaves
>   `amdgpu.sched_policy=2` off until RADV setup; Control Center no longer writes it back right
>   after the module ("deferred until Mesa / RADV setup" is accepted as complete). The retired
>   "Install per-game FSR4" button, which could only fail, is gone.
> * Native AC-3 and OpenLinkHub now recognise the Real Toolkit's copies, and the toolkit's
>   OpenLinkHub install is guarded against the native one.
> Physical results are still pending; see the delivery list in
> [STEAMOS_HARDWARE_VALIDATION.md](STEAMOS_HARDWARE_VALIDATION.md).

> **Update 2026-11-18 — keyboardspecialist alternative pinned to v0.40.0.** The reviewed
> revision is `6aee5530a07f2c1a4fd2f23c00a87986030c5b35` (master and tag v0.40.0, 2026-11-17),
> replacing `e1563f2` (v0.30.0); the Proton checkout still follows master. The kernel patches,
> the GFX1013 commit (DryhoppedIPA `d3e6dc06`, legacy `b66203e`), the marker tag
> `smu-8core-metrics-r1`, the deferred `amdgpu.sched_policy=2` and the status texts are unchanged.
> * Upstream v0.38 fetches build dependencies from the installed channel itself
>   (`fetch-build-deps.sh`, `pacman-conf --repo-list` → extra-3.9/core-3.9 on 3.9.5, SHA-256 and
>   runtime checks). Control Center's GLIBC_2.44 adapter (`prepare-steamos-build-runtime.py`,
>   `*-bc250cc.sh`, `deps-bc250cc-*`) is retired and its leftovers are removed; the upstream scripts
>   run unchanged. A dependency step that fails upstream's runtime check still reports
>   `STEAMOS_BUILD_RUNTIME_INCOMPATIBLE` (BC250-BUILD-001), before the kernel download.
> * The protected copy also carries `bc250-audio-fix/fetch-build-deps.sh` and
>   `bc250-mesa-patches/libdrm-2.4.134-wrap.patch` (Mesa 26.3 setup refuses to build without it).
>   Upstream's `scripts/` is never copied and the guard refuses it: since v0.37 the entrypoints
>   source `scripts/feature-tracking.sh` when present, which would run its Python recorder as root.
> * RADV: Mesa 26.3.0, DirectMesh 1.4 enabled for every game (upstream default), profile
>   `directmesh-1.4-mesa-26.3-fsr4-v7`; intact v4/v5/v6 installs read as installed but not current.
> * Installations made by Control Center 1.22.x (`main`, v0.30.0 pin) stay supported. Kernel
>   Check, Mesa / RADV Check and Restore the stock module accept the complete copy it staged
>   (`LEGACY_STAGES`: e1563f2 with that release's members, same ownership/permission/no-link
>   checks) and say it is from v0.30.0; Install / update and Remove stage v0.40.0 first and never
>   run from the old copy. Its module markers and RADV manifest (mesa-26.2.2,
>   `production-fsr4-v4`) read as installed, not incomplete; after the stage moves to v0.40 the
>   status report shows that RADV as "Installed (earlier release)" instead of upstream's
>   "invalid". Proton install/update waits for the v0.40 stage (upstream wants a current RADV).
>   Copies staged by releases before e1563f2 (v0.21.2) must be prepared again before Check or
>   Restore.
> Checked against the real v0.40.0 tree (structure, constants, `bash -n`) and this SteamOS 3.9.5 /
> 7.2.7 host (read-only). Building, installing and booting remain physical tests.

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
