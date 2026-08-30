# Quick Access control-surface design record

## Scope

This document records the v5 Quick Access presentation contract implemented
from `bc250_quick_access_full_dashboard_v5 (1).html`. The redesign replaces the
old frontend rather than layering new cards on it. Protocol 5 adds only the
finite CPU callables required by the approved surface; the Desktop UI and the
separate `bc250-steamos-game-helper` remain untouched.

The reference is the Desktop Compute Units editor, not a miniature copy of the
Desktop dashboard. The QAM panel is a narrow, controller-first control surface:
it must tell the player what can be changed, what is live, and what will happen
when A is pressed without turning every datum into a coloured card.

## Visual contract

- Use one 360 px-style unified graphite surface (`#171717`) with neutral
  dividers and native SteamOS controls. There are no nested module frames or
  `PanelSection` blocks.
- Use the prototype's purple/orange/blue/cyan only in small subsystem identity
  marks. Orange denotes a current choice or intentional primary action, not
  the background of every module.
- Reserve colour for meaning: green `D+` (driver+routed), cyan `S+` (live SPI
  route), red `D!` (driver available but held), graphite `--` (off), and amber
  only for attention/warnings. Pending CU edits are a thin amber lower marker,
  never a replacement for the cell's routing-state colour.
- Controller focus is one thin blue border with a restrained inset cue. It
  must not add a bloom, scale, second exterior outline, or change the colour
  semantics of a control.
- Keep type readable at normal Game Mode viewing distance. Strong weight is
  reserved for an active value or a command label, not every caption.

## Structure

1. A compact identity/live header is followed by one passive 2×2 telemetry
   block for GPU, CU, CPU and the selected PWM channel. Session history and a
   manual refresh button are not part of the permanent surface.
2. GPU is a native 2×2 profile group. `More frequencies` is one disclosure row
   whose root-advertised TOML points appear as native gamepad buttons.
3. Compute Units is the prototype's compact 4×5 topology: exactly twenty WGP
   buttons are direct children of one focus grid, followed by the four explicit
   actions Apply, Save, Install and Remove in a 2×2 grid.
4. CPU contains live clock/Tctl, the saved-profile shortcut, a 3500–4200 MHz
   slider, an estimated-VID slider mapped to the audited -50..0 scale, temporary
   apply, and dedicated install/remove service actions. It reuses a saved
   thermal ceiling when present, otherwise uses the explicitly labelled 90 °C
   temporary-test limit, and rejects estimates above 1325 mV at both backend
   layers. The exact candidate must pass a live test before boot persistence.
5. Fans use the native D-pad slider and an inline 2×2 native-button channel
   chooser, avoiding Decky dropdown popup behavior that failed on the target
   Steam client. PWM 2 remains the default.

## Explicit non-goals

- Do not bring back Live Scenes or turn telemetry into another write surface.
- Do not use large coloured module backgrounds, custom keyboard navigation, a
  mouse-only div control, dropdown/combo popups, or external CSS.
- Do not copy Desktop widgets verbatim; Desktop owns richer editing and
  diagnostics. QAM carries only bounded actions that can be verified live.
- The voltage slider is an estimated VID representation of `scale`, not direct
  millivolt control and not a measured sensor value.

## Validation required

Source checks cover strict TypeScript, Decky build, native `Button` activation,
the single CU focus grid, HTML-structure parity, finite protocol validation and
the packaging preflight. A physical Game Mode pass is still required after
deployment: traverse all 20 WGP cells, GPU points, fan channel chooser/slider,
both CPU sliders, confirmations and every CU/CPU service state at actual QAM
width.
