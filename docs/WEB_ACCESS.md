# Web control from a phone

The web interface runs on the BC-250. It reuses Control Center's application
services and privileged helpers. It needs no CDN, external font, cloud account,
Node runtime. The HTTPS backend uses Cheroot (`requirements-web.txt`), installed
as a distribution dependency in packaged builds. Node is used only to rebuild
the frontend.

## Open it

1. In the desktop app, open **Remote access**. All web connection and security
   controls live in one card; this page no longer starts SSH or previews the TUI.
2. Start web access and enable **Reachable from the local network**. HTTPS is
   mandatory on the LAN. The QR appears directly beside the address and key;
   select the desired address if the board has multiple interfaces.
3. Use **Save public certificate** to export only this installation's CA
   certificate. Transfer it privately to the phone and compare the displayed
   SHA-256 fingerprint before installing it. On Android install a CA certificate;
   on iOS/iPadOS install the profile and enable full trust in Certificate Trust
   Settings. This trusts certificates signed by this local authority, so install
   it only on devices you own and protect the board's private CA key.
4. Scan the visible QR from the same home network, or enter the address and key.
   New browser sessions have **monitoring-only** permission. In the desktop's
   **Connected devices** table, match the device code displayed on the phone (plus browser/address) and press **Allow
   hardware control**. This is independent of native administrator authorization.
5. The owner can downgrade or disconnect each browser, or disconnect all of them.
   Reconnecting starts in monitoring-only mode. By default, sessions expire after 30 minutes
   without requests or eight hours in total; the owner can choose another
   expiry for each session in the device toolbar; an open monitoring page counts as
   activity. Restarting the server invalidates its browser sessions.

Each installation creates its own local CA. Private keys have owner-only access;
only the public CA certificate is exported. A certificate for the web server is
renewed when it is expiring or the board's LAN addresses change, keeping the same
CA so the phone does not need to install a new authority. Old self-signed server
certificates are replaced on the first start with this implementation. Until the
public CA is trusted on the phone, the browser will still show a warning. This
application cannot install trust on the phone remotely.

The pairing key travels in the URL fragment, which browsers do not send in HTTP
requests. The page removes the fragment before sending the key in the login
request. Entering the key by hand remains available. Generating a new key
revokes existing browser sessions on their next request.

The default port is 8250. To run the checkout without reinstalling:

```sh
PYTHONPATH=src:. python -m frontends.web --host 0.0.0.0 --port 8250
```

Use `--http` only for loopback development or a protected SSH tunnel. Network
HTTP connections cannot log in, run control actions or submit Linux passwords, including when an old
`lan_password` setting is present. The service does not change firewall rules
or router forwarding.

## Source-install runtime and safe restarts

If the desktop's system Python lacks the web dependencies, prepare a stable,
user-owned environment instead of modifying system Python:

```sh
python3 -m venv --system-site-packages ~/.local/share/bc250-control-center/web-runtime
~/.local/share/bc250-control-center/web-runtime/bin/python -m pip install -r requirements-web.txt
```

The launcher probes the current interpreter and then this environment. The user
service records the working interpreter in `ExecStart`. A network-mode switch
checks dependencies before stopping the current endpoint; if restart fails it
restores the previous settings and tries the previous mode. Starting reports
success only once the listener is ready. Restart an already-open desktop after
updating launcher code so its in-memory functions use the new implementation.

With LAN disabled the server listens on `127.0.0.1`, remains protected by the
access key, and can be opened only from the board itself. A phone's localhost
refers to the phone. The connected-devices table lists signed-in browsers,
not all hosts on the Wi-Fi. Rows show browser, IP, device code, permissions,
active/idle state, last activity and effective expiry. Headers and cells share left alignment. Drag the three-dot grip below the table
to change its height; the local UI settings remember it across refreshes and
application restarts. Double-click the grip to fit the rows. Selection survives
refreshes; granting control or disconnecting targets that selected session.

## Local-network boundary and server

Cheroot handles HTTP parsing and TLS with 4–12 worker threads, a 16-connection
accepted queue, 12 keep-alive slots, a 10-second socket timeout, 16 KiB headers
and 64 KiB request bodies. The server refuses to start as root. HTTP is allowed
only on loopback. It never silently falls back from HTTPS.

Remote peers must belong to a directly attached RFC1918 home-network subnet.
Docker/VM links and common VPN links are excluded from discovery. Discovery
failure leaves only loopback accessible. The policy uses the actual connection
peer, ignoring forwarded IP headers. An interface/subnet change requires a
server restart. A custom bridge or VPN named like a physical interface is not
an authenticated trust boundary; keep router forwarding, public reverse proxies
and tunnels disabled. Loopback remains available for the owner's local browser.
This policy is an application check, not a replacement for firewall rules.

The desktop lists up to 16 browser sessions in an owner-only registry. It stores
hashed session identifiers, address, browser metadata, role and expiry; it never
stores the session cookie, CSRF token or Linux password. Only the local owner
can grant control. A browser cannot self-promote by changing a request or the UI.
Revocation takes effect on its next request; it closes the terminal and may
interrupt an operation in progress. Downgrading prevents new control requests
and terminal input; the owner of an already-running job can still stop it.

## SSH authorization in the browser

SSH is optional. If it is needed, enable the board's SSH service through the
operating system first; the redesigned Remote access page manages only the web. Press **SSH** in the
Dashboard board card, then **Connect SSH**. Authentication is handled by the installed
OpenSSH client: an existing permitted SSH key/agent may work, otherwise the
Linux password is requested in the web dialog. No password is retained for
later commands.

The SSH destination is fixed to `127.0.0.1` and the account running Control
Center. The browser cannot choose a host, account, shell command or executable.
Host keys are pinned from root-owned, non-writable `/etc/ssh/ssh_host_*_key.pub`
files. Unknown or changed keys are rejected; there is no automatic acceptance
or `StrictHostKeyChecking=no` fallback. Custom server configurations without
those public key files need their local host-key setup corrected first.

After SSH login, a private worker runs as that user on a persistent terminal.
Without SSH, the web creates the same terminal locally. Neither the server nor
the Python action worker runs as root. SSH is optional when the web already runs
on the board; it is not a substitute for Linux administrator authorization.

Hardware actions use **native sudo** on that terminal to invoke the same
installed helpers with their existing parameter and ownership checks. This
avoids graphical Polkit dialogs, including policies that deny remote sessions
before any password challenge. The desktop and TUI keep their existing Polkit
path. No Polkit policy, sudoers rule or system SSH configuration is modified.
The account needs permission under the machine's existing sudo policy.

When sudo needs the Linux password, its prompt appears in the operation panel.
Input goes directly to the active terminal; it is not saved in a command,
configuration, protocol message to the worker or transcript. Sudo controls its
own authorization retention: the persistent terminal permits reuse while the
installed policy allows it. Passwordless sudo is not required or installed.
Closing the terminal ends that terminal's authorization context; global sudo
cache behavior remains subject to the host policy.

The web access key is requested once at login. Changing CPU/GPU/CU settings
still requires confirmation, but never asks for that web key a second time.
Hardware bounds, trusted-backend checks and operation locks remain in place.
The private worker accepts only the existing action catalog; it cannot execute
an arbitrary browser-supplied shell command.

SSH encrypts the connection between the web process and the SSH service. HTTPS
protects the separate phone-to-web connection. Using SSH internally does not
make an HTTP page encrypted.

Each browser owns its local/SSH terminal and operation output. Another browser cannot
read its console, type into its job or cancel it. The server serializes hardware
jobs across browsers. Logging out, key rotation and session expiry close its terminals. An unused terminal expires after 15 minutes.

## Desktop privacy cover

The desktop's Remote access page starts concealed on every application launch.
Revealing it starts a five-minute window, after which its entire contents are
concealed again, even when the user is interacting. **Lock view** in the page header
conceals it immediately. An opaque cover inside the existing card shows **Show
information**; pressing it starts another five-minute window. Navigating away,
refreshing status or returning to the page does not reset that deadline.

The live controls are hidden, including the QR, key, addresses and device table;
keyboard focus moves to the reveal button and the view's status polling pauses.
The cover blends softly moving graphite shades over a softened thumbnail of the
layout: pearl grey in the light theme, graphite in dark, and deep slate blue
with steel-blue highlights in night-blue.
Animation uses elapsed time and subpixel movement to avoid jumps or changes in
speed when rendering slows; the text and reveal button stay still.
Before creating it, the key, addresses, networks and device cells are replaced or
hidden and the QR is replaced with decorative blocks. Only this sanitized,
128-pixel-wide thumbnail stays in memory while concealed; nothing is saved to
disk. Revealing the page discards it. The animation pauses when the page
is hidden. The card keeps its dimensions and the reveal action follows the
visible portion when scrolled. In-flight background operations and the web
service continue; the cover changes no device permissions or session expiry.
This is screen privacy, not an operating-system lock or password challenge.

## Choose session expiry per device

Select a row in **Connected devices**, choose **Expires in**, then **Apply
expiry**. Presets cover 15/30 minutes, 1/8/24 hours and 7/30 days. **Custom**
accepts a duration in minutes, from one minute up to one year. The fixed deadline
starts when applied, replaces both the default inactivity limit and the original
eight-hour limit for that browser, and preserves its hardware permissions.
Other browsers keep their own policies. The table displays a date for deadlines
on another day, with the complete local date/time in its tooltip.

The choice is stored in the owner-only session registry and is enforced on each
server request. Only the desktop owner can change it; no HTTP action allows a
browser to extend its own session. A new login starts a new monitoring-only
session with the defaults; server restart, key rotation and explicit revocation
still invalidate sessions. Existing expired sessions cannot be revived.

The transport cookie can remain for up to one year so an owner-selected long
expiry also works while the browser is closed. Cookie presence is not
authorization: default idle/absolute limits or the selected server deadline
still reject an expired session regardless of cookie lifetime.

## Install on the home screen

The web includes a same-origin web app manifest with BC250 icons, a standalone
window and a stable Dashboard entry point. **Install app** appears on the login
screen and in web Settings. Supporting Chromium browsers use the native install
prompt; other browsers receive inline menu instructions. Safari on iPhone/iPad
uses Share → Add to Home Screen (enable Open as Web App if offered).

Installation needs a supported browser and trusted HTTPS on the phone. Trust the
board's local CA first. The board must remain running and LAN access must be
on for a phone; an installed shortcut to `127.0.0.1` on the board is not a phone
address. If the LAN IP or port changes, the installed shortcut points to the old
origin; use a stable board address or replace the shortcut.

The manifest/start URL contains no pairing key or session token. Installation
does not grant control, store the Linux password, or extend session expiry.
Normal key login and desktop device approval remain in force. No service worker
or offline hardware cache is installed: hardware reads and commands need the
live server. Existing build notices continue to avoid forced reloads during jobs.

References: [MDN installation criteria](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable),
[Apple home-screen web apps](https://support.apple.com/guide/iphone/iphea86e5236/ios).

## Phone layout

The bottom bar reaches Dashboard, CPU, CU, GPU and Sensors. Settings and fans
are in the menu. CPU/GPU profiles have separate, touch-sized edit buttons. GPU frequencies
are changed through profiles; the manual frequency slider belongs to desktop.
The SSH button appears only inside the Dashboard board card; repeated page
headings and the CU overview card are omitted. Secondary and experimental controls are
expandable. CU rows show five WGP pairs each and warn about engine imbalance. Selecting a preset or toggling a pair only edits the draft; applying
still needs confirmation.

CPU and GPU control pages separate profile configuration from monitoring.
Their profile choices remain vertical bars with a right-side edit button,
without an operating-profile heading or subtitle. Editing stays inline. The
GPU governor service card contains its three service buttons, then the Cyan
method/usage/temperature selectors, the telemetry checkboxes and the Apply
compatibility button. Compatibility has no separate card or disclosure.

The GPU voltage laboratory keeps its own navigation section. Entering it
immediately shows Gentle, Moderate, High and Custom, followed by the active
frequency/current/selected/delta table and actions. There is no extra open
button, nested disclosure, repeated title or additional-settings menu in that
workspace. The web exposes only those three boost presets and custom editing;
restoration remains a separate action. Review is inline and still requires
explicit confirmation before executing a helper. Changes to the draft cancel
a stale review. The shared 600–1210 mV bounds and monotonic-curve checks remain.

GPU details distinguish the configured TOML ceiling from the loaded D-Bus
limits and the active range. Enabled file points become available to profile
editors before Cyan reloads them. Commented points leave the editor immediately.
Commenting is blocked while the active range is above 2000 MHz; select and
apply a lower profile first. Completion invalidates the reader's caches even
when an operation fails, so partial outcomes can be read back.

Sensors use two primary mobile views: **List** and **Graphs**. Search and a
category selector remain visible; less frequent options sit under **More**.
Tap a reading to reveal its statistics and history in place. Checkboxes choose
which sensors are available to plot; filtering preserves selections outside
the visible list. Graphs show a separate history for every selected sensor, including selections
outside the current list filter. Selected sensors without data have an explicit
waiting state. Desktop web retains the table and multiple plots.

Mobile plots use fewer axis labels and separate numerical readouts rather
than overlapping labels on the curve. Touch or drag a plot to inspect a
sample; arrow keys move the cursor and Escape returns to live readings. The
mobile time axis grows with the available history up to two minutes; it does
not fill missing history with synthetic samples. Per-core heat maps become
readable rows with individual history lines and current values on phones.

Profile editing and routine hardware reviews happen in the page. Voltage
review is also inline and requires explicit confirmation; other higher-risk
actions retain their confirmation dialog. Mobile operations start
in a compact progress bar and open their console when authentication is needed
or an operation fails. Finished progress can be dismissed directly. The
voltage editor is immediately visible in its own section and keeps drafts
across preview changes.
Navigating between pages resets the main scroll position.

Themes and language are browser-local. The shared desktop catalogs supply all
30 languages; changing the web preference does not alter desktop settings.

## Development and verification

```sh
python -m pip install -r requirements-web.txt
npm ci --prefix frontends/web/app
npm run build --prefix frontends/web/app
QT_QPA_PLATFORM=offscreen python -m pytest tests/web -q -o addopts=''
```

Built assets are committed under `frontends/web/dist/` and copied with the
frontend by the existing installers and package staging. QR generation is a
pinned MIT-licensed dependency vendored in the source tree; see
[Third-party notices](THIRD_PARTY_NOTICES.md).

Tests cover the HTTP authentication boundary, CSRF, key rotation, plaintext
password rejection, browser isolation, action allowlisting, avoiding duplicate workflow
execution after a failure, and the real SSH worker against an isolated sshd with
throwaway keys. The SSH integration test skips when OpenSSH server/client tools
are unavailable. It does not start or reconfigure the system SSH daemon.

See [Web architecture and file map](WEB_ARCHITECTURE.md) for the execution and authorization diagrams.

## Frontend updates

The build writes a content identity in `dist/version.json` and the HTML, and
adds it to the JavaScript/CSS URLs. An open web session checks that identity
every 15 seconds and offers **Refresh** when a newer frontend is available.
It never reloads automatically; refreshing is disabled while an operation is
running. A tab opened before this mechanism was added needs a manual reload
once. Translation catalogs are reread when the refreshed frontend requests
them, including after a frontend rebuild without a server restart.

## GDDR6 controls

The GDDR6 temperature block and its Prepare / Monitor live / Stop controls live
only on Dashboard. The web does not add session chip temperatures to the CPU,
GPU or Sensors pages. Sampling is explicit and uses the same root-owned helper
and readiness rules as desktop: reviewed source, protected helpers, firmware,
external collector and SMU-channel checks. No manual bypass is exposed.

One authenticated session lasts at most 600 seconds and samples every five
seconds. Structured helper output feeds the Dashboard's average, hotspot and
per-chip readings; expired or stopped readings are not presented as live. An
existing BC250-Telemetry collector is displayed without starting a second
sampler. Your own monitor is stopped before another command can use the
terminal; another browser cannot stop your session. Sessions can be recovered
after a page reload and are closed on logout or key rotation.

Legacy installed GDDR6 helpers expect PKEXEC_UID. The web passes its own fixed
Linux UID through sudo's checked command-environment assignment syntax. The
browser cannot choose that value, and sudo policy is not changed. Neither the
web server nor its Python action worker runs as root.
