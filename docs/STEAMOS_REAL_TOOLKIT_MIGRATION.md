# SteamOS Real Toolkit migration

Status: in progress. This document records the full requested scope, not a
claim that an upstream checkout or a menu launcher completes the integration.

For the current requirement-by-requirement evidence and remaining gaps, see
[STEAMOS_INTEGRATION_STATUS.md](STEAMOS_INTEGRATION_STATUS.md). Entries below
are chronological and can be superseded by later implementation changes.

Baseline application commit: `6940210` (support handbook, search, report fixes).
Upstream: https://github.com/rpf16rj/bc250-steamos-real-toolkit
Inspected revision: `88abd200170c8855f45cc6883e72d243151ceb7a`, version 1.12.0.
The machine-readable companion inventory records the SHA-256 of `start.sh`,
every detected function/menu item, external components and extras. Preserve all
these surfaces through migration; review nested scripts separately.

## User constraints: existing Control Center features

These requirements govern the migration and supersede any earlier progress
entry proposing replacement solely because the host runs SteamOS.

Preserve Control Center's GPU controls, fan controls and engine, firmware
workflows, Blackbox, remote access, Decky Quick Access plugin, monitoring,
Compute Units, CPU overclocking, and CPU OC persistence without BIOS flashing.
Keep their configuration formats, privileged protocols and persistence behavior.
Expose Real Toolkit's overlapping options explicitly; do not silently substitute
its implementation for an existing working Control Center feature.

Source audit on 2026-11-16: upstream start.sh manages the same
`bc250-smu-oc.service` and `cyan-skillfish-governor-smu.service` names. Its GPU
installer stops/disables the existing service and removes /etc overrides before
installing its own unit. Its CPU revert may remove `/etc/bc250-smu-oc.conf`.
Therefore an explicit menu plus an ordinary confirmation does not yet prove
safe coexistence. Audit ownership and shared paths for overlapping operations,
including bulk install/revert, before declaring these routes complete.

The pending worktree leaves the core GPU repository, fan repository, firmware,
Blackbox, remote access, CPU OC config engine, CU repository and existing Decky
plugin code untouched. Preparation UI/provider changes still require review;
unchanged source alone is not evidence that an external installer cannot affect
its files or services. Hardware validation remains outstanding.

## Provider policy updated by the user

On 2026-11-16 the user explicitly requested keeping keyboardspecialist as a
maintained alternative, including existing kernel/GFX installations. This
supersedes the original requirement to remove its runtime dependency. Real
Toolkit is the main integration; users must explicitly choose the alternative
provider. Keep provider-specific status/install/remove/recovery paths and never
fall back to a different provider after a failed operation. Validate tools in
Additional Settings alongside native Control Center functionality.

## Required final state

- SteamOS workflows offer Real Toolkit as the main provider and retain
  keyboardspecialist/bc250-steamos as an explicitly selected alternative. Historical credits remain unchanged at the
  user's request; distinguish attribution from executable dependencies.
- Expose all upstream options, including install, configuration, status,
  revert and recovery. Cover profiles, CPU/GPU governors, runtime/persistent
  CU topology, CPU core unlock, UMA/TTM, mitigations, swap/ZSWAP, ACPI,
  combined kernel/display/Mesa, AC3, dual audio, Proton variants, VA-API,
  Wi-Fi/BT, controllers/chords, fan/sensors, CoolerControl, OpenLinkHub,
  Decky plugins, emulators, GRUB repair/recovery and package-keyring repair.
- Preserve upstream interactive choices instead of silently selecting defaults
  or piping answers into menus. Do not run Install All during integration tests.
- Keep desktop and Decky state coherent with the services, drivers and
  persistence files actually managed by the new provider. Preserve rollback.
- Validate the adapter with isolated command fixtures, UI tests, packaging
  checks and a reproducible SteamOS hardware test checklist. Never equate
  mocked command tests with real hardware validation.

## Observed integration constraints

`start.sh` is an executable root TUI, not a library: its top level relaunches
with sudo, configures user paths and keepalive, may bootstrap a moving checkout,
and eventually runs an interactive menu. Sourcing it in a status probe would
execute these side effects. Its CLI provides recovery flags, not a general
per-component API. Inspect this initialization before adding a dispatch adapter.

The README advertises Beta/Preview kernel 7.2.x support. This is not evidence
that the 7.3.1 kernel in the recent reports is supported. Inspect the actual
kernel build scripts and patch applicability before making that claim.

Existing application routes span dependencias_steamos, AMDGPU protected staging,
graphics runtime, Proton, CPU/CU helpers, accessory providers, package strategies,
dashboard/preparation pages, GPU UI, recovery, conflicts, packaging and Decky.
Replacing just EXTERNAL_TOOLS URLs would leave incompatible script paths and
status protocols, so do not activate a half-migrated provider.

## Work sequence and completion evidence

1. Baseline commit and pinned upstream inventory (recorded).
2. Inspect component implementations and dependencies; map every inventory
   surface to a native action and its status/rollback evidence.
3. Implement reviewed provider checkout/staging/dispatch and lifecycle tests.
4. Replace old-provider routes and expose remaining upstream features while
   preserving the native Control Center features listed above.
5. Update runtime strings/locales and provider conflict detection without
   editing credits. Keep old-provider executable routes only behind the
   explicit alternative, and verify that primary routes never silently fall
   back to it, using scoped searches and tests.
6. Exercise install/configure/status/revert/recovery against fixtures, verify
   UI and packaged payloads, then record hardware results and limitations.

The goal remains active until all requested options and the SteamOS migration
are implemented and their relevant validation is complete.

## Adapter progress

`steamos_real_toolkit.py` now defines 54 explicit native action routes and a
SHA-256-attested entrypoint transformation. It inserts dispatch before the
upstream main loop, preserves component functions, rejects unknown/extra
arguments, forces interactive confirmations (`AUTO=0`) and preserves exit
status. This module does not yet download, stage or execute the toolkit from
application routes. 61 focused tests pass; the transformed actual pinned
entrypoint passes `bash -n`. These are adapter contract checks, not hardware
validation.

The new upstream already vendors `external/bc250-steamos` as ordinary tracked
files (not a submodule). Its `fixes_repo_sync` checks that bundled directory;
the old URL constant is not used to clone it. Migration must consume this
vendored copy from the Real Toolkit revision, not separately fetch the former
repository. Preserve attribution as requested.

Staging must account for upstream `chown` of external component directories,
logs written below SCRIPT_DIR, and user-home persistence paths. A root-owned
snapshot cannot be assumed immutable after executing these routines. Design
and test the execution workspace and verification boundary before activation.
Next: protected checkout/workspace/dispatch lifecycle, component bindings and
native UI routes, followed by removal of old runtime fetches.

## Verified source preparation

The pinned codeload source archive is 127483692 bytes, SHA-256
`e019a4d5ddb8701cb3cea7681e7eef00ff8f474b1194a3a67e8521015707b813`.
`prepare_snapshot` hashes the same bounded bytes it extracts (no reopen after
verification), validates every tar member, refuses links/special files/path
traversal/duplicates, strips special permissions, validates the adapted Bash,
and atomically publishes a fresh destination. Existing destinations are never
merged or overwritten. Failure removes only the newly created staging tree.

The complete real archive was prepared successfully under `/tmp`, including
all seven external components, without executing toolkit operations. 68 tests
pass for dispatch and archive staging; lint passes. Staging ownership is a
caller responsibility: this API is not yet a deployed privileged launcher.
Persistent build-workspace handling, launcher packaging and native application
routes remain the next required work, not completed items.

## Launcher and initial application bindings

`steamos_real_toolkit_runtime.py` and the packaged
`scripts/system/run-steamos-real-toolkit.py` now implement the explicit sudo
launcher. The launcher validates action, invoking desktop user, SteamOS and
BC-250 hardware; locks concurrent application actions; caches the pinned
verified archive; prepares a fresh attested snapshot; restores tracked provider
files into a persistent workspace; and runs the selected upstream function in
the interactive terminal. Untracked build outputs/logs survive workspace refresh.
Links at provider paths are rejected. The toolkit's own prompts remain active.

Preparation of SteamOS compatibility now routes to `combined-install`.
Proton install/update, status and uninstall route to `proton-install`, `verify`
and `proton-revert`; a general service method exposes the allowlisted actions
for forthcoming native controls. These paths no longer fetch the former
provider. Other old routes/status readers are still pending migration.

110 focused tests pass across adapter, archive/runtime preparation, Proton and
clean-install routing. Test expectations tied to the old builder were updated
to the new provider contract; no real package install or hardware action ran.
The packaged entrypoint is copied by the existing scripts/system packaging rule.
Remaining work includes graphics/status ownership migration, native controls for
the remaining actions, packaging execution checks, and hardware validation.

## Native controls and graphics/verification migration

The preparation page now exposes a searchable, category-filtered Real Toolkit
index. It has 55 explicit action controls, including Launch Coach (an upstream
extra not wired into start.sh's main menus). Launch Coach runs its vendored
installer as the desktop user, following the other upstream Decky installers.
Provider dispatch and preparation assertions include this adapter-owned route.

The graphics install/remove routes and toolkit diagnostics now use the same
Real Toolkit launcher as Proton and compatibility preparation. Legacy graphics
and Proton confirmation dialogs no longer describe the former provider; their
actions pass through the common Real Toolkit confirmation and terminal path.
The native search consumes Enter instead of triggering a dialog default action.
Controls are disabled when SteamOS is only a distribution preview on another OS.
Credits and attribution records remain unchanged.

138 focused tests pass for provider dispatch, source/runtime preparation,
clean-install routing, the complete native action index, Proton card and
dashboard action integration. New operation names have Spanish/English content
fallback, like the handbook; native navigation uses normal app translations.
Other specialized SteamOS state readers and component actions still need
migration. Native status must reflect Real Toolkit files/services before the
migration can be declared complete. Packaging and hardware audit remain open.

## Passive installation evidence and preparation routing

`steamos_real_toolkit_state.py` adds a filesystem-only probe: provider snapshot
metadata, valid Mesa ICD JSON and referenced ELF library, the effective last
VK_DRIVER_FILES assignment, Proton marker plus actual compatibility-tool files,
running-kernel override candidates and component configuration markers.
It executes no toolkit code, downloads nothing, creates no files, and reports
live graphics activation as unknown rather than assuming a configuration file
proves that the running Vulkan process uses it.

The repository inventory includes this provider evidence. The native SteamOS
graphics card now displays it and routes its buttons directly to Real Toolkit;
old kernel-stage readiness no longer blocks a native verification action.
The displayed source paths point to the new workspace. General SteamOS prepare
opens upstream's component chooser, not Install All. CPU core installation uses
the toolkit route; GPU installation checks the requested governor and does not
silently substitute Cyan for an explicit Oberon choice.

145 focused tests pass, including passive probes against isolated filesystems,
missing libraries, overwritten environment assignments, incomplete Proton,
old-kernel modules, and an actual sidebar render/click through the native
verification route. Lint and diff checks pass. Specialized accessory/CU/Decky
state and action migration, old manifest/adapter cleanup and hardware checks
remain required for completion.

## Specialized installation routes

SteamOS video installation/removal (including the 32-bit preparation entry),
CPU preparation, AC3 installation/removal, OpenLinkHub installation/removal,
and sensor/PWM driver preparation/removal now delegate to Real Toolkit.
Other distributions retain their existing providers. Video tests and Flatpak
integration remain separate operations pending their own provider-path audit;
these were not silently replaced by a general status check.

Decky preparation distinguishes bootstrap-authorized installation from
plugin-only installation. The latter rechecks the actual user's Decky plugins
directory inside the terminal dispatch and returns failure without invoking
the upstream installer if Decky is absent. Three explicit sensor driver
routes and plugin-only installation bring the native index to 59 actions.

108 focused provider/routing/UI tests and 178 existing accessory/audio/video/UI
regression tests pass (286 total in these runs). No real installer, module load
or Decky service change was executed in these tests. Remaining specialized
work includes CU structured state/actions, CEC lifecycle/automation ownership,
Decky inventory, video Flatpak/testing paths, and old-provider manifest cleanup.

## CEC session ownership and Decky inventory

Native actions now include CEC setup/status, boot-wake install/remove,
poweroff-standby install/remove and restoring Steam CEC toggles. They invoke
the vendored CEC CLI as the desktop user with that user's HOME and D-Bus
session, through closed symbolic action routes. The index now has 66 actions.
Existing CEC setup and wake/poweroff automation buttons use these routes;
generic removal of the previous CEC installation still needs an explicit
migration/uninstall policy rather than silently deleting another owner's files.

SteamOS Decky inventory now looks for Toolkit SteamOS Control's actual files:
plugin.json, main.py, fan_manager.py and dist/index.js. It verifies the plugin
name and rejects symlink payloads. It does not demand package.json, the old
profile-policy subtree or the BC250 Quick Access helper/protocol. Those fields
are explicitly non-applicable for this provider, not falsely marked verified.
Other distributions retain the old plugin inventory. Legacy payload regression
tests now exercise that provider on Bazzite; dedicated tests cover SteamOS.

117 focused tests pass for these routes, artifacts and native UI. Further
work remains on CEC removal/migration, native remote-control state ownership,
CU structured actions, profile exchange, obsolete provider cleanup and hardware
validation. These changes do not establish a working SteamOS hardware boot.

## Scope correction: preserve Control Center functionality

The user clarified that functioning Control Center features must remain available
on SteamOS. This supersedes the broad provider convergence described above.
Removed unconditional SteamOS delegation from governor selection/installation,
CPU overclock preparation, core unlock installation, dependency preparation,
VA-API lifecycle, fan driver preparation, accessories, and Quick Access installation.
The existing Quick Access inventory and its protocol remain the default on SteamOS;
Real Toolkit plugin inspection is a separate explicit probe. Restored Control
Center native SteamOS diagnostics rather than replacing them with toolkit verify.
CU structured read/write backend and profile formats remain unchanged.

Real Toolkit remains available through its explicit native action index. Integration
of overlapping components must inspect existing installations, compatibility and
service ownership individually; operating system identity alone is insufficient
reason to switch providers. Earlier test counts describe earlier snapshots.

## Native diagnostics and installed payload verification

Control Center diagnostics no longer execute the old protected AMDGPU
patch-driver status command. The new passive native graphics check reads
/proc/cmdline and /sys/module/amdgpu (version, srcversion, taint and scheduler
parameter). It distinguishes missing observations from failure and explicitly
avoids claiming module attestation or Vulkan activation from these files.
The existing services, UMR/CU and NCT diagnostic sections remain. No installer
is invoked and no root privilege is requested by the graphics check.

33 focused native-diagnostic, clean-install, provider-runtime and UI tests pass.
The graphics tests execute against temporary filesystem fixtures, including a
path containing spaces and missing kernel evidence. Lint/diff checks pass.

Executed packaging/scripts/stage-package-root.sh into a temporary package root:
source structure/syntax/vendor validation and compilation passed. Executed the
staged run-steamos-real-toolkit.py with /usr/bin/python3 -I and an invalid action
with a caller PYTHONPATH set: the installed module imports worked and the
action was rejected before privilege, hardware, network or installation work.
This verifies packaging and isolated import, not a SteamOS installation.

Remaining old-provider work includes the unused compatibility staging builder,
legacy manifest entries/constants and any passive inventory assumptions; these
are not evidence that runtime migration is complete. Shared-service ownership
checks for overlapping Real Toolkit operations remain required.

## Explicit alternative backend retained

Implemented the revised provider policy: the preparation panel shared by the
dashboard and Additional Settings now exposes a separate keyboardspecialist
section with ten explicit kernel, Mesa/RADV, per-game FSR4 and GE-Proton
lifecycle actions. These have a separate action namespace, service dispatcher
and terminal titles. They cannot silently invoke Real Toolkit. Restored the
reviewed protected kernel/graphics/Proton implementations behind alternative
method names, including the existing GPU-frequency prerequisite guard and
SteamOS writable-root restoration boundaries. The new provider remains the
default for its dedicated graphics/Proton actions.

Both providers now have separate passive inventory evidence. The alternative
section displays its own RADV/FSR4 artifact state; it does not reuse Real Toolkit
state to declare the alternative installed. Real Toolkit is registered in the
external-tool manifest with its pinned revision, archive workspace and conflict
boundaries. It is not falsely represented as a verified git checkout. Credits
remain unchanged.

81 focused alternative/kernel/graphics/UI tests passed, followed by 57 focused
manifest/revision/provider/UI tests after the inventory integration. These runs
overlap; counts are not additive. Lint passed. Test execution did not run real
installers, change kernel modules or boot SteamOS.

Remaining work: enforce coexistence at mutating component boundaries, including
bulk/nested upstream menus; audit all Additional Settings external tools and
state contracts; review meaningful kernel-version compatibility; complete
locale/render verification and hardware lifecycle validation. Keeping both
providers available does not establish that their overlapping installations
can be installed or removed interchangeably.

## Native ownership guards at component boundaries

The attested entrypoint transformation now also renames 20 explicitly reviewed
upstream component functions and inserts wrappers that first run the installed
read-only native-ownership checker. The wrappers call the original function only
after the check succeeds and preserve its arguments and exit status. This
protects nested manual menus as well as direct actions. Bulk Install All/Revert
All checks the covered native components before its first action, avoiding a
partially changed setup before discovering a later CPU/GPU conflict.

The checker detects native CPU, GPU, CU and fan service definitions by actual
Control Center helper paths, plus the native Cyan preflight drop-in together
with an existing Cyan configuration. A helper binary alone does not establish
ownership; a disabled native persistence unit still does. On conflict the
operation returns 79, names the protected files and directs users to their
existing Control Center controls. No native setting/service is changed by the
check. This is not a provider-switch/uninstall workflow.

152 focused guard/provider tests and existing CPU-persistence, Quick Access
inventory and fan-persistence regressions pass. Direct/bulk/nested dispatch
fixtures prove the original function body does not run after a conflict; a
nonconflicting fixture still dispatches normally. The actual attested upstream
start.sh adapted with all wrappers passes bash -n. No real toolkit component
was executed. Lint and diff checks pass.

Coverage is deliberately explicit: Decky coexistence, core-unlock ownership,
external graphics provider ownership and other shared resources still need
individual audit/guards. The present checks do not prove those cases safe.

## Core unlock and Decky fan ownership

Confirmed a concrete core-unlock collision: both providers use
/etc/systemd/system/bc250-core-unlock.service. Native Control Center persists
through /var/lib/bc250-core-unlock/bin/bc250-core-unlock, while Real Toolkit
replaces/removes that unit using its own boot wrapper/config. The ownership
probe now recognizes the native installed-tool path. Both core install and
revert are guarded, and the bulk guard includes core persistence.

Decky source review found separate plugin directories and no deletion of native
bc250-quick-access by the Toolkit installer. Therefore native Quick Access is
not replaced or disabled merely to install the additional plugin. However,
Toolkit SteamOS Control can run a second fan curve service and directly write
PWM. The verified snapshot now attests and adapts its main.py and fan_manager.py:
mode/profile mutations check native fan ownership before changing configuration
or restarting the Toolkit fan service, and every PWM write rechecks ownership.
Status and LED functions remain available without taking over native fans.
The native plugin, helper protocol and configuration format are unchanged.

146 focused provider/Decky/ownership and existing persistent-core tests pass.
Fixtures verify conflict rejection before any config/PWM write, preserved
nonconflicting PWM execution, and protection of the native core service. The
actual pinned archive was prepared successfully with 22 Bash component wrappers
and the two adapted Decky payloads; both Python files compiled and start.sh
passed bash syntax validation. No upstream component was executed.

This does not yet prove bidirectional runtime arbitration if a user starts a
Toolkit fan daemon first and later activates native fan control. External
graphics ownership, other shared resources and physical SteamOS validation
remain outstanding.

## Reverse fan ownership detection

Native desktop, root fan helper/service, Quick Access and SteamOS Game Mode now
observe the known Toolkit fan service's populated cgroup before PWM/automatic
mode actions. This extends the existing external-controller refusal mechanism
without changing native fan profiles, engine, configuration or helper protocol.
The observation reads cgroup.events directly; it does not spawn systemctl on
every fan tick, stop another controller or manufacture a handoff marker. A
stopped/absent Toolkit service does not block native control. An existing but
unreadable cgroup fails closed. The UI includes Toolkit SteamOS Control among
running external fan managers.

Taking native control back through EXTERNAL OFF is refused while the Toolkit
service has live processes, before clearing the existing handoff marker. Native
service release also stands aside because it uses the same external-state
check. This addresses the service-started-first case documented above. It is
not a global lock protocol for every possible independent PWM writer.

82 focused helper/desktop/Decky/payload-trust tests pass. New tests exercise
actual native helper dispatch for Game Mode and Quick Access, reject session
PWM/automatic/service-enable commands before sysfs writes, preserve PWM duty
and mode, refuse takeback, and distinguish populated versus empty cgroups.
Lint and diff checks pass. No real controller or systemd unit was started.

## Graphics provider conflict boundaries

Source comparison confirmed Real Toolkit's combined install writes the kernel
override plus /opt/bc250-gfx1013 and VK_DRIVER_FILES, while the retained
keyboardspecialist runtime uses libvulkan_radeon_driconf.so, a per-user
bc250-mesh-shader manifest and a separate session generator. The Toolkit
combined revert removes /opt/bc250-gfx1013 and all VK_DRIVER_FILES lines, so it
must not execute against an alternative/custom graphics configuration.

Added read-only checks for the other provider's actual runtime artifacts,
including incomplete ICD/manifests and conflicting custom VK_DRIVER_FILES
selections. Source checkouts alone do not count as installed graphics. Toolkit
combined install/revert and bulk operations check before their original body.
Alternative kernel install and selected graphics/Proton mutations run the
installed checker before any checkout/build command. Provider status stays
available without this mutation guard. Per-game FSR4 and Proton cleanup remain
available through their provider-specific actions.

123 focused graphics/provider/alternative/clean-install tests pass. Tests cover
existing and incomplete runtimes, downloaded-source-only state, custom Vulkan
selection preservation, the stock 32-bit fallback, and guard command ordering
before clone/build. The actual reviewed start.sh now has 24 component guards
and passes bash syntax validation. Lint and diff checks pass.

These checks do not identify the owner of a kernel-only override from its
generic hash marker: both projects use the same marker scheme. A supported
explicit migration/recovery path for already mixed installations and dedicated
alternative kernel rollback still need implementation and validation. No
hardware installation or reboot was performed.

## Kernel recovery and storage correction

The alternative section now has an explicit stock-module recovery action for
the running kernel only. It invokes the pinned protected rollback.sh after
validating the complete root-owned backend tree/revision. It does not clone,
use --all or --adopt-legacy, remove Mesa/Proton, or require a particular
provider's Mesa to be absent. Thus stock-module recovery remains accessible
for mixed configurations. The confirmation explains that patched graphics
features require follow-up review/restart. An untrusted/missing backend stops
before the rollback command. A full mixed-installation cleanup plan is still
required; kernel recovery alone does not reconcile Mesa.

Found and corrected a startup ordering defect introduced by function guarding:
upstream handles --revert-all before its main loop. Guard definitions now
appear before the initial desktop-shortcut/recovery handling, ensuring the
renamed original functions remain callable through guarded wrappers there too.
A regression fixture executes this early recovery path and verifies conflict
refusal before the original revert body. Actual attested upstream syntax and
wrapper placement have been checked.

Archive measurement: 121.6 MiB compressed, 187.3 MiB tracked files expanded.
Caching the archive plus snapshot and persistent workspace in SteamOS /var
can exceed its small partition before a build even starts. Storage is now
/home/.bc250-control-center/real-toolkit, outside each desktop user's home.
The runtime validates every ancestor as a root-owned non-writable directory
without symlinks before creation/use, and checks for at least 768 MiB free
for source preparation. Kernel/Mesa builds need additional space and retain
their upstream checks. Inventory, manifest and displayed paths use the new
workspace. Previous /var paths in historical entries describe superseded work.

152 focused provider/state/ownership/alternative/clean-install/UI tests pass.
Tests also cover unsafe writable storage ancestors and low-space refusal
before file creation, as well as scoped rollback and failed trust checks.
Lint passed. No real installation, module rollback or SteamOS boot occurred.

## Additional Settings presentation revised from user references

Replaced the generic per-action Open-button list with the actual existing
PreparationInfoCard/CompatibilityBrowser row renderer used by Additional
Settings. Real Toolkit now has 33 component rows containing all 66 actions;
the alternative has three component rows containing its 11 actions. Each row
provides a title, description, named primary action and native More menu for
secondary operations. No separate stylesheet or new button theme was added.
The provider index remains searchable and filterable by module, and is folded
under its provider row until opened. Repeated optional-state labels were
removed where no component-specific observation is available.

The user supplied screenshots of the existing compatibility and boot-option
rows as visual references. Rendered and inspected the new interface with the
application stylesheet at 1250x800; preview: /tmp/bc250-steamos-tools-native.png.
The preview uses a synthetic SteamOS UI state, not real hardware evidence.
The three new provider/recovery explanatory messages were added to all 30
catalogues with translations; provider names remain literal. Long-form tool
names/descriptions currently use the Spanish/English fallback policy and
still need the broader locale audit recorded earlier.

46 focused interface, distribution-presentation, inventory-coverage and complete
locale-catalogue checks pass. New tests verify native More-menu dispatch, no
action loss or duplication across component groups, and opening a provider
index without dispatching a backend operation. Lint and diff checks pass.
Backend action keys and native-feature ownership guards remain unchanged.

## Live language changes and native ownership in the index

The existing preparation-panel language refresh now updates both provider
indices. It refreshes component titles/descriptions, primary/More action labels,
category captions and search accessibility copy without rebuilding widgets,
resetting search/category state, changing payloads or emitting backend actions.
Additional Settings already forwards this refresh; no duplicate page hook is
needed. A regression switches English → Spanish → English through the actual
page localization path and verifies preserved filters and action payloads.

The passive provider probe now reports native ownership evidence separately
from shared configuration presence. A CPU configuration file alone is still
only presence evidence; a unit pointing at the native CPU helper identifies
Control Center ownership without implying a Toolkit installation. The native
index displays this ownership and disables precisely the protected operations
whose component guards apply, including bulk/profile actions when relevant.
Manual/status menus and unrelated components remain accessible. The privileged
checker remains authoritative and rechecks immediately before execution.

38 focused UI, native-ownership/probe and widget-localization tests pass. They
cover ownership appearance/removal, preserved disabled states after language
refresh, shared config versus provider preparation, and no backend dispatch
during localization. Lint passed. Hardware verification remains outstanding.

## ACPI, AC-3, dual audio and HDMI-CEC coexistence

Source audit confirmed ACPI overlaps through early-initrd selection: native
Control Center uses its marked 92-bc250-acpi.cfg drop-in and bc250-acpi.cpio,
while the Toolkit writes acpi_override.cpio and modifies the main GRUB setting.
AC-3 and dual audio also overlap semantically: the Toolkit dual-audio installer
removes AC-3 profile sets/rules that the native implementation relies on.
Added marked-native-artifact ownership checks for ACPI, AC-3 and CEC, including
user configuration under the actual invoking user's home. A packaged AC-3
profile alone does not falsely establish native ownership.

ACPI install/revert, AC-3 install/revert, dual-audio install/revert and the CEC
menu now have component wrappers; the attested entrypoint has 31 guarded
functions. Direct CEC mutation routes check ownership before entering the user
session; direct CEC status remains available. Bulk checks include ACPI/audio
but exclude CEC because the reviewed bulk functions do not change CEC. The UI
uses the same component classification, preventing false bulk lockouts from a
native CEC configuration.

Corrected passive dual-audio evidence to inspect the user WirePlumber and
PipeWire configuration files actually installed by this Toolkit revision,
rather than an obsolete /etc path. Native ACPI/audio/CEC implementations and
formats were not replaced.

173 focused provider/ownership/UI and existing audio/TV accessory tests pass;
two subsequently added cases for CEC UI isolation and actual dual-audio paths
also pass. The actual reviewed entrypoint adapts and passes Bash syntax with
all 31 wrappers. Lint and diff checks pass. No live ACPI, audio or CEC change
was performed. Remaining audit includes other shared resources, mixed-graphics
cleanup, packaged execution and physical SteamOS lifecycle evidence.

## Recovery failure propagation and root-mode postconditions

Found two upstream recovery paths that suppressed a failure: --revert-all
converted any result into exit 0, and the generated recovery controller
continued cleanup/reboot after a failed Toolkit revert. The attested adapter
now preserves the revert status, checks ownership before unlock (including
the self-contained emergency path), resolves the state directory owner's UID
for user-specific checks, verifies that root actually became writable, and
stops before success cleanup/reboot when the child revert fails or is refused.
The upstream controller's EXIT trap that restores its own readonly window is
retained. Template changes fail preparation rather than silently dropping the
recovery adaptation.

The normal packaged launcher now reads the initial SteamOS root mode without
unlocking it, lets upstream own its short privileged windows, then verifies
and restores the original mode on completion or Python exceptions. An unknown
initial mode stops before executing the Toolkit. A failed/unverifiable restore
is an error even if the component returned success. Source downloads/build
preparation do not require a writable root. This is not yet evidence for
unhandled process termination, power loss or real boot recovery.

111 focused provider/launcher/recovery tests pass. They execute fixture command
flows only: refusal before unlock, child failure without cleanup/reboot,
failed-unlock refusal, successful recovery continuation, original status
preservation, initially writable/protected roots, unknown state and failed
restoration. The actual attested source adapts and passes Bash syntax; lint
passes. No real root mode, kernel or boot entry was changed.

## Protected runtime for packaged and source installations

Removed the privileged launcher's dependency on a fixed /usr/share source
checkout. Source installations can use a different application prefix, and
root Python must not load the desktop user's modules or optional GUI stack.
Both installation routes now install the same two entrypoints under
/usr/libexec/bc250-control-center with an adjacent, deterministic stdlib-only
runtime archive. The source validator rejects an archive that differs from
its current module sources. Launch commands use Python isolated mode.

The Toolkit's guarded Decky payload and generated recovery controller use a
protected copy of the checker/runtime under /home/.bc250-control-center/
real-toolkit/runtime. This is outside the upstream workspace that build steps
may chown to the desktop user. App uninstall removes its managed global
helpers, while this independent guard runtime remains available to the
already-installed upstream workflows. Each explicit Toolkit launch refreshes
the cached guard from the currently installed protected files.

131 focused launcher, runtime, distribution routing, local installation and
privileged packaging tests pass. Tests also execute both entrypoints with
Python -I -S and a poisoned PYTHONPATH, and execute the cached checker after
removing its global source files. An actual package staging into a temporary
directory passed source validation, produced helper modes 0755/runtime 0644,
and both staged entrypoints imported successfully without site packages.
Lint and diff checks pass. No package was installed on this host and no live
Toolkit action or SteamOS root-mode change was performed.

A separate 131-test regression run passed for the native-style Toolkit panel,
attested entrypoint adaptation, Decky guards, recovery failure propagation,
graphics ownership and the retained keyboardspecialist alternative (262 tests
across the two runs). Physical SteamOS lifecycle validation remains pending.

## Bulk recovery must preserve component failure

Further inspection of the attested start.sh showed that fixing the outer
--revert-all exit status was insufficient: run_revert_all itself ignored
component failures and could purge recovery state after an unsuccessful
rollback. Bash errexit does not supply the missing guarantee when the function
is invoked inside an OR-list. The adapter now adds explicit failure propagation
to each of the 16 reviewed component/recovery-entry operations. Preparation
rejects a changed function/step contract. Successful order and final cleanup
are retained; failures stop before subsequent operations and state purging.

114 focused adapter/recovery/standalone-runtime tests pass, including failure
at each of the 16 steps under a conditional call and successful cleanup. A
separate check extracted the actual adapted upstream bulk-revert function and
executed it with marker-only operations: every injected component failure
preserved exit 23 and stopped later operations/purge; the success case retained
the full order. The full attested entrypoint passes Bash syntax validation.
No live rollback, boot entry, root mode or service was changed.

The physical validation protocol is now recorded in
[STEAMOS_HARDWARE_VALIDATION.md](STEAMOS_HARDWARE_VALIDATION.md). Its matrix
contains all 66 registered Real Toolkit actions across 33 UI components and
all 11 actions of the explicit alternative. Results remain pending: the
current host reports ID=arch, not SteamOS. The protocol includes source/package
installation, native-feature coexistence, each provider's lifecycle, real
recovery boot, readonly postconditions, peripheral behavior and removal of the
main app while guarded external workflows remain installed.

## Interrupted graphics installations and retained Vulkan selections

The alternative provider's guard previously looked only for a Real Toolkit
ICD manifest. An interrupted copy can leave libraries or other prefix contents
before the ICD is published; a removed prefix can also leave its active
VK_DRIVER_FILES selection. Both cases now count as a conflict requiring the
original provider's repair/removal. A dangling prefix symlink is preserved;
an empty prefix or a downloaded checkout alone does not establish ownership.

The Real Toolkit guard now parses exported/whitespace assignment forms as
well as ordinary VK_DRIVER_FILES assignments. Its upstream rollback deletes
every matching line, so it must not proceed over a foreign or unparseable
selection. Stock 32-bit fallback is allowed alongside the Toolkit selection,
but a stock-only custom selection and a path escaping the Toolkit prefix via
parent traversal are protected. Comment-only references do not count as an
active setting. These probes remain read-only.

49 focused graphics ownership, alternative provider, standalone runtime and
native panel tests pass, including partial-library-only copies, dangling
links, stale environment selections and malformed/foreign assignments. Lint,
generated-runtime freshness, installation-source validation and diff checks
pass. This is evidence of refusal and preservation against fixtures, not
evidence of real mixed-provider cleanup or graphics-driver behavior.

## Interruptions wait for upstream before root restoration

Replaced the subprocess.run action wait with an explicit interactive child
wait and a scoped SIGINT/SIGTERM/SIGHUP relay. Python's ordinary interrupted
subprocess wait can unwind before the child is confirmed stopped, which could
start filesystem-mode restoration while upstream is still running. The new
launcher keeps the inherited terminal process group, forwards signals sent
only to the parent, waits for the top-level upstream process to finish, and
keeps the parent handlers installed through root-mode restoration. Previous
handlers are restored afterward. Cancellation returns 128 + signal; a child
terminated by a signal is normalized to the same shell convention. Unexpected
Python wait failures terminate and reap the child before propagating.

Six new signal/process tests include real fixture parent/child processes for
SIGINT, SIGTERM and SIGHUP. The fixture child records the signal and deliberately
waits for release: the parent remains alive and the simulated root remains
writable until the child finishes, then the initial mode is restored and the
expected cancellation status is returned. Other tests check prior-handler
restoration, exception cleanup order and signal exit codes. These tests use
only temporary files and ordinary child processes, not real root-mode changes.

This does not certify SIGKILL, power loss, detached descendant behavior or
SteamOS terminal/session teardown. Physical interruption and recovery tests
remain in the hardware protocol; the launcher does not claim a process-tree
or cgroup kill guarantee from a top-level child wait.

The combined adapter, runtime, recovery, signal and standalone packaging run
passes 141 tests. Generated runtime, lint, source validation and diff checks
also pass after this change.

## One Vulkan interpretation and primary UI routes during inventory refresh

The passive state probe and the conflict checker now share the same ordered
Vulkan assignment parser. Exported/whitespace forms are recognized in both.
A malformed or empty later assignment no longer reuses an earlier valid
selection and falsely reports it configured. A partial prefix without an ICD
is incomplete, as is a dangling Toolkit selection; an unrelated Vulkan
selection alone no longer establishes a Toolkit installation. The probe still
does not infer live graphics activation from configuration files.

Removed a separate repository readiness heuristic that accepted an ICD file
name plus a matching environment substring, including comments. The historical
presenter field now derives from the validated provider probe (ICD, ELF
library and effective assignment), preserving its public shape without
duplicating weaker detection.

The preparation card no longer falls back to the old two-stage SteamOS UI
when inventory is absent or refreshing. All four primary actions remain
explicit Real Toolkit install/check/Proton/revert routes, independent of the
former backend's kernel-ready flag. Readiness labels now distinguish unknown,
incomplete, configured and absent graphics; configured does not say active.
The keyboardspecialist index remains the explicit alternative.

Focused tests cover ordered invalid assignments, partial/stale installs,
repository readiness despite misleading old artifacts, primary UI routing
without inventory, and translated state labels. No driver, service or boot
configuration was changed by this verification.

The expanded 44-file SteamOS/provider/UI/packaging regression run passes 554
tests and 10 subtests after these changes. Source validation and generated
runtime freshness also pass. This remains software/fixture evidence; physical
SteamOS boot, graphics and peripheral validation is still outstanding.

## GPU dependency dialog uses the same primary provider policy

The GPU page's dependency dialog still presented the former numbered kernel /
Mesa sequence and gated Mesa on the old provider's kernel-ready field. Its
shared presenter could also label configured files as live async compute.
The SteamOS presenter now reads only the Real Toolkit graphics state and
returns unknown / incomplete / configured / not installed, without asserting
live activation. Old-provider flags cannot override that primary presentation;
the explicit alternative retains its own controls and status.

The GPU dialog now dispatches explicit Real Toolkit combined-install, verify
and combined-revert actions without the old kernel gate. Its project link and
reviewed version/revision now refer to the actual pinned Real Toolkit, not
the generic Fedora reference. The preparation card uses this same presenter
instead of duplicating the status mapping. A concise instruction is translated
in all 30 catalogs and registered in the interface catalog.

New widget tests click each real button with both old-kernel-ready flag values
and verify the emitted provider-specific action, enabled state, exact reviewed
metadata and project link. Presenter tests verify configured does not mean
async compute is active and stale alternative flags do not change the primary
state. A Spanish offscreen Qt rendering was inspected at 800 px: state and all
four actions fit without the old numbered steps.

The expanded 45-file run passes 568 tests and 10 subtests, including complete
locale-catalog validation. Lint, source validation and diff checks pass.
This verification does not perform a physical SteamOS installation or boot.

## VA-API ownership in both directions

The reviewed Toolkit installs its video driver under /var/lib/bc250 and
activates it through 99-bc250-vaapi.conf and zz-bc250-vaapi.sh. Control Center's
native driver instead uses /var/lib/bc250-control-center/vaapi and its own
marked environment/profile/Xsession files. Distinct runtime paths alone do
not provide coexistence: both set LIBVA_DRIVER_NAME / LIBVA_DRIVERS_PATH and
the Toolkit's later environment file can hide the native driver used by
streaming and recording applications.

Added native video ownership to the component checker and bulk preflight;
both Toolkit video install and revert are guarded (33 wrapped functions in
the attested entrypoint). Its native-style row identifies the existing Control
Center owner and disables only overlapping video/bulk operations; graphics,
status and component selection remain available.

In the other direction, native VA-API activation now recognizes both Toolkit
environment/profile files. Its existing foreign-provider preflight also runs
before 32-bit installation and Flatpak activation, not only the 64-bit
installer. A foreign activation is no longer shown as our active driver merely
because LIBVA_DRIVER_NAME also says bc250. If both copies exist, native removal
remains available while further 32-bit/Flatpak activation is not offered.
The native driver's runtime, shaders, codecs and probe protocol are unchanged.

215 focused native-video, provider guard, adapter, panel and standalone-runtime
tests pass. They include shell refusal without writes, both foreign activation
paths, preservation of configured native files, bulk/direct protection, and
the mixed-installation UI. The actual attested upstream entrypoint adapts and
passes Bash syntax with all 33 wrappers. Lint, source validation, generated
runtime freshness and diff checks pass. No real video installation, codec
operation, Flatpak override or streaming session was changed or tested here.

## Integrated launcher lifecycle against a fixture source archive

Added orchestration tests that run the actual download digest verifier,
snapshot adapter, guard-runtime cache, workspace refresh, flock, interactive
dispatcher and Bash child together. The fixture replaces only the privileged
identity, protected storage boundary, hardware and remote response; its safe
component writes a temporary trace and exits 23. No actual upstream installer
or privileged host change is executed by this test.

The integrated lifecycle proves initial preparation and dispatch, AUTO=0,
canonical user identity, original child exit status, reuse of the verified
archive, replacement of locally altered provider source, preservation of build
outputs, and removal of temporary verification trees. A second flock holder
prevents download/cache/child execution. A corrupted download cannot publish
or execute a workspace and releases the lock for a successful retry.

The identity check is now a separate boundary that still runs after allowlist
validation and before preparation. It uses the standard-library os-release
parser rather than ad hoc quote stripping, requires ID=steamos (not merely
ID_LIKE), resolves the invoking user by UID and retains the BC-250 hardware
check. Boundary tests cover non-root invocation, missing desktop UID,
non-SteamOS host and canonical UID lookup/hardware validation. This fixture
identity is not evidence of actual sudo or physical SteamOS behavior.

38 integrated launch, runtime, real fixture signal and standalone packaging
tests pass. Lint, generated runtime, source validation and diff checks pass.

## Proton completeness and root-menu documentation options

The Proton probe previously accepted the Toolkit marker plus a VDF alone.
It now also requires a present, executable proton launcher for each recorded
variant. A complete variant cannot hide another incomplete variant or malformed
marker record. Complete tool names remain available in the result, but the
overall state is incomplete until every recorded variant satisfies these
minimum installation checks. This is not a game-launch or FSR4 test. The
preparation card now shows partial Proton installations as incomplete instead
of treating them as an optional absent component.

Root-menu coverage is now checked option by option: the seven operational
entries map to explicit native actions; Help maps to the existing unprivileged
project link; Changelog maps to a new What's new entry in the management row's
More menu; Exit remains native close/return and the upstream menus' original
exit handling. This replaces the inaccurate test assumption that the manual
installer menu was the parent of the entire root menu. The 109 inventory
entries and all 66 operational actions remain represented.

The changelog link targets CHANGELOG.md at the integrated immutable revision
(the pinned raw file returned HTTP 200 during review). It follows a closed
documentation route, opens through the desktop and does not launch sudo or
the Toolkit. Existing What's new translations are reused. UI tests exercise
the actual More action and routing, while documentation tests verify the
resolved URL. Proton tests cover VDF-only copies, non-executable launchers,
partial multi-variant installation and the visible incomplete state.

64 focused inventory, provider-state, documentation, native panel and isolated
packaging tests pass. No real Proton, Steam library or game was executed or
changed by these checks.

## Whole attested archive and actual Decky refusal paths

Re-downloaded the complete pinned archive into the development cache and
verified its expected SHA-256 and 127483692-byte size. The current adapter
prepared all 3790 files, found exactly the seven inventoried external projects,
adapted both attested Decky payloads and generated matching provider metadata.
All 52 bundled shell scripts passed bash -n; the two adapted Python payloads
compile. No shell installer was executed by this syntax validation.

Also evaluated the actual attested Decky Python files with a stub Decky import,
temporary configuration paths and a temporary checker returning 79. The four
real API methods (mode/save/select/delete) used their real async _run method
and refused before creating configuration. The real adapted low-level
write_fan refused before PWM access. Only the temporary checker file remained.
This strengthens the earlier mock evidence; it is not a loaded Decky session
or fan hardware test.

Added [validate-steamos-toolkit-source.py](../scripts/qa/validate-steamos-toolkit-source.py)
to reproduce archive verification, preparation, external inventory matching,
all bundled shell syntax checks and adapted Python compilation without a
network call or installer execution. The JSON report includes revision,
archive digest, adapter-module digests, file counts and checked script paths.
A bad archive returns failure and replaces any stale passing report with a
failure result. The actual archived source passes the new tool; lint and
diff checks pass. The local evidence report is under the development cache,
not a claim that installation or SteamOS boot validation has completed.

## Kernel-only provider ownership and interrupted rollback

Compared the actual Real Toolkit install/rollback scripts with the pinned
alternative e1563f2051727702a000b6ff6f6c524e2792aa21. Both write the same
updates/amdgpu.ko.zst path. Real Toolkit writes hash-only audio/metrics markers;
the current alternative adds its composition tag and a separate
.bc250-gfx1013-fix marker. Alternative rollback keeps its markers until
initramfs regeneration succeeds, so a missing on-disk module is not sufficient
to consider an interrupted rollback complete.

The primary graphics guard now rejects alternative kernel markers even when
no Mesa was installed, including the interrupted-rollback state. It protects
an existing native high-OC telemetry override while its actual module remains;
a stale telemetry marker or unused .old backup alone does not block migration.
The alternative guard does not silently adopt shared hash-only/ambiguous
legacy markers; its own reviewed tagged markers remain repairable. The
explicit current-kernel stock rollback remains available through its existing
protected backend and ownership verification, without adopting legacy bytes
or removing other kernels.

Individual graphics checks inspect the running kernel. Bulk install/recovery
checks inspect all kernels because emergency recovery can remove overrides
across installed kernels. Broken marker links and unsafe release arguments
fail closed. The installed checker passes this scope explicitly; source
checkouts alone still do not prove an installation.

Tests cover kernel-only installs, both marker formats, interrupted rollback,
native OC override/stale marker distinction, other-kernel isolation, bulk
scope, marker links, own-provider repair and installed checker dispatch. This
does not prove boot recovery or patch compatibility on physical SteamOS.

91 focused ownership, alternative, packaged checker, recovery, native backend
and telemetry tests pass. Lint, source validation, runtime freshness and diff
checks pass. No installed kernel/module/initramfs was changed.

## keyboardspecialist alternative: e1563f2 (v0.30.0) → 6aee553 (v0.40.0)

Reviewed `e1563f2..6aee553` (21 commits, 2026-10-02 → 2026-11-17) for the
members Control Center stages and runs. Unchanged: the kernel patches,
`rollback.sh`, `cleanup-other-slot.sh`, `mkinitcpio-compat.sh`,
`check-module.sh`, `ensure-build-prereqs.sh`, `clean.sh`, `prepare-kernel.sh`,
the `patch-driver.sh status` and `boot-config.sh` texts, the GFX1013 commit
`d3e6dc06` (legacy `b66203e`) and the `smu-8core-metrics-r1` marker tag.

Changed and adapted:

* `fetch-sources.sh` no longer holds `DEP_REPOS=(extra-main core-main)`; it
  calls the new `fetch-build-deps.sh`, which takes the extra/core pair from
  `pacman-conf --repo-list`, verifies package SHA-256s against the repository
  metadata, and publishes the private cache only after `build-env.sh` runs its
  tools, Python extension imports (`math`, the GLIBC_2.44 case), Perl and C
  headers. Control Center's adapter, whose anchors are gone, is removed; the
  build calls `fetch-build-deps.sh` first (so a mismatch stops before the kernel
  download and keeps the BUILD-001 marker), then `fetch-sources.sh` and
  `build.sh` unchanged, and deletes the old `*-bc250cc.sh` copies and
  `deps-bc250cc-*` cache.
* `bc250-mesh-shader.sh` builds Mesa 26.3.0 with DirectMesh 1.4 (global,
  opt-out `RADV_DIRECTMESH=0`), writes profile
  `directmesh-1.4-mesa-26.3-fsr4-v7` and applies
  `bc250-mesa-patches/libdrm-2.4.134-wrap.patch` from next to itself, which is
  now staged. Its CLI (`setup`, `status-json`, `uninstall`,
  `uninstall --fsr4-legacy`), paths and manifest layouts are unchanged; the
  status JSON adds `directMeshVersion`, now shown by the status report.
* Entrypoints source `../scripts/feature-tracking.sh` when it exists (v0.37
  "automatic tracking"). It is not adopted: `scripts/` is not staged and the
  guard refuses a stage containing it, so the hooks are skipped exactly as
  upstream does when the file is missing.

Installations made by Control Center 1.22.x (branch `main`, pin `e1563f2`)
remain supported: read-only checks and the stock-module restore accept the
complete protected copy that release staged (`LEGACY_STAGES`), with the same
root-ownership, permission and no-link checks and a note naming v0.30.0;
install, update and removal stage v0.40.0 first. Its RADV manifest (profile
`production-fsr4-v4`) is "installed, update available", and the status report
names it an earlier release where v0.40's `status-json` says "invalid".
Copies staged before `e1563f2` (v0.21.2, `1f4f326`) have a different
`rollback.sh` and must be prepared again.

Not adopted: upstream's interactive toolkit menus, tracking/targeted recovery,
and the v0.31-v0.40 components Control Center does not expose (TTM, swap,
Wi-Fi backend lock, Decky). Checked against the real v0.40.0 tree with a
read-only structural script (members and modes, constants, CLI verbs, status
texts, kernel bases, `bash -n` of every staged script) and on a SteamOS 3.9.5 /
7.2.7 host without privileges. No build, install or reboot was performed.
