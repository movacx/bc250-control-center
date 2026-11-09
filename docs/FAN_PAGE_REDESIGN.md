# Fans page — redesign from scratch

The current page stacks the v1 single-channel deck, a thermal list, a profiles strip and the v2
channel board one below the other: two ways to do the same thing, eight tall cards for headers with
no fan, unstyled white buttons, icon badges on every heading. It is replaced, not patched.

## Visual language (copied from Sensors, Processes and Black Box)

- **One panel** (`panel` background, 1 px `border`, 18 px radius), page title + one-line description
  in plain text. **No icons, no icon badges, no eyebrow kickers, no cards inside cards.**
- Underlined **text tabs** (`processTab` style) for views.
- Flat **text buttons** (`processButton='secondary'`/`viewSwitch`) — never filled white.
- A dense **table** (QTreeView, `sensorTree` style): small uppercase muted headers, hairlines,
  alternate rows, tabular figures, numbers right-aligned, units in the column heading.
- Small **colour dots** for state (green active, blue curve, orange override/warn, red fault, grey
  firmware) exactly like the sensor kind dots.
- A muted **footer line** with counts and the service/driver state.

## Layout

```
┌ Fans ──────────────────────────────────────────────────────────────────────────────┐
│ Fans                                                         [●] Control from boot │
│ Every fan header on the board, what it follows and how fast it turns.             │
│ ───────────────────────────────────────────────────────────────────────────────── │
│ Channels   Thermal                                       ☐ Hide unused channels    │  ← text tabs
│ Mode: Quiet  Balanced  Performance  <saved…>   [Save mode…]          [More ▾]      │  ← kind-chip style
│ ┌ CHANNEL │ HEADER │ MODE │ FOLLOWS │ TEMP °C │ TARGET % │ DUTY % │ RPM │ STATE ┐  ┌ editor ───────┐ │
│ │● PWM 2   CPU_FAN1/J4003 F1 · BIOS 1  Curve  Hottest  53.4  64  64  2101 Active│  │ PWM 2 · name  │ │
│ │● PWM 1   J4003 F5 · BIOS 5          Firmware —      —     —   50  0    —     │  │ Mode tabs     │ │
│ │ …                                                                            │  │ form rows     │ │
│ └──────────────────────────────────────────────────────────────────────────────┘  │ curve plot    │ │
│                                                                                   │ points table  │ │
│                                                                                   │ [Revert][Apply]│ │
│ 5 channels · 2 followed by the system service · nct6687 · writable                └───────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- **Channels** tab: table left, editor right (QSplitter, like Sensors list + graphs). Selecting a row
  loads it into the editor. "Hide unused channels" (on by default) hides headers with 0 RPM that are
  not configured — no more eight empty cards.
- **Editor** (right): heading `PWM n` + editable name (plain line edit, no badge), header/BIOS line in
  muted text, then underlined mode tabs **Firmware · Fixed · Curve · Mix**, then form rows (label left,
  control right, hairline between rows — the thermal-detail list look): role (Fan / Pump), sensor,
  fixed duty slider, the curve plot (existing `FanCurvePlot`, live operating point), points as a
  compact two-column table, "Advanced" as a disclosure with the tuning rows. Footer of the editor:
  Revert / Apply (text buttons, Apply in accent outline).
- **Thermal** tab: the inputs the service follows (GPU, CPU, VRM with source, board), their critical
  limits and offsets, failsafe duty — a sensor-style table, with the hand-off to another program and
  the driver tools (prepare nct6687, PWM paths, raw status) as text buttons at its foot.
- **Header right**: "Control from boot" ToggleSwitch, like Black Box's "Start with the session".
- **More ▾** menu: export/import profiles file, export to Decky, hand off to another program.
- **No driver / read-only**: the table still lists RPM read-only; a single muted line above it says
  what is missing with one text button "Prepare PWM driver".

## Behaviour

Everything goes through `FanChannelsService` + `_sync_system_fan_policy`. No direct PWM writes from
the page except "Firmware" on a channel when the service is off (restore automatic) and "Fixed" when
the service is off (one pkexec write, as today). Curves/mix need the service; the editor says so in a
muted line and Apply turns into "Save" when it is off.

## Kept / removed

Kept (non-UI): `fans_helpers`, `core/fan_state_presenter`, `FanCurvePlot`, `PwmPathsDialog`,
profile exchange, driver actions, hand-off. Removed: the v1 manual/curve deck, profile cards,
`fans_channels.py` board, the overview/cooling cards, every SectionCard icon on this page.
App hooks kept: `settings_requested`, `apply_appearance`, `set_updates_active`, `refresh`,
`retranslate_dynamic_copy`, `prepare_pwm_driver(dialog_parent=)`; `fans_manual`/`fans_curve`
dashboard actions open the Channels tab with the editor on Fixed/Curve.
