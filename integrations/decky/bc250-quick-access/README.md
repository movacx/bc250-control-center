# BC250 Quick Access (Decky)

Optional Game Mode panel for BC250 Control Center. It is designed for controller use and offers a small set of verified hardware actions; it does not replace the desktop application.

## Available controls

- GPU: conservative Cyan ranges and already validated safe-points.
- Compute Units: live 4×5 WGP selection, saved boot table and service actions.
- CPU: bounded detector, temporary profile and validated scale test.
- Fans: manual PWM 2–5 control and return to automatic mode.

The panel shows live status while it is open and keeps Desktop and Quick Access CU state synchronized. Advanced GPU voltage editing, arbitrary commands, firmware work, bootloader changes and fan curves remain in the desktop application or are intentionally unavailable.

## Install

BC250 Quick Access is installed from **BC250 Control Center**, not as a standalone plugin download.

1. Install and open BC250 Control Center in Desktop Mode.
2. Open **Dashboard** and scroll to the lower **Decky** section.
3. Choose **Install Decky + Quick Access (Beta)** when Decky Loader is missing, or **Install / repair BC250 Quick Access** when Decky is already present.
4. Review the terminal result, then restart Game Mode or reload Decky.

The application detects the existing Decky state and uses the appropriate official/bootstrap route before deploying the BC250 plugin. SteamOS is the primary target; Bazzite and CachyOS Game Mode are compatibility targets.


## Safety

Every action is checked again by the root-owned helper and read back when possible. Hardware validation on the target BC-250 is still required before release.
