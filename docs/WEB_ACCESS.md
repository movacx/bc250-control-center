# Web control from a phone

The web interface runs on the BC-250. It reuses Control Center's application
services and privileged helpers. It needs no CDN, external font, cloud account,
Node runtime or additional Python package. Node is used only to rebuild the
frontend.

## Open it

1. In the desktop app, open **Remote access** and start the web interface.
2. Enable **Reachable from the local network** and keep **HTTPS** enabled.
3. Press **Connect with QR**, select the board's address if more than one is
   listed, and scan from a phone on the same network. The QR contains the access
   key: treat it like the key shown on screen.
4. The first visit uses the board's self-signed certificate. Verify that it is
   your board before accepting the browser's certificate exception. The SHA-256
   fingerprint is shown in the QR dialog. No public certificate authority or
   external service is contacted.

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

## SSH authorization in the browser

Start the board's SSH server from **Remote access** first. Press **SSH** in the
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

## Phone layout

The bottom bar reaches Dashboard, CPU, CU, GPU and Sensors. Settings and fans
are in the menu. CPU/GPU profiles have separate, touch-sized edit buttons. GPU frequencies
are changed through profiles; the manual frequency slider belongs to desktop.
The SSH button appears only inside the Dashboard board card; repeated page
headings and the CU overview card are omitted. Secondary and experimental controls are
expandable. CU rows show five WGP pairs each and warn about engine imbalance. Selecting a preset or toggling a pair only edits the draft; applying
still needs confirmation.

The voltage laboratory expands an in-page workspace:
Gentle, Moderate, High and Custom modes; a scrollable table of active points;
and Frequency, Current, Selected and delta-from-packaged-default columns.
The fixed footer previews changed points and peak voltage before review.
Draft values survive polling, mode changes, closing the panel and cancelling
the confirmation. Additional settings retain all shared levels 0–6. Custom
edits use the shared 600–1210 mV bounds. The service rechecks active frequencies and rejects
a decreasing custom curve before any helper call. Restoring defaults also
comments the high-frequency points, using the existing backup/restart workflow.
Oberon voltage controls remain unavailable because it has no validated curve.

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
the visible list. Graphs show one focused sensor with a picker for the other
selected traces. Desktop web retains the table and multiple plots.

Mobile plots use fewer axis labels and separate numerical readouts rather
than overlapping labels on the curve. Touch or drag a plot to inspect a
sample; arrow keys move the cursor and Escape returns to live readings. The
mobile time axis grows with the available history up to two minutes; it does
not fill missing history with synthetic samples. Per-core heat maps become
readable rows with individual history lines and current values on phones.

Profile editing and routine hardware reviews happen in the page. Higher-risk
actions still require an explicit confirmation dialog. Mobile operations start
in a compact progress bar and open their console when authentication is needed
or an operation fails. Finished progress can be dismissed directly. The
voltage editor expands in its own card and keeps drafts across preview changes.
Navigating between pages resets the main scroll position.

Themes and language are browser-local. The shared desktop catalogs supply all
30 languages; changing the web preference does not alter desktop settings.

## Development and verification

```sh
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
