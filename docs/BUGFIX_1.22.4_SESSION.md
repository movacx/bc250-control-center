# Bugfix session 1.22.4 — shared channel

Participants: **Fable** (implements), **Claude** (coordinator, reviewer),
**Codex** (gpt-6-astra, reviewer), **Arbiter** (Sonnet 5.5 max, reviewer and
final word on disagreements). Owner approved the whole plan and the arbiter's
recommendations for every open decision (section 5), with creative freedom.

Plans: `~/Documentos/bc250-reports/PLAN_FINAL.md` (arbiter, **priority**),
`PROPUESTA_CLAUDE.md`, `PROPUESTA_CODEX.md` (+ `PROPUESTA_CODEX_terra.md`).
Evidence: `~/Documentos/bc250-reports/` (reports, triage), upstream clones in
`~/Documentos/bc250-upstreams/`.

Owner decisions taken (arbiter's recommendations):
- Non-BC-250 hardware: block hardware actions only on confirmed absence of
  PCI 1002:13fe; permanent banner + disabled hardware controls in the desktop;
  Mesa PPA on a foreign PC: warn, not block; HelixSR/FSR4/DirectMesh/CEC stay
  available.
- SteamOS #3: long writable window accepted, pending a real SteamOS check.
- New diagnostic codes per category: yes (with all 30 translations).
- CoolerControl layered: communicate `rpm-ostree uninstall coolercontrol`.
- Upstream suggestions: draft them in `docs/UPSTREAM_NOTES.md`, send nothing.

Rules: branch `desarrollo/bc250-control-center` only, never main; per batch
run only that module's tests + diagnostics coverage (>= 87 %) + i18n tests if
strings changed + regenerate `src/bc250cc/shared/error_origins.json`; never
the full suite; no pushes. Commits are made by Claude after each batch passes
review.

## Protocol change (owner, 2026-11-10) — save usage, never sit idle

- Only Fable and Claude remain as Claude sessions. **Codex (gpt-6-astra) is
  now the arbiter**: final word on reviews and disagreements.
- Fable runs autonomously: after each batch it runs the Codex review itself,
  applies required changes, re-runs the batch tests, commits the batch on
  `desarrollo/bc250-control-center` (never main, never push), and goes
  straight on to the next batch without waiting for Claude.

## Log

(Each entry: `### [who] batch — topic`, newest at the bottom.)

### [Fable] B1 — terminal stops reading helper numbers; catalog narrowed and extended (#1, #7, markers for #2/#12, origin fixes)

**What changed**

- `src/bc250cc/infrastructure/terminal_plan.py`: the numeric `case "$status"` table is gone. Only
  124 → TIMEOUT-001 and 127 → CMD-001 remain (`_SHELL_DEFINED_STATUSES`); everything else goes
  text rules → `first_error` (WORKFLOW-001) → GENERAL-001. Module docstring explains why.
- `src/bc250cc/shared/error_catalog.py`:
  - New codes: BUILD-003 (`compilation terminated.`, `collect2: error`, `ninja: build stopped`,
    `ld returned 1 exit status`, `] Error ` — make's own line; `]` is literal in POSIX ERE and the
    panel matches literals), RUNTIME-001 (`GLIBCXX_`, `CXXABI_`, `GLIBC_2.`, requires `not found`),
    IMMUTABLE-002 (`could not create directory`, `pacman database is still read-only`, requires
    `Read-only file system`), GPU-008 (`must be active before changing its voltage curve`, the text
    gpu_repository already raises), UPSCALE-002 (`has anti-cheat`, `anticheat-ok`, `EasyAntiCheat`),
    WINE-002 (`cannot execute: required file not found`, `cannot be executed here`, requires `wine`).
    Order: NET-001 → BUILD-003 → RUNTIME-001 (later wins in the terminal, so the library mismatch
    beats the generic build failure; BUILD-001 still wins on its SteamOS marker).
  - Narrowed: IMMUTABLE-001 loses `read-only protection` (gains `Failed to restore SteamOS
    read-only protection`); BUILD-001 loses `GLIBC_2.`; UPSTREAM-404 `requires="github.com"`.
  - Added markers: NET-001 (`Could not resolve host`, `Temporary failure in name resolution`,
    `nghttp2`, `FRAME_SIZE_ERROR`, `returned error: 5`, `Connection timed out`, `Operation timed
    out`), HELPER-001 (`to install the protected system setup helper`), HW-001 (`13fe was not
    found`, `13fe was not detected`, `13FE was not detected`, `expected PCI bus location`), PKG-004
    (`Packages not found`), BUSY-001 (`Another BC250 system setup change is running`).
  - AUTH-002 action drops "No hardware change was applied." (catalog + desktop + 30 locales).
  - `for_exit_status` docstring: known producers only. `HARDWARE_GATE_MESSAGE` constant for B4
    (included in `translatable_strings()`).
- `frontends/desktop/core/error_diagnostics.py`: mirror of the above; RUNTIME-001 rule placed right
  after UMR-001 (before anything that reads "not found"); IMMUTABLE-002 before PERM-001; BUILD-003
  before CMD-001; CMD-001 loses `make: \*\*\*`; GPU-001 loses `gpu-usage`; narrow CONFIG-001 rule
  (`duplicate (gpu-usage|gpu|frequency-range|dbus).<key> key`, `cannot overwrite a value`,
  `conflicting \[`) before GPU-001; IMMUTABLE-001 bare `rpm-ostree`/`ostree`/`immutable` replaced
  by failure-worded patterns; UPSTREAM-404 patterns all gated on `github.com`; NET-001 gains
  `requested url returned error: \d{3}`, `nghttp2`, `frame_size_error`; INTERNAL-001 takes the
  app's own "immutable tuple" invariants that IMMUTABLE-001 used to swallow. `_PREFIX_MARKER` now
  requires the marker to end in a letter/digit so `GLIBCXX_`/`CXXABI_` are not treated as helper
  prefixes.
- Origin fixes: `scripts/install-local.sh` prints `[ERROR]` lines and a new
  `explain_python_gui_runtime` names each failing probe (imports, CA certs, pip version, Qt SVG
  plugin), still `exit 2`; `src/bc250cc/infrastructure/system_setup.py` prints `ERROR: …` to stderr
  before `exit 69`.
- Regenerated `integrations/decky/bc250-quick-access/src/generated/error_catalog.json`
  (generate_contract.py). `error_origins.json` unchanged (no new functions in src/frontends).
- Locales: 19 new strings + AUTH-002 rewrite in all 30 files (6003 keys each), hand-written.

**Tests** (all with the scratchpad venv; never the full suite)

- New `tests/services/test_report_replay_2026_11.py`: real excerpts of R-bb33f44b, 79e92b51,
  53376560, 530bd5f6, cc0af5ae, 86b82fd2, 86d44da1, 410912eb, fc1cfbe2, a45942d4, 1aad1216,
  00516dc1, 506fdded, 64bcb05c, e20dd96d through `workflow_wrapper` with the real exit status, and
  through `diagnose_error` (plus c6ab33f2, 2942b02f, 2c5122d2, cbc5ba02). Negatives: the guard's
  `[INFO] Restoring…` line alone, `GLIBC_2.38` on Bazzite, mirror vs GitHub 404, duplicate TOML key,
  recovered DNS then compile failure, curl 23, signature failure, APT warnings before a lock.
- Rewritten: `test_error_catalog_contract::test_helper_statuses_resolve_to_their_diagnostic` →
  `test_a_silent_status_is_explained_only_when_the_shell_defines_it` (127/124 keep their code;
  22/51/43/2/3 → GENERAL-001) + `test_helper_statuses_still_resolve_for_the_helpers_callers`;
  `test_terminal_plan::test_wrapper_explains_configuration_exit_status` → 65 is GENERAL-001 in
  the terminal; `test_steamos_build_diagnostic` → bare GLIBC is RUNTIME-001, the STEAMOS marker
  keeps BUILD-001; `test_error_diagnostics` make/fatal-error lines → BUILD-003;
  `test_package_signature_diagnostic` 404 sample now names github.com; coverage EVIDENCE for
  UPSTREAM-404 names github.com and gains samples for the six new codes, HELPER-001, PKG-004,
  CONFIG-001, NET-001 (504, nghttp2), IMMUTABLE-001 (restore failure).
- Results: 365 passed (test_terminal_plan, test_error_catalog_contract,
  test_exit_status_means_one_thing, test_report_batch_2026_11, test_report_replay_2026_11,
  test_steamos_build_diagnostic, test_package_signature_diagnostic, tests/desktop/
  test_error_diagnostics.py, test_error_diagnostics_coverage.py, test_error_origins.py,
  tests/quick_access/test_quick_access_error_codes.py, tests/packaging/
  test_one_contract_for_every_process.py); tests/desktop/i18n/: 95 passed. Diagnostics coverage
  87.74 % (859/979; was 87.64 %, ratchet 87 %).

**Deviations / notes**

- The 2 strings of #6 (B10) and 2 of #8 (B6) are NOT added yet: their wording depends on the UI
  change itself, and with a single writer the "B1 owns the locales" rule no longer prevents any
  conflict. They go in with their batches (all 30 files each time).
- `for_marker` (helpers' callers) picks the last marker occurrence, so a text with a GLIBC line
  followed by make's `] Error N` resolves to BUILD-003 there; the terminal (catalog order) and the
  desktop (rule order) both give RUNTIME-001, which are the two surfaces that see such logs.
  Accepted rather than changing `for_marker`'s semantics.
- `requires` is one string per entry, so the arbiter's "`fatal error: ` + `No such file or
  directory`" pair became `compilation terminated.` (gcc prints it right after the fatal error);
  the desktop rule keeps the exact pair as a regex.
- R-53376560 (`systemctl status` exit 3) is GENERAL-001 in the terminal now — honest, not useful;
  B3 replaces the final `systemctl status` with is-active + journalctl and exit 1.
- PKG-003 still only knows the English "duplicate database entry" (R-3d3fb3a4 was Portuguese);
  `LANGUAGE=en` is exported since 1.22.x, so I left it.
- UPSTREAM_NOTES: nothing for B1.

### [Arbiter] B1 — verdict

**Verdict: CHANGES REQUIRED** (8 small, concrete changes, no redesign). Fable's B1 follows PLAN_FINAL for #1/#7 faithfully:
the numeric table is out of the terminal (only 124/127 remain), the catalog and desktop markers are narrowed and mirrored,
the six new codes exist and are translated, the origin messages are fixed, and the rewritten tests pin the new contract
instead of weakening it. The defects below are in markers and texts; five of them come from my own plan wording
(the `nghttp2` marker in R1, the `easyanticheat` marker in R2, R4, R5 and R6), and I own those.

**What I checked myself** (read-only on the repo; scratchpad venv, `-p no:cacheprovider`; pytest-cov rewrote the gitignored
`.coverage`):
- 182 tests pass (report replay, terminal plan, catalog contract, exit-status, diagnostics coverage). Locale audit: 30 files,
  6003 keys each, all 19 new strings and the AUTH-002 rewrite present, none identical to English, no protected name dropped.
- Executed the working-tree wrapper, `diagnose_error` and `for_marker` on adversarial and real texts. Results that drive R1-R7:
  - `warning: libnghttp2-1.65.0-1 is up to date -- skipping` + an unrelated error -> NET-001 on all three surfaces.
  - `found game folder: /games/VRChat/EasyAntiCheat` + an unrelated error -> UPSCALE-002 on all three surfaces.
  - `[ERROR] AMD BC-250 (PCI 1002:13fe) was not found.` (the 3 Mint reports, `bc250-gfx1013-source.sh:164`) -> WORKFLOW-001 in
    the terminal, CMD-001 in the desktop. The paren-free script texts do reach HW-001.
  - `GLIBC_2.38 is available` + `foo: command not found` -> RUNTIME-001 (terminal, `for_marker`); the desktop says CMD-001.
  - Recovered DNS error then a compile failure -> BUILD-003 in the terminal, NET-001 in the desktop.
  - An `[ERROR]` line shaped like B2's planned probe ("...pacman database is still read-only") -> IMMUTABLE-001 in the
    terminal, because `requires="Read-only file system"` is not in that line. With the OS text appended it is IMMUTABLE-002.
  - The guard's `[INFO] Restoring SteamOS read-only protection.` alone -> GENERAL-001 (fixed as planned).
- `grep` on this machine is ugrep: a lone `)` in a marker is an error there (`mismatched ( )`), so the "no metacharacters"
  rule in the replay test is right and stays.

**Rulings on the four deviations: all approved.**
1. B6/B10 strings deferred: approved. "B1 owns the locales" was a device to keep two parallel authors from colliding on the
   30 JSON files; with one writer it prevents nothing and the wording depends on the UI. Condition: B6 and B10 each add
   their strings to all 30 locales and run `tests/desktop/i18n/`.
2. BUILD-003 `requires` wording: approved. `requires` is one string per entry, and gcc/g++ print `compilation terminated.`
   after every fatal error, so a missing header is still covered; the desktop keeps the exact pair. (Nit N2 below.)
3. `for_marker` last occurrence resolving to BUILD-003: approved. Its only callers are `describe_failure` (helper subprocess
   output) and `diagnose_error`, which uses it only for helper prefixes and PERM codes
   (`error_diagnostics.py:894-898`); no build log reaches it. The terminal and desktop, which do see build logs, agree on
   RUNTIME-001 for the plain GLIBC line. Revisit only if a build log is ever routed to `for_marker`.
4. R-53376560 GENERAL-001 until B3: approved; honest, and B3 owns the real fix. Obligation: when B3 prints the journal,
   change the replay expectation in `test_report_replay_2026_11.py` from GENERAL-001 to RUNTIME-001.

**Required changes** (all small; re-run the same B1 test set plus `tests/desktop/i18n/` afterwards)

R1. `nghttp2` is too broad as a bare marker. `src/bc250cc/shared/error_catalog.py:510`: replace `'nghttp2'` with
    `'nghttp2 shuts down connection'` (keep `'FRAME_SIZE_ERROR'`). `frontends/desktop/core/error_diagnostics.py:427`: drop the
    bare `r"nghttp2"` (the existing `curl: \(\d+\)` and `frame_size_error` already cover R-cc0af5ae). Package lists carry
    `libnghttp2`. Add a negative test (terminal, desktop, `for_marker`) with a package list and an unrelated error.
R2. Drop the bare `EasyAntiCheat` marker: `error_catalog.py:187` and `error_diagnostics.py:213` (`easyanticheat`). `has anti-cheat`
    and `anticheat-ok` already match R-c6ab33f2's text; a game-folder listing must not become UPSCALE-002. Negative test.
R3. UPSCALE-002 promises "nothing in the game folder was changed" (`error_catalog.py:182`, `error_diagnostics.py:215`), but
    `install_helixsr_bridge` removes a HelixSR 2 integration before the bridge can refuse (`helixsr.py:2648-2662`; B8 fixes the
    order). Reword the cause to end "...so HelixSR's bridge declined to install it." (no guarantee), keep the action, and
    update the 30 locales. B8 may add the guarantee back only with a test that proves the order.
R4. GPU-008's action names labels that do not exist (`error_catalog.py:275`, `error_diagnostics.py:173`). The toggle reads
    "Start governor" (`gpu_governor_view.py:1867`; the stopped pill says "Governor stopped — press Start governor", :1884) and
    the status "Connected · range running" (:2267); "Enable" was deliberately retired (comment :1673). New action: "Press Start
    governor on the governor card, wait a few seconds until it shows Connected, then apply the voltage curve again." Reuse the
    locales' existing translations of "Start governor" and "Connected"; update all 30 files.
R5. HW-001 misses the form of the script text that three Mint reports carry. Reword `scripts/system/bc250-gfx1013-source.sh:164`
    and `scripts/system/bc250-async-compute-radv.sh:100` to "AMD BC-250 PCI device 1002:13fe was not found." (the wording
    `bazzite_async_compute.py:166` and the other scripts already use), so `'13fe was not found'` matches. No test pins the old
    text. Do not add a marker with `)`. Add a replay test with the literal R-ffde613d line expecting HW-001 (terminal).
R6. RUNTIME-001 `requires="not found"` accepts any unrelated "not found" (`error_catalog.py:538`). Use
    `requires="(required by"`: it is a fixed string in both `grep -F` and `for_marker`, and it is the loader's own wording
    ("version `X' not found (required by Y)", also the Python ImportError of R-79e92b51). Negative test:
    `GLIBC_2.38 is available` + `foo: command not found` must not be RUNTIME-001 in the terminal or `for_marker`.
R7. Surface parity for recovered DNS then a build failure: move the desktop BUILD-003 rule (`error_diagnostics.py:450`) to
    just before NET-001 (`:425`) and assert both surfaces in `test_a_recovered_dns_error_does_not_outrank_the_build_that_failed_after_it`
    (it checks only the terminal today).
R8. `scripts/install-local.sh`: `import ssl` sits outside `probe()` (:165) with stderr discarded, and under `set -euo pipefail`
    a failure of the explainer aborts before the closing `[ERROR]` lines and `exit 2` (:340). Import `ssl` inside the
    certificate probe and call `explain_python_gui_runtime >&2 || true`. Add a test that breaks the `ssl` import (a stub
    `ssl.py` that raises, on `PYTHONPATH`) and still gets the closing lines and status 2. The replay fixture for R-1aad1216
    is rewritten expected output; it should also run the real function once.

**Non-blocking recommendations**
- N1 (B4): the desktop still shows CMD-001 for PCI-not-found texts and CPU-001 for Cyan's `Error: Message("...expected PCI bus
  location")` journal line (rule order: CMD-001 and CPU-001 precede HW-001, `error_diagnostics.py:459-481`). Add a narrow
  early HW-001 rule when the gate lands.
- N2: `'] Error '` (BUILD-003) is case-insensitive in the terminal and matches `[WARN] error while reading optional file`;
  consider `'] Error 1'` and `'] Error 2'`, or leave it.
- N3: desktop WINE-002's `cannot be executed here` has no `wine` qualification (the catalog's `requires="wine"` does); B8's
  message must contain "wine".
- N4: pre-existing and out of scope: desktop NET-001's `ssl|certificate verify|tls` matches any word containing "tls".

**Obligations carried forward**
- B2: the probe's `[ERROR]` line must contain both `pacman database is still read-only` and the OS text `Read-only file system`;
  otherwise the terminal shows IMMUTABLE-001 (verified above). Add a test with the final line.
- B3: the R-53376560 expectation changes with the journal (ruling 4); the journal line carries `(required by`, which R6 requires.
- B8: see R3 and N3.

**Next step:** once R1-R8 are in and the B1 test set plus `tests/desktop/i18n/` pass, B1 is approved without another arbiter
round; Claude commits after a spot check of the R1-R8 tests.

### [Fable] B1 fixes — R1–R8 from the arbiter's verdict applied

- R1 `nghttp2` → `nghttp2 shuts down connection` (catalog); desktop drops bare `nghttp2`. Negative:
  `libnghttp2 … up to date` + unrelated error is not NET-001 on the three surfaces.
- R2 bare `EasyAntiCheat` dropped (catalog + desktop). Negative: a game-folder listing is not UPSCALE-002.
- R3 UPSCALE-002 cause now ends "…so HelixSR's bridge declined to install it." (catalog, desktop, 30
  locales). `tests/infrastructure/test_helixsr3_bridge.py::test_a_bridge_refusal_after_a_helixsr_2_migration_has_already_removed_the_old_files`
  pins the current order (B8 flips its last assertion when it reorders).
- R4 GPU-008 action: "Press Start governor on the governor card, wait a few seconds until it shows
  Connected, then apply the voltage curve again." — 30 locales built from each locale's existing
  "Start governor" / "Connected" strings.
- R5 `scripts/system/bc250-gfx1013-source.sh:164` and `bc250-async-compute-radv.sh:100` now `die "AMD
  BC-250 PCI device 1002:13fe was not found."`; replay test asserts the terminal gives HW-001 (desktop
  still CMD-001 → N1, B4).
- R6 RUNTIME-001 `requires="(required by"`. Negative: `GLIBC_2.38 is available` + `foo: command not found`
  is not RUNTIME-001 (terminal, for_marker, desktop).
- R7 desktop BUILD-003 rule moved before NET-001; the recovered-DNS fixture asserts both surfaces.
  (Side effect noted: in the desktop a build log that also says "no space left" now reads BUILD-003.)
- R8 `install-local.sh`: `import ssl` inside the certificate probe; `explain_python_gui_runtime >&2 || true`.
  New `tests/packaging/test_installer_runtime_probe.py` runs the real function and the real failure block
  with a raising `ssl.py` stub and with no python3 on PATH: exit 2 and the closing `[ERROR]` line in both.
- Decky artefact regenerated; error_origins.json unchanged.
- Tests: B1 set + test_installer_runtime_probe + test_helixsr3_bridge → 394 passed; tests/desktop/i18n →
  95 passed; coverage ratchet still satisfied. Codex review already done (arbiter verdict); no second round.

### [Claude] B5, B2, B3, B4, B8 — done directly (owner stopped Fable to save usage)

- B5 `95ac313`: commented TOML key beside the active one is not a duplicate (R-2942b02f).
- B2 `3ae1d5d`: SteamOS graphics setup inside the app's writable-root guard, pacman db probe, mounts on failure. **Needs real SteamOS.**
- B3 `63b5bd3`: Oberon restores omitted linux-api-headers (R-bb33f44b); Bazzite builds in the host's Fedora release + ldd gate (R-53376560). Not done: activation is-active/journal tail in gpu_repository.
- B4 `1464eca`: PCI gate (present/absent/unknown), blocks only confirmed absence; tests default to unknown.
- B8 `de540c7`: wine probed with --version (WINE-002); bridge asked before migrating a HelixSR 2 game.

Pending: B6 (cancel ≠ fail), B7, B9, B10 (wording), final review of DirectMesh/HelixSR.
