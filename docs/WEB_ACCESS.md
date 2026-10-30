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
web header, then **Connect SSH**. Authentication is handled by the installed
OpenSSH client: an existing permitted SSH key/agent may work, otherwise the
Linux password is requested in the web dialog. No password is retained for
later commands.

The SSH destination is fixed to `127.0.0.1` and the account running Control
Center. The browser cannot choose a host, account, shell command or executable.
Host keys are pinned from root-owned, non-writable `/etc/ssh/ssh_host_*_key.pub`
files. Unknown or changed keys are rejected; there is no automatic acceptance
or `StrictHostKeyChecking=no` fallback. Custom server configurations without
those public key files need their local host-key setup corrected first.

After SSH login, a private worker runs as that user. Its protocol accepts only
the existing action catalog, job status, authentication input, cancellation and
closing the session. It is not a general-purpose terminal. CPU, GPU and CU
requests still pass through their normal services and root-owned helpers.

**SSH login does not grant root access.** Sudo and Polkit can still ask for
permission. Their prompts appear in the operation panel in the phone's browser,
with password input shown when the terminal disables echo. The existing Polkit
policy is unchanged; its own authorization retention rules still apply.
Confirmations and access-key reauthentication for dangerous operations remain
mandatory. SSH is optional: the original local execution path is available
when no SSH session is connected.

SSH encrypts the connection between the web process and the SSH service. HTTPS
protects the separate phone-to-web connection. Using SSH internally does not
make an HTTP page encrypted.

Each browser owns its SSH session and operation output. Another browser cannot
read its console, type into its job or cancel it. The server serializes hardware
jobs across browsers. Logging out, key rotation and session expiry close the SSH
connection. An unused SSH connection expires after 15 minutes.

## Phone layout

The bottom bar reaches Dashboard, CPU, CU, GPU and Sensors. Settings and fans
are in the menu. CPU/GPU show live readings before their controls; profiles have
separate, touch-sized edit buttons. Secondary and experimental controls are
expandable. CU rows show five WGP pairs each, the selected total and engine
balance. Selecting a preset or toggling a pair only edits the draft; applying
still needs confirmation.

Sensors have search, category filters and list/graph layouts. On a phone the
main list shows name and current value, with a button to expose min/average/max.
CPU, GPU, VRAM, RAM, disk and network retain their resource views. Polling pauses
in a hidden tab; stale responses from a previous view are discarded.

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
password rejection, browser isolation, action allowlisting, avoiding action
retries on TypeError, and the real SSH worker against an isolated sshd with
throwaway keys. The SSH integration test skips when OpenSSH server/client tools
are unavailable. It does not start or reconfigure the system SSH daemon.
