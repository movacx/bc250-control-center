# Fan workspace review fixes

The desktop now distinguishes saving a desired setting from confirming a hardware operation. A root-service request shows a saved notice only after the helper accepts it; rejected or unsupported requests cannot produce an applied notice. Fixed-duty writes keep their existing hwmon verification. Failed writes remain retryable without editing the percentage, and an overridden channel can resume its unchanged policy.

## Drafts and profiles

- Applying a global profile requires explicit discard of a pending channel draft; Cancel keeps it.
- Applying a draft while changing rows checks whether the inner low-duty confirmation was cancelled before navigating.
- Save as captures the visible draft without applying it. Built-in names and their current translations are reserved; overwrites require confirmation.
- The selector displays Custom when no named profile is active.
- Imported speed-slot values immediately update both the shortcut labels and their callbacks.

## Profile files

The desktop exports `bc250-fan-profiles` schema 2. It carries the three legacy fixed-speed slots, current `channels`, channel `labels`, named `modes`, and the last active mode name. Channel records retain the shared engine's fields, including mixtures, pump role and response settings.

Imports validate the whole document before saving. Current channels are stored as an imported named snapshot when no identical snapshot exists; importing never replaces the active hardware policy. Existing profile-name collisions require confirmation, repeated snapshot imports are idempotent, and the existing 12-mode limit rejects an over-capacity merge instead of silently dropping data. Files are read with a bounded size.

Schema 1 remains readable. Its optional curve becomes a saved imported profile instead of being ignored. The original schema-1 domain helpers remain available to other clients, and Decky still uses its own three fixed-speed presets.

## Calibration and compatibility

Calibration requires a finite, valid temperature throughout the sweep. Missing or invalid readings abort and attempt full speed. The direct temperature reader requires an APU reading and also includes available NCT board/VRM temperatures. Saved or draft pump channels cannot enter the calibration sweep. Cancellation leaves full speed intentionally; Resume/Sync is available for the existing policy.

Helper capability detection reads the installed root-owned helper's schema declaration without launching it or asking for credentials. Known schema-1 helpers are refused before saving/applying an incompatible policy; an unknown helper still receives normal transport validation. The installed helper and generated engine must be updated together through the normal installer to use schema-2-only features. Running `run.sh` does not replace installed privileged components.

## Layout and localization

The editor's feedback and Apply/Revert controls stay outside its scroll area. Compact graphs preserve the complete axes. The top action explicitly says Apply profile, and driver tools are grouped under Diagnostics. The Save as dialog has adaptive sizing and translated buttons. New messages are included in all supported locale catalogs.

Regression coverage is in `tests/desktop/fans/test_fan_review_regressions.py` and `test_fan_calibration.py`. The checks include deferred success/failure, queued service updates, retry/resume, draft preservation, complete profile round trips, compatibility preflight, import refresh, dialog geometry and calibration safety.
