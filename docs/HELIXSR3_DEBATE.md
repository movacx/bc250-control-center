# HelixSR 3.x support: planning debate

Participants: Claude (planning, UI design, review), Codex (backend, translations,
tests). Branch: `desarrollo/bc250-control-center` only, never `main`. Only the
HelixSR module's tests are run, never the full suite. UI changes wait for the
user's approval of a mockup.

## Facts (checked 2026-11-09)

- Latest release: **v3.3.0** (2026-11-08, stable). `HelixSR-3.3.0.zip`
  SHA-256 `30838854b545d31891e50075b929b2ab03512cece95b453d98dc2fc620135eaf`
  (upstream `SHA256SUMS.txt`). 3.0.0, 3.2.0, 3.2.1 are pre-releases; 3.1.0 stable.
- The app pins `HELIXSR_TAG = "v2.0.0"` and refuses majors above
  `SUPPORTED_MAJOR = 2` ("new package layout"), so 3.x is never offered.
- 3.x layout:
  - `HelixSR/helixsr.dll` + `HelixSR/helixsr.ini` (HLX DLSS; the setup builds
    the network into this DLL). Was `HelixSR-fsrfg/amd_fidelityfx_dx12.dll`.
  - `HLX-FSR4/amd_fidelityfx_upscaler_dx12.dll`: HLX FSR 4, **ships built**,
    the FSR 3.1 drop-in (`fsr` way).
  - `setup/preset-k/` (optional Preset K, `--preset-k`), `--vulkan` (optional
    native Vulkan kernels).
  - `helixsr-scaler/` = HelixSR Scaler 2.3.0 (OptiScaler fork, GPL-3.0).
  - **No HelixSR frame generation** (`setup/fg` gone).
- `setup/helixsr_bridge.py` = the backend of upstream's own HelixSR Desktop
  (Tauri app; the .deb ships the same bridge). Its command table is identical
  in 2.0.0 and 3.3.0: `status, games, install, remove, scaler-fg,
  reset-settings, settings-get, settings-set, log, rollback`; ways `scaler`
  and `fsr`. Protocol 1, one JSON object per call.
  - `status` on a fresh 3.3.0: `version 3.3.0, network_ready false,
    fg_available false, hlx_ready true, k_available true, k_ready false`.
  - game JSON: `id, name, folder, inputs, ways, recommended, anticheat,
    installed, version, settings_path, log_path, exe_folder, scaler_version,
    scaler_dll, scaler_layout, launch_options, previous, ...`.
  - `install --game DIR --way scaler|fsr|auto [--scaler DIR --scaler-version V]`;
    `fsr` on 3.x needs `hlx_ready`, not the network.
  - It recognises installs of earlier layouts and moves them on update.
- `helixsr-setup.sh` flags: `[GAME_FOLDER].. --dlss FILE --rebuild
  --preset-k --vulkan --yes --no-fg`. The app already runs it with
  `</dev/null` and `--dlss` (verified local or downloaded DLSS 310.7.0).

## Round 1 — Claude's plan

Principle (user's): use upstream's tested path. For 3.x everything a game
gets goes through the bridge, as HelixSR Desktop does; the app is only the UI.
2.x keeps working exactly as today.

Backend (`src/bc250cc/infrastructure/helixsr.py`, Codex):
1. `HELIXSR_REVIEWED["v3.3.0"]` with the archive SHA-256 above (and the
   digests the module records for the DLL, if any still make sense);
   `HELIXSR_TAG = "v3.3.0"`; `SUPPORTED_MAJOR = 3`.
2. Layout by version: 3.x DLL folder `HelixSR/`, `helixsr.dll`. Readiness from
   bridge `status` (`network_ready`, `hlx_ready`, `k_available`, `k_ready`,
   `fg_available`), not from file sniffing.
3. Setup: same `_setup_block`, plus optional `--preset-k` / `--vulkan` from
   the UI; frame-generation steps skipped when `fg_available` is false.
4. Per game on 3.x: install / update / switch way / remove / rollback /
   settings via `_run_bridge` (`--way fsr` = HLX FSR 4 drop-in, `--way scaler`
   with `--scaler <release>/helixsr-scaler --scaler-version <from
   HelixSR-Scaler-package.txt>`). The app's own native DLL copy path is not
   used for 3.x. Records kept so the game matrix and "Update all" still work.
5. Settings card: on 3.x write through `settings-set` per game; offer only
   keys 3.x reads (`Upscaling.Int8`, `Upscaling.NetworkResolution`,
   `Sharpening.*`, `Compatibility.WaveSize`, `Log.Enabled`).
6. Migration: a game with a 2.x install shows "Update"; the bridge moves it.

UI (Claude designs, mockup first): Upscaling tab keeps its layout. Per game
the two ways ("DLSS · HelixSR Scaler", "AMD FSR · HLX FSR 4"); "Build frame
generation" hidden on 3.x; "Build network files" gets Preset K / Vulkan
options.

Translations, `error_origins.json`, diagnostics patterns: Codex.

Open questions for Codex:
- a. Which parts of `helixsr.py` hard-code the 2.x layout (DLL path, embed
  footer check, native install/remove/update, `_supported_layout`, FG)?
  List functions that must branch on major 3.
- b. Is routing *native* (fsr way) installs through the bridge for 3.x safe
  with the app's existing per-game records (`_scaler_records`, game
  matrix)? What record changes are needed?
- c. The setup's embedded-network check (`HELIXSR_EMBED_MAGIC` footer) — does
  3.x still append the network the same way? If not, use `status`.
- d. HelixSR Scaler version pairing (`check_scaler_pairing`): where does the
  app read the scaler version for 3.x?
- e. Proposed file split and order of work; tests to add/update.
## Round 1 — Codex

**The bridge is the right 3.x installation path, but the plan needs separate readiness and settings contracts for each way.** In particular, a fresh 3.3.0 release can offer HLX FSR 4 before the DLSS network is built.

**a. Branch points.** In [helixsr.py](/home/movacx/Documentos/GitHub/bc250-control-center/src/bc250cc/infrastructure/helixsr.py:196):

- `_supported_layout` (196), `helixsr_dll_folder` (314), `helixsr_state` (1226), and `build_helixsr_install_command` (1958) assume the existing layout and DLL identity. Branch the DLL filename as well as its folder; preserve archive and released-DLL verification.
- `_setup_block` (1841) selects the old build folder, FG arguments and post-build footer target. `build_helixsr_network_command` (2047) needs build options; `build_helixsr_fg_command` (2682) and `helixsr_fg_ready` (2384) need capability gating.
- `install_helixsr_game` (2160), `remove_helixsr_game` (2230), `update_helixsr_game` (2291), `update_all_helixsr_games` (2621), `helixsr_games` (722), and `save_helixsr_settings` (1702) assume app-managed native files or a network requirement. Route 3.x bridge-managed games by recorded ownership and way, including removal after changing the selected release.
- `install_helixsr_optiscaler` (1106) and its update/remove path are a separate existing integration. Do not silently replace it with HelixSR Scaler or assume the bridge can safely migrate the app’s OptiScaler Client records.
- Scaler functions at 2374–2667 also need capability, way, migration and version handling. `_refuse_native_game` and `_refuse_other_helixsr` currently prevent the proposed switch.

**b. Records and migration.** Routing new FSR installs through the bridge is feasible, but storing them unchanged in `_scaler_records` is unsafe: `_scaler_state` (2422), `_scaler_result` (2512), scaler rows and removal assume Scaler artifacts. Native `_records` instead require `files`, backup paths and digest checks. Neither schema describes both.

Add a bridge-owned record with stable app ID, game root, `way`, installed release, previous version, and bridge-reported paths, layout, Scaler version and launch options. Derive state from bridge inspection, reconcile missing/restored files, and ensure each game appears once in the matrix and bulk update. Commit record changes only after bridge success; retain enough information to recover from a bridge success followed by record-write failure.

Challenge the blanket migration promise: upstream `cmd_install` (bridge line 1478) recognizes its own detected layouts, but app-managed 2.x native installs have different records and backups. Verify detection, original backup preservation, multiple FSR targets, switch, rollback and removal using fixtures before offering “Update.” The bridge drops previous snapshots when switching ways (lines 1509–1531), so switching is **not** a reversible version rollback. Also retain the app’s running-game and conflicting-OptiScaler protections.

**c. Footer.** Yes: upstream `helixsr_setup.py` `embed` (247) still writes `[DLL][weights][pak][HXSRNET1][three u64s]`; `network_sizes` (235) validates sizes and format. The DLL is now `HelixSR/helixsr.dll`. Prefer bridge `status` for readiness, while retaining version-appropriate digest verification. The app’s `_embedded_size` (365) is less strict than upstream’s format and size validation.

**d. Scaler pairing.** Claude’s proposed source is incorrect: `HelixSR-Scaler-package.txt` is a **file manifest**, not a version file. Upstream `scaler_pkg_version` (bridge 751) reads the version supplied via `--scaler-version`, otherwise searches `OptiScaler.dll` for `HelixSR Scaler vX.Y.Z`. `check_scaler_pairing` (766) requires at least 2.0.0 for the NGX layout when a version is known. Extract and validate the bundled DLL version, pass it explicitly, and expose unknown as unknown—not a fabricated version. Test the pairing and unknown-version behavior.

**Settings challenge.** Upstream `SETTINGS` (bridge 70) accepts only four sharpening/wave-size keys; `check_value` (1433) rejects `Upscaling.Int8`, `NetworkResolution` and `Log.Enabled`. For Scaler, `settings-set` targets `OptiScaler.ini` and accepts only `SCALER_SETTINGS` (77, 1214), not the HelixSR keys Claude lists. The FSR way installs HLX, whose installer removes its own old `helixsr.ini` (`helixsr_games.py:1149`); do not present HelixSR DLSS settings as effective for that way. Scope the UI to settings the bridge actually supports per installed way; investigate any missing controls separately.

**Backend/UI contract.** Extend `helixsr_state()` with `layout`, `bridge_status`/`status_error`, `hlx_ready`, `fg_available`, `k_available`, `k_ready`, and `scaler_version`. Keep `network_ready` and `fg_ready` distinct. Give each game `installed_way`, `available_ways`, `way_ready`, `previous_version`, and per-way `settings_supported`; include capability/error details rather than turning a bridge failure into “not ready.” Preserve existing keys during transition. Add explicit install/switch/rollback actions and build options to [gestionar_helixsr](/home/movacx/Documentos/GitHub/bc250-control-center/src/bc250cc/infrastructure/dependencias_repository.py:622). Gate each action independently: [preparation_render.py:527](/home/movacx/Documentos/GitHub/bc250-control-center/frontends/desktop/components/preparation_render.py:527) and :733 currently gate the whole experience on `network_ready`. Confirm `--rebuild` semantics for adding Vulkan to an already-built network.

**e. Order and tests.** First isolate release/layout/status and bridge protocol helpers; then implement bridge-owned records and reconciliation, followed by per-way operations, migration and settings, repository actions, translations and diagnostics. UI work follows the approved mockup, as requested in the debate.

Update the major-layout rejection test to reject an unsupported future major. Add focused HelixSR tests for verified 3.x installation, status failures, FSR-ready/network-missing, Scaler pairing, setup flags, both ways’ lifecycle and rollback, legacy migration and backup safety, conflicts, partial failures, settings restrictions, and bulk update without double counting. Extend the existing dashboard tests for independent gates and capability visibility. Run only the HelixSR module tests specified in the debate. No files were edited and no release scripts or tests were run.

## Round 2 — Claude (decisions, accepted from Codex)

1. Recommended release **v3.3.0** (`HELIXSR_TAG`), `SUPPORTED_MAJOR = 3`;
   2.0.0 and older stay selectable. A future major 4 is still refused.
2. Readiness per way from bridge `status`: the `fsr` way (HLX FSR 4) needs
   `hlx_ready` only; the `scaler` way (HLX DLSS) needs `network_ready`. A
   bridge failure is reported as `status_error`, never as "not ready".
3. New bridge-owned record (separate file, e.g. `bridge_games.json`): app id,
   game root, way, release, version, scaler version, layout, launch options,
   previous version. Written only after bridge success. Existing native and
   Scaler records keep their schema for 2.x.
4. Migration of an **app-managed 2.x native** game: the app's own remove
   (restores the original DLL from its backup) first, then bridge install;
   never the bridge on top of app files. App-managed 2.x **Scaler** games
   (already bridge files): bridge install `--way scaler` updates in place.
   Switching way is not a rollback (the bridge drops previous snapshots);
   the UI says so.
5. Scaler version: read `HelixSR Scaler vX.Y.Z` from the bundled
   `helixsr-scaler/OptiScaler.dll`, pass `--scaler-version`; unknown stays
   unknown.
6. Settings: only what the bridge accepts per way. 3.x Scaler games:
   `HelixSR.WaveSize` (QuickFlow is FG-only, hidden on 3.x). FSR way on 3.x:
   none from the HelixSR card (HLX FSR 4 has its own ini); the card says
   so. 2.x unchanged.
7. Frame generation hidden when `fg_available` is false.
8. Build options: `preset_k`, `vulkan`, `rebuild` passed to the setup.
   Adding Vulkan to a built network needs `--rebuild` (upstream README).
9. Keep running-game and conflicting-OptiScaler protections.

### State contract (backend -> UI)

`helixsr_state()` keeps every existing key and adds:

```
layout: "2" | "3"                      # major of the installed release
status_error: str                      # bridge status failure, "" if fine
capabilities: {fg: bool, preset_k: bool, vulkan: bool}
ready: {network: bool, hlx: bool, preset_k: bool, fg: bool}
scaler_version: str                    # "" when unknown
bridge_games: [                        # 3.x games (bridge-owned), one per game
  {appid, name, folder, ways: ["scaler","fsr"], recommended,
   installed_way: "scaler"|"fsr"|None, version, previous_version,
   way_ready: {scaler: bool, fsr: bool}, launch_options, managed_by:
   "bridge"|"app-2x"|"other", outdated: bool}
]
```

Repository actions (`gestionar_helixsr`, payload `helixsr_<action>`):
`bridge_install:<appid>:<way>`, `bridge_remove:<appid>`,
`bridge_rollback:<appid>`, `network:<opts>` with opts a comma list of
`preset_k`, `vulkan`, `rebuild` (empty = plain build). `update_all` covers
both 2.x and 3.x games.

### Ownership

- Codex: `src/bc250cc/infrastructure/helixsr.py`, `dependencias_repository.py`
  (`gestionar_helixsr`), `upscaler_releases.py`, backend tests
  (`tests/infrastructure/test_helixsr*.py`, new `test_helixsr3_bridge.py`),
  then translations (30 locale JSON), `error_origins.json`,
  `error_diagnostics.py` patterns.
- Claude: UI (`preparation_pages.py`, `preparation_render.py`,
  `dashboard_widgets.py` game matrix / settings card, `gpu_governor*.py`
  routing) and UI tests; final review.

## Round 3 — Status (2026-11-09)

Done, uncommitted on `desarrollo/bc250-control-center`:
- Codex: backend (3.3.0 reviewed, bridge status/games/install/remove/rollback,
  bridge records, migration, build options, Scaler version), diagnostics
  patterns, `error_origins.json`, bridge tests, translations (6 batches).
- Claude: Upscaling UI (matrix cells per way, HLX FSR 4 before the network,
  DLSS network / Preset K / Vulkan builds, FG hidden on 3.x, settings card
  reduced to HelixSR Scaler's group), bridge dialogs, UI tests; review fixes:
  symlink-safe folder matching, Steam DLL override for Scaler under another
  name, optional builds gated on the network.
- Module tests: 439 passed (HelixSR, HelixSR 3 UI, i18n, diagnostics,
  DirectMesh). Not run: full suite; a real install on a BC-250.

## Round 4 — Review and fixes (2026-11-09)

Codex reviewed three times; Claude fixed every finding:
- installed release stays in use when nothing was picked (no hidden games
  for 2.0 users); upgrade writes the pick only after the new release is in
  place, before the old one is removed;
- remove/rollback for legacy (native, Scaler) and unrecorded games;
  external installs show only Remove;
- bridge read timeouts and a 120 s games-scan cache, cleared by changes and
  by Find games; Steam shortcuts in the scan;
- saved Scaler WaveSize applied to new Scaler games (failure reported);
- legacy games always outdated, with the same way in the row and Update all;
- a `network:` dialog branch that had landed in the FSR4 handler, found by
  clicking every action on the real window.
Verified: real 3.3.0 bridge install/remove of HLX FSR 4 in a fake game
(original DLL restored byte for byte); 9/9 actions on the real window;
451 module tests. Not run: the real install script (blocked by the
permission system: it downloads and runs upstream's setup), a real game on a
BC-250, the full suite.
