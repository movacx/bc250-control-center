# Frontends

BC250 Control Center provides three interactive interfaces and a command-line
entry point. They present application results and dispatch user intent;
hardware rules and system access remain under `src/bc250cc`.

| Frontend | Entry point | Implementation |
| --- | --- | --- |
| Desktop | `bc250-control-center` | PyQt6 pages, components, embedded console, themes and translations in `desktop/` |
| TUI | `bc250-control-center-tui` or `bc250-control-center tui` | curses pages, keyboard/mouse handling and operation console in `tui/` |
| Web | **Remote access** in the desktop app or TUI | Python HTTPS backend and Compose browser interface in `web/` |
| CLI | `bc250-control-center-cli` | Command parser and non-graphical operations in `cli.py` |

The optional Game Mode interface lives separately in
[`integrations/decky`](../integrations/decky/bc250-quick-access/README.md).

## Terminal

From a checkout:

```sh
scripts/entrypoints/bc250-control-center-tui
scripts/entrypoints/bc250-control-center-tui --page gpu --theme mono
```

`app.py` starts the application, `screen.py` handles rendering and input,
`layout.py` and `content.py` describe presentation, `console.py` manages workflow
output, and `pages/` contains the sections. The TUI uses the shared application
services; it is not a second hardware implementation. Python needs `curses`
and `psutil`. See the root README for terminal-only installation and key bindings.

## Web

`web/app/` contains the Kotlin Multiplatform pages, shared with the Android app. `web/dist/` is the
compiled application shipped to users. `server.py` serves HTTPS and enforces
sessions and request checks; `actions.py` defines the accepted operations;
`data.py` provides monitoring data. Private workers run operations as the normal
Linux user and invoke installed privileged helpers through system authorization.

Rebuild after changing its source:

```sh
scripts/development/build-web.sh
```

The build requires a JDK; running the server requires Python and
`requirements-web.txt` only. The built files are not committed: after a build,
`scripts/development/empaquetar_web.py` writes the archive to upload to the
`web-builds` release and records it in `web/web-build.json`, which is committed.
Installers and packages download exactly that archive and verify it. See the [root README](../README.md#web-interface)
for connection and authorization details.

## Shared boundaries

All interfaces use `src/bc250cc/application/` for operations and share the
configuration, telemetry adapters and privileged helpers. Browser preferences
such as theme and language are local to that browser. A frontend confirmation
is a usability step; argument validation and permission checks must also happen
at the service/helper boundary.
