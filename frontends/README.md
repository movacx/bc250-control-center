# Frontends

BC250 Control Center provides three interactive interfaces and a command-line
entry point. They present application results and dispatch user intent;
hardware rules and system access remain under `src/bc250cc`.

| Frontend | Entry point | Implementation |
| --- | --- | --- |
| Desktop | `bc250-control-center` | PyQt6 pages, components, embedded console, themes and translations in `desktop/` |
| TUI | `bc250-control-center-tui` or `bc250-control-center tui` | curses pages, keyboard/mouse handling and operation console in `tui/` |
| Web | **Remote access** in the desktop app or TUI | Python HTTPS backend and React browser interface in `web/` |
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

`web/app/src/` contains the React pages and shared controls. `web/dist/` is the
compiled application shipped to users. `server.py` serves HTTPS and enforces
sessions and request checks; `actions.py` defines the accepted operations;
`data.py` provides monitoring data. Private workers run operations as the normal
Linux user and invoke installed privileged helpers through system authorization.

Rebuild after changing React source:

```sh
scripts/development/build-web.sh
```

The build requires Node.js and npm; running the server requires Python and
`requirements-web.txt`, without a Node.js runtime. Commit the rebuilt assets
alongside their source changes. See the [root README](../README.md#web-interface)
for connection and authorization details.

## Shared boundaries

All interfaces use `src/bc250cc/application/` for operations and share the
configuration, telemetry adapters and privileged helpers. Browser preferences
such as theme and language are local to that browser. A frontend confirmation
is a usability step; argument validation and permission checks must also happen
at the service/helper boundary.
