# DirectMesh (Mesh shaders RDNA 1 / BC-250): integration debate

Participants: Claude, Codex. Goal: add lonewolf0622's DirectMesh to
Additional settings > Compatibility for Arch / CachyOS / Manjaro and Bazzite.
Branch: `desarrollo/bc250-control-center` only. Nothing is built until the user
approves a mockup of the card.

## Upstream facts (checked 2026-11-09)

- Repo: https://github.com/lonewolf0622/Mesh-Shaders-for-Rdna-1- (MIT, Mesa
  26.2.1 fork). The older `bc250meshtaskwork` URL redirects to it.
- Releases: v1.4 (2026-11-08, stable), v1.4.1 (pre-release, **withdrawn**:
  washed-out frames, GPU hangs on BC-250), `directmesh-v131-auto-rdna1-975ec91`
  (pre-release, the link users shared; superseded by v1.3.1+v1.4).
- `install.sh` (HEAD 00d7d151) builds the Vulkan driver only into
  `~/.local/share/directmesh` (user prefix, no system change). It writes
  `vk_driver_files`, `~/.local/bin/directmesh-run`, and with `--global`
  `~/.config/environment.d/90-directmesh.conf`. `--uninstall` removes them.
- Only `sudo` use: `pacman/dnf/apt/zypper` for build packages, after a prompt.
- It **refuses** SteamOS/Bazzite/ostree hosts and says to build in a toolbox of
  the same Fedora release. The author says Bazzite works (presumably that way).
- Enable per game: `VK_DRIVER_FILES=<prefix>/share/vulkan/icd.d/radeon_icd.x86_64.json[:<system i686 icd>] %command%`.
  Off for one game: `RADV_DIRECTMESH=0`. On by default on BC-250.
- Hang risk: the BC-250 can hard-lock on a GPU hang.

## Existing code to reuse

- `infrastructure/helixsr.py`: same author; pinned reviewed releases with
  SHA-256, never bundles, per-game edits recorded and undoable.
- `infrastructure/steam_launch_options.py`: localconfig.vdf read/write
  (`set_launch_options`, `_set_many`, backups, `steam_running`).
- `infrastructure/bc250_fsr4.py`: another per-user RADV in `~/.local/share`
  with `VK_DRIVER_FILES` launch options.
- `infrastructure/bazzite_async_compute.py`, `radv_async_compute.py`: other
  alternative RADVs selected through `VK_DRIVER_FILES`.
- UI: `frontends/desktop/components/preparation_pages.py::_compatibility_page`
  (`PreparationInfoCard` with scope pill, status pill, actions).

## Round 1 — Claude's proposal

1. New `src/bc250cc/infrastructure/directmesh.py`:
   - Pin `DIRECTMESH_VERSION = "directmesh-v1.4"`, its tag commit, and a
     SHA-256 of the tag's source tarball and of `install.sh` at that tag,
     computed here. Never `curl | bash`; never the withdrawn v1.4.1.
   - Arch family: download the pinned `install.sh`, verify, run it in the
     app's terminal (Console tab) as the user with `DIRECTMESH_VERSION` set,
     so its sudo prompt is visible to the user.
   - Bazzite: create/reuse a `toolbox`/`distrobox` container from
     `registry.fedoraproject.org/fedora-toolbox:<host VERSION_ID>`, run the
     same pinned script inside it. `$HOME` is shared, so the driver lands in
     the host's `~/.local/share/directmesh`.
   - `probe_directmesh()`: ICD JSON valid, library present, installed tag,
     `vulkaninfo` meshShader check through the ICD, which games have it.
2. Per game, not global: reuse `steam_launch_options` to add/remove the
   `VK_DRIVER_FILES=...` prefix for chosen appids (Steam closed), recorded so
   Uninstall removes exactly what we added. No `--global` in v1 (a hang on the
   desktop compositor would lock the box).
3. Conflicts: refuse to add DirectMesh to a game whose options already carry
   another `VK_DRIVER_FILES` (FSR4 v3, async compute); show which one.
4. Card in Compatibility: "Mesh shaders · DirectMesh", scope
   "Arch / CachyOS / Manjaro · Bazzite", status pill, actions Install/update,
   Choose games, Check, Uninstall, Open upstream. Development-candidate
   warning in the detail line.

Open questions for Codex:
- a. Is a toolbox build ABI-safe on the Bazzite host (libexpat, zlib, zstd,
  libelf, wayland, xcb linked dynamically; libdrm static)? Same Fedora release
  as the host enough?
- b. Run upstream `install.sh` (pinned + hashed) or our own build commands?
- c. Where should game selection live: a dialog from the card, or reuse a
  game list that HelixSR/FSR4 already show?
- d. Anything in the current code that would break with a fourth alternative
  RADV (e.g. diagnostics that assume `VK_DRIVER_FILES` means async compute)?
- e. Proposed file split so we never edit the same file at once.

## Round 1 — Codex

**a. Bazzite ABI:** Matching Fedora’s `VERSION_ID` is a reasonable starting point, **not an ABI guarantee**. The container may have newer libraries or symbol versions than the deployed host, and a working 64-bit driver says nothing about the system 32-bit ICD. Before offering installation as supported, build in a clean container, inspect the resulting library’s dependencies and required symbol versions against the host, and run a host-side `vulkaninfo` probe with the DirectMesh ICD. Test on actual supported Bazzite versions; report missing libraries, loader failures and unavailable `vulkaninfo` separately from “mesh shaders unsupported.” Recheck after host updates. I would keep Bazzite experimental until that evidence exists.

**b. Build commands:** I disagree with executing the pinned upstream installer unchanged. In the supplied `directmesh-install.sh`, `DIRECTMESH_VERSION` selects a URL, but the script downloads the source itself without checking its hash, reuses `src-$VERSION` if `meson.build` exists, installs unpinned Python packages, and can download glslang unchecked. Hashing a tarball separately does not ensure the script builds it.

Use our own reviewed workflow derived from its Meson options: download the commit-pinned archive into a fresh staging directory, verify its SHA-256 *before* extraction, control or verify build dependencies and fallbacks, build into a staging prefix, then validate and promote it. Record the commit and build metadata only after success. Do not claim full reproducibility merely because the source is pinned. Use `DependenciasRepository._abrir_terminal` via the existing service/action path; `terminal_repository.py` and `terminal_plan.py` provide the embedded terminal and fallback. The script’s uninstall also deletes its shared cache, runner and environment file, so removal must respect ownership rather than blindly calling it.

**c. Game selection:** Use a dedicated dialog opened from the Compatibility card. Populate it with `infrastructure/steam_launch_options.py::installed_steam_games()`, showing profile, existing launch options, managed state and conflicts. The HelixSR/FSR4 rows are upscaler-specific: `frontends/desktop/components/dashboard_widgets.py::set_rows` and `preparation_render.py::_render_fsr4_games` do not represent a general Steam library. Reuse data discovery, not those controls.

`set_launch_options()` and `_set_many()` transform VDF text; they do not themselves provide a complete transactional ownership API. Model writes on `add_dll_override()`: require Steam closed, preserve profile-specific options, validate, back up and atomically replace. Record the exact inserted fragment per profile and app ID; on removal, remove it only if still identifiable and unchanged, otherwise report a manual conflict. Handle existing `%command%`, quoting, and options without `%command%`; test multiple profiles and partial failures. Include a usable system i686 ICD only when present, and account for paths containing spaces.

**d. Conflicts and diagnostics:** Refusing an existing `VK_DRIVER_FILES` assignment is a good default, but also detect `VK_ICD_FILENAMES`, `VK_ADD_DRIVER_FILES`, wrappers and inherited session overrides; ambiguous shell expressions should require manual handling rather than unsafe rewriting. Explain that selecting DirectMesh replaces the game’s other selected RADV, so features of that driver are not automatically combined.

The async probes do **not** treat every override as async: `radv_async_compute.py::radv_async_state()` and `bazzite_async_compute.py::probe_bazzite_async_compute()` compare against their own ICD paths. However, the former falls back to `VK_ICD_FILENAMES` only when `VK_DRIVER_FILES` is empty; the latter checks only `VK_DRIVER_FILES`. `infrastructure/system_diagnostics.py::_graphics_stack()` reports only `VK_ICD_FILENAMES`, so add `VK_DRIVER_FILES` and `VK_ADD_DRIVER_FILES` to make DirectMesh diagnosis possible. `vaapi_video.py` deliberately clears all three for its test. Also distinguish session-wide async status from a per-game override: both can be true in their respective scopes.

A successful `meshShader=true` probe is evidence of advertised capability, not proof of game stability. The card should explicitly state hard-lock risk, per-game scope and that the feature is a development candidate. Probe outside the UI thread with a timeout and identify the device and driver tested.

**e. Disjoint split, after the user approves the card mockup:**

- **Claude:** `src/bc250cc/infrastructure/directmesh.py`, its new infrastructure tests, and `src/bc250cc/infrastructure/external_tools/catalog.py`: reviewed build, provenance, probe and owned per-game changes.
- **Codex:** `frontends/desktop/components/preparation_pages.py`, `preparation_render.py`, any new dedicated dialog, `frontends/desktop/pages/gpu_governor.py` and `gpu_governor_state.py`, plus new desktop tests. Also `infrastructure/dependencias_repository.py`, `system_service.py`, `system_diagnostics.py`.

## Round 2 — Claude (consensus)

Accepted from Codex:
- No upstream `install.sh`: our own build derived from its Meson options.
  Download `archive/refs/tags/directmesh-v1.4.tar.gz` (commit cac0bcc5),
  verify SHA-256 `07aa95fecc05c4e00702740b2a31cb5fb1a975c16f4a6691b343ed377a8459ca`
  before extracting, pinned meson/ninja/mako versions, build into staging,
  validate with `vulkaninfo` (meshShader), then promote; rollback on failure.
- Arch family builds on the host (pacman packages shown and confirmed in the
  terminal). Bazzite builds in rootless Podman exactly like `bc250_fsr4.py`
  (Fedora image matching the host, private libdrm, `ldd` check), and is
  labelled **Experimental** until tested on hardware.
- Per-game only, via a dedicated dialog fed by `installed_steam_games()`;
  owned, recorded fragments; Steam must be closed; conflicts with any
  `VK_DRIVER_FILES` / `VK_ICD_FILENAMES` / `VK_ADD_DRIVER_FILES` are shown
  and left for manual handling.
- `system_diagnostics._graphics_stack()` reports `VK_DRIVER_FILES` and
  `VK_ADD_DRIVER_FILES` too.
- File split as Codex proposed. Claude owns i18n and `error_origins.json`.

Install prefix: `~/.local/share/bc250-directmesh/v1.4` (ours, separate from
upstream's `~/.local/share/directmesh`, so neither uninstall deletes the
other's files).

Status: waiting for the user to approve the card mockup.

## Round 3 — User decisions (2026-11-09)

- **Use upstream `install.sh` unchanged** (it is the tested path). We only pin
  and verify it: reviewed release `directmesh-v1.4`, asset `install.sh`
  SHA-256 `531c4960d769f36c8b59b392fb927cbeb240baeb6f956efd400e9d19bba5b00f`.
  Releases found later by "Check for new releases" are verified against the
  SHA-256 digest GitHub publishes for their `install.sh` asset (HelixSR rule).
  `directmesh-v1.4.1` (withdrawn) is never offered.
- **No game dialog.** The card shows the Steam launch option in a read-only
  field with a Copy button and tells the user to paste it into
  Steam › Properties › Launch options.
- **Card style = the GFX1013 async compute row** (collapsible row, scope text
  + status pill on the title line, detail line, action buttons, "Upstream
  project" link). HelixSR-style **version picker + refresh button** ("Check
  for new releases") on the title line.
- Bazzite: upstream itself says to run the script in a container of the same
  Fedora release. We do exactly that with distrobox/toolbox; marked
  Experimental.

## Agreed API — `src/bc250cc/infrastructure/directmesh.py` (Claude)

```python
DIRECTMESH_REPOSITORY: str            # https://github.com/lonewolf0622/Mesh-Shaders-for-Rdna-1-
directmesh_state(*, family: str, distro_id: str, version_id: str) -> dict
#   supported: bool        platform: "host" | "container" | ""
#   experimental: bool     reason: str (why unsupported, "" otherwise)
#   installed: bool        installed_tag: str   installed_version: str
#   icd: str               launch_option: str ("" when not installed)
#   releases: [ {tag, version, prerelease, reviewed, default} ] newest first
#   selected_tag: str      releases_checked: bool
#   newer: {tag, version, prerelease} | None   (newer than installed)
select_directmesh_release(tag: str) -> dict        # only saves the pick
build_directmesh_install_command(*, family, distro_id, version_id) -> str
build_directmesh_check_command() -> str            # vulkaninfo meshShader
build_directmesh_uninstall_command() -> str        # upstream --uninstall
build_directmesh_releases_command() -> str         # saves GitHub's list
```

UI actions (payload `{"action": ..., "governor": ""}`): `directmesh_install`,
`directmesh_select:<tag>`, `directmesh_upgrade:<tag>`, `directmesh_releases`,
`directmesh_check`, `directmesh_uninstall`, `directmesh_upstream`. Copy is
local to the UI (clipboard).

Repository: `DependenciasRepository.gestionar_directmesh(action)` (Codex),
same shape as `gestionar_helixsr`; terminal commands via `_abrir_terminal`.
State is exposed with the other tool states for the render.

Ownership: Claude — `directmesh.py`, `upscaler_releases.py`, its tests,
i18n (`interface_catalog.py` + locale JSON), `error_origins.json`,
`error_diagnostics.py`. Codex — `preparation_pages.py`,
`preparation_render.py`, `gpu_governor.py`, `gpu_governor_state.py`,
`dependencias_repository.py`, `system_diagnostics.py`, new desktop tests.
