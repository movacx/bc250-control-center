# Fan control v2 — design

Status: in progress on `desarrollo/bc250-control-center`. Work log and ownership: `docs/FAN_CONTROL_V2_DEBATE.md`.

## Why

Field reports show the v1 fan system is too limited to replace CoolerControl:

- **Forum report (J4003 wiring):** fans on PWM 1, 3, 4, 5 with curves, PWM 2 (AIO pump) fixed at 90 %.
  Only the last channel "Apply fan curve" was pressed on followed the curve; every other channel fell
  back to firmware (70 %). Cause: the policy carries **one** `pwm`, and the root service releases the
  previous channel whenever the policy's channel changes.
- **Issue #29:** "pwm1 is not detected, the BIOS shows Fan 1 running". The BIOS and the Linux driver
  number the headers differently (BIOS 1→pwm2, 2→pwm3, 3→pwm4, 4→pwm5, 5→pwm1, per
  mothenjoyer69/bc250-documentation `hardware.md`). Our labels follow the generic MSI driver names
  ("CPU Fan" on pwm1), so users look for the wrong channel.
- PR #30 added the real regulator temperature (`bc250_vrm`) to the root loop.

## Goals

1. Every PWM channel is controlled independently, from boot, by the root service.
2. One control engine. The desktop daemon fallback, the root service, the TUI/web previews and the
   tests run the same pure code. No more "mirrors X; a parity test keeps them in step".
3. Feature parity with what a BC-250 owner uses CoolerControl for: per-channel curves bound to a
   chosen sensor, mix (max of several curves), fixed duty, firmware hand-back, hysteresis and response
   delay, asymmetric step limits, min/max duty, pump protection, stall detection, emergency override,
   named modes.
4. Fail safe: invalid policy → firmware; missing sensor → failsafe after timeout; critical
   temperature → failsafe on every controlled channel immediately; service stop → each channel goes
   back to firmware automatic.

Non-goals (for now): RGB/LCD, liquidctl devices, remote/plugin devices, custom file sensors.

## Architecture

```
src/bc250cc/domain/fan/engine.py      canon, stdlib only, pure (no I/O)
        │  scripts/development/generate_fan_engine.py  (committed artefact, byte-compared by a test)
        ▼
privileged/lib/bc250_fan_engine.py    loaded by absolute path by bc250-fan-pwm-helper (root)
```

Same pattern as `shared/contract.py` → `privileged/lib/bc250_contract.py`. The helper loads the engine
from `/usr/libexec/bc250-control-center/lib/` (packaged) or `../lib` next to itself (source tree),
after the same root-ownership / no group-other-write check `bc250-system-setup-helper` does.

The helper keeps everything that touches hardware (sysfs reads/writes, locks, `bc250_vrm`
sampling, overrides, external hand-off, unit management). The engine owns only decisions.

## Policy schema 2

```jsonc
{
  "schema": 2,
  "failsafe_percent": 100,          // 40..100
  "sensor_timeout_seconds": 15,     // 3..300
  "critical_c": {"gpu":95,"cpu":95,"vrm":105,"board":90},
  "offsets_c":  {"gpu":0,"cpu":0,"vrm":0,"board":0},   // -30..30, applied before curves
  "channels": {
    "2": {
      "mode": "fixed",               // firmware | fixed | curve | mix
      "percent": 90,
      "role": "pump"                 // fan | pump
    },
    "1": {
      "mode": "curve",
      "source": "hottest",           // gpu | cpu | vrm | board | hottest
      "points": [[40,30],[60,55],[75,100]],   // 2..8 points, strictly increasing temp
      "role": "fan",
      "min_percent": 20,             // floor while controlled (0..100)
      "max_percent": 100,
      "hysteresis_c": 1.0,           // 0..10
      "response_delay_seconds": 0,   // 0..30: a change must persist this long (rising bypasses when > critical-5)
      "deadband_percent": 2,         // 0..20
      "max_up_step_percent": 100,    // 1..100 per write
      "max_down_step_percent": 10,   // 1..100 per write
      "start_percent": 0,            // 0..100: spin-up kick when leaving 0 %
      "stall_detect": true
    },
    "3": {
      "mode": "mix",
      "mix": [                        // max of member curves, each on its own source
        {"source":"gpu","points":[[50,30],[80,100]]},
        {"source":"vrm","points":[[70,30],[95,100]]}
      ]
    }
  }
}
```

- Channel keys are `"1".."12"`. At most 12 channels, at least 1.
- `role: "pump"`: no policy may command a pump below 30 % (refused at validation); on a curve its
  `min_percent` defaults to 50. A stopped pump is its own fault (`pump-stalled`).
- A critical reading drives every controlled channel to **100 %** (never lower than its current
  duty), latches until every sensor is 5 °C under its limit, and holds while a sensor that answered
  before is missing. Sensor loss (no critical evidence) uses `failsafe_percent`, also never lower.
- Schema 1 policies are still accepted and migrated in memory to a single-channel schema 2 policy,
  so an upgraded helper keeps following a policy written by an older desktop.
- The status file gains `channels: {"<n>": {percent, raw, source, sensor, temperature, state,
  fault, error}}`, `faults`, `controlled` and `policy_schemas: [1, 2]`; the v1 top-level fields
  describe the first controlled channel.
- Negotiation: the desktop sends schema 2. A helper from before v2 answers "Unsupported fan policy
  schema"; the desktop then sends the same policy as schema 1 only when nothing is lost
  (`downgrade_policy_to_v1`), otherwise it asks the user to reinstall. Digests are compared after the
  engine's normalization, so a v1 file equals its v2 meaning.
- `--restore-boot` replays only person-chosen duties on channels the policy does not control, and
  nothing when the saved policy is invalid. The service's own curve outputs are never replayed.

## Engine API (pure)

```python
validate_policy(data) -> dict                 # raises ValueError; v1 → v2 migration
interpolate(points, temperature) -> int
effective_readings(readings, policy) -> dict  # offsets applied
critical_reading(readings, policy) -> (sensor, value) | None
class ChannelMemory  (frozen dataclass: last_percent, last_temperature, pending_since, pending_percent,
                      last_write, missing_since, stalled_since, ...)
plan_channel(channel_policy, policy, readings, memory, now) -> ChannelDecision
                                              # percent|None(firmware/hold), source, sensor, temperature,
                                              # new memory, reason
plan(policy, readings, memories, now) -> dict[int, ChannelDecision]
assess_stall(channel_policy, decision, rpm, memory, now) -> fault | None
```

Order inside `plan_channel`:
1. critical reading anywhere → `failsafe_percent` (bypasses everything, every non-firmware channel).
2. mode firmware → release.
3. fixed → percent.
4. curve/mix: source temperature (hottest of the requested set) → missing → wait `sensor_timeout`
   then failsafe.
5. interpolate (mix = max of members).
6. hysteresis on temperature, response delay, deadband, asymmetric step limits.
7. clamp to `[min_percent, max_percent]`; start kick when last was 0 and target > 0.

## Hardware labels (#29)

| Linux | Physical header | BIOS name |
|---|---|---|
| pwm1 | J4003 Fan 5 | Fan 5 |
| pwm2 | CPU_FAN1 / J4003 Fan 1 | Fan 1 |
| pwm3 | J4003 Fan 2 | Fan 2 |
| pwm4 | J4003 Fan 3 | Fan 3 |
| pwm5 | J4003 Fan 4 | Fan 4 |

Users can rename every channel (`fan_channel_labels` in the desktop config); the label never changes
the channel identity.

## UI

The Fans page becomes a channel board: one card per writable channel with live RPM / duty / source
temperature, a mode selector (Firmware · Fixed · Curve · Mix), the source selector, and an editor that
opens per channel with a live operating-point marker. A "Modes" strip saves and applies a snapshot of
every channel (Quiet · Balanced · Performance · custom). Everything goes through the root policy;
the desktop never races the service.

## Phases

1. Engine + generator + tests. 2. Helper multi-channel + packaging. 3. Desktop config model,
`build_system_fan_policy` v2, daemon fallback on the engine. 4. UI channel board. 5. Labels/#29,
TUI/web/Decky follow-ups.
