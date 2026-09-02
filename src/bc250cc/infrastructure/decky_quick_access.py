"""Explicit, reviewable SteamOS/Bazzite Decky bootstrap commands.

Decky Loader is an optional third-party root-plugin environment.  BC250 does
not bundle or silently install it as a regular dependency.  This module only
builds the terminal workflow used after the user accepts the Beta warning in
the GUI; it never downloads or executes anything itself.
"""
from __future__ import annotations

import shlex
from pathlib import Path

DECKY_OFFICIAL_INSTALLER_URL = (
    "https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/"
    "download/install_release.sh"
)
DECKY_OFFICIAL_PRERELEASE_INSTALLER_URL = (
    "https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/"
    "download/install_prerelease.sh"
)
STEAM_RENAMED_INIT_API_BUILD = 1784934043


def _quoted(path: str | Path) -> str:
    return shlex.quote(str(path))


def _frontend_compatibility_repair_lines(*, indent: str = "") -> tuple[str, ...]:
    """Update Decky only when the installed stable build cannot inject Steam UI.

    Steam renamed its stage-one initialization API at build 1784934043. Decky
    3.2.8 is the first upstream release line containing the compatibility fix.
    Keep the stable installer as the default; use the official prerelease only
    while stable is older than that minimum on an affected Steam client.
    """
    prerelease_url = shlex.quote(DECKY_OFFICIAL_PRERELEASE_INSTALLER_URL)
    lines = (
        "steam_build=0",
        "for steam_manifest in \"$HOME\"/.local/share/Steam/package/steam_client*.manifest \"$HOME\"/.steam/steam/package/steam_client*.manifest; do",
        "  test -r \"$steam_manifest\" || continue",
        "  candidate=\"$(sed -n 's/^[[:space:]]*\"version\"[[:space:]]*\"\\([0-9][0-9]*\\)\".*/\\1/p' \"$steam_manifest\")\"",
        "  case \"$candidate\" in ''|*[!0-9]*) continue;; esac",
        "  if (( candidate > steam_build )); then steam_build=$candidate; fi",
        "done",
        "decky_supports_renamed_init_api() {",
        "  local value=\"${1#v}\"",
        "  [[ \"$value\" =~ ^([0-9]+)\\.([0-9]+)\\.([0-9]+) ]] || return 1",
        "  local major=${BASH_REMATCH[1]} minor=${BASH_REMATCH[2]} patch=${BASH_REMATCH[3]}",
        "  (( major > 3 || (major == 3 && (minor > 2 || (minor == 2 && patch >= 8))) ))",
        "}",
        "loader_version=\"$(tr -d '[:space:]' < \"$HOME/homebrew/services/.loader.version\" 2>/dev/null || true)\"",
        f"if (( steam_build >= {STEAM_RENAMED_INIT_API_BUILD} )) && ! decky_supports_renamed_init_api \"$loader_version\"; then",
        "  echo 'Detected a newer Steam initialization API that Decky stable does not support.'",
        "  echo 'Installing the official Decky prerelease compatibility fix.'",
        f"  curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --output \"$workspace/decky-prerelease-install.sh\" {prerelease_url}",
        "  test -s \"$workspace/decky-prerelease-install.sh\" || { echo 'ERROR: official Decky prerelease installer download is empty'; exit 67; }",
        "  chmod 0700 \"$workspace/decky-prerelease-install.sh\"",
        "  echo 'Downloaded prerelease installer SHA-256:'",
        "  sha256sum \"$workspace/decky-prerelease-install.sh\"",
        "  decky_user=\"$(id -un)\"; sudo env UID=0 SUDO_USER=\"$decky_user\" /usr/bin/bash \"$workspace/decky-prerelease-install.sh\"",
        "  loader_version=\"$(tr -d '[:space:]' < \"$HOME/homebrew/services/.loader.version\" 2>/dev/null || true)\"",
        "  decky_supports_renamed_init_api \"$loader_version\" || { echo 'ERROR: Decky compatibility update did not install version 3.2.8 or newer'; exit 67; }",
        "fi",
    )
    return tuple(f"{indent}{line}" for line in lines)


def build_plugin_install_command(installer: str | Path) -> str:
    """Build the explicit local BC250-plugin installation command.

    The caller has already detected a supported Game Mode family and an
    existing Decky directory.
    The local installer independently validates the plugin destination and the
    root-owned BC250 helper before it replaces either payload.
    """
    install_path = Path(installer)
    return "\n".join((
        "set -Eeuo pipefail",
        f"test -x {_quoted(install_path)} || {{ echo 'ERROR: BC250 Quick Access installer is unavailable'; exit 61; }}",
        "echo '== Installing / repairing BC250 Quick Access (Beta) =='",
        f"exec /usr/bin/bash {_quoted(install_path)}",
    ))


def build_decky_bootstrap_command(installer: str | Path) -> str:
    """Build the deliberate official-Decky-then-local-plugin workflow.

    The upstream installer is not pinned or bundled by BC250.  It is fetched
    over HTTPS to a private temporary file and hashed visibly for the
    operator. The calling GUI has already received the user's explicit Beta
    confirmation, so no redundant terminal prompt is required. This
    intentionally avoids the upstream convenience pattern ``curl ... | sh``.
    """
    install_path = Path(installer)
    url = shlex.quote(DECKY_OFFICIAL_INSTALLER_URL)
    return "\n".join((
        "set -Eeuo pipefail",
        "test \"$(id -u)\" -ne 0 || { echo 'ERROR: run this workflow as the Desktop Mode user, not root'; exit 60; }",
        f"test -x {_quoted(install_path)} || {{ echo 'ERROR: BC250 Quick Access installer is unavailable'; exit 61; }}",
        "command -v curl >/dev/null 2>&1 || { echo 'ERROR: curl is required to download the official Decky installer'; exit 62; }",
        f"/usr/bin/bash {_quoted(install_path)} --preflight-immutable-host",
        # Decky's official installer uses jq.  Prepare the missing runtime
        # through the available package manager instead of downloading a
        # second unreviewed binary or failing halfway through installation.
        "if ! command -v jq >/dev/null 2>&1; then "
        "  if test -e /run/ostree-booted || (test -r /etc/os-release && . /etc/os-release && case \"${ID:-}\" in steamos|holo) exit 0;; *) exit 1;; esac); then "
        "    echo 'ERROR: jq is missing on an immutable system. Prepare distribution dependencies and reboot into the updated deployment before installing Decky.'; exit 66; fi; "
        "  if command -v pacman >/dev/null 2>&1; then sudo pacman -S --needed --noconfirm jq; "
        "  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y jq; "
        "  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y jq; "
        "  elif command -v rpm-ostree >/dev/null 2>&1; then sudo rpm-ostree install --idempotent jq; "
        "  else echo 'ERROR: jq is required by the official Decky installer and no supported package manager is available'; exit 66; fi; "
        "fi",
        "command -v jq >/dev/null 2>&1 || { echo 'ERROR: jq is still unavailable; Decky was not downloaded or installed'; exit 66; }",
        "echo '== Game Mode Quick Access Beta =='",
        "echo 'Decky Loader is an external third-party root-plugin service.'",
        "echo 'BC250 will download the official stable Decky installer to a temporary file; it is not bundled or modified by BC250.'",
        f"echo 'Official source: {DECKY_OFFICIAL_INSTALLER_URL}'",
        "echo '== Checking the BC250 protected helper deployment =='",
        "workspace=$(mktemp -d \"${XDG_RUNTIME_DIR:-/tmp}/bc250-decky-beta.XXXXXX\")",
        "trap 'rm -rf -- \"$workspace\"' EXIT",
        f"curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --output \"$workspace/decky-install.sh\" {url}",
        "test -s \"$workspace/decky-install.sh\" || { echo 'ERROR: official Decky installer download is empty'; exit 63; }",
        "chmod 0700 \"$workspace/decky-install.sh\"",
        "echo 'Downloaded installer SHA-256:'",
        "sha256sum \"$workspace/decky-install.sh\"",
        "echo 'Approval was already confirmed in BC250 Control Center; running the official Decky stable installer.'",
        "echo '== Running official Decky stable installer =='",
        # The current upstream script tests ``$UID`` with ``/bin/sh``.  Mint's
        # dash does not define that Bash-only variable, so the script loops on
        # ``[: Illegal number`` and never reaches installation.  Invoke it via
        # the already authenticated root transaction and provide the real
        # desktop account explicitly; this keeps the official payload intact
        # while making the workflow portable across Debian-family shells.
        "decky_user=\"$(id -un)\"; sudo env UID=0 SUDO_USER=\"$decky_user\" /usr/bin/bash \"$workspace/decky-install.sh\"",
        *_frontend_compatibility_repair_lines(),
        "test -d \"$HOME/homebrew/plugins\" || { echo 'ERROR: Decky did not create its plugin directory; BC250 plugin was not installed'; exit 65; }",
        "echo '== Installing BC250 Quick Access into the detected Decky runtime =='",
        f"/usr/bin/bash {_quoted(install_path)}",
        "echo 'OK: restart Steam/Game Mode or reload Decky to discover BC250 Quick Access.'",
    ))


def build_bazzite_decky_bootstrap_command(installer: str | Path) -> str:
    """Prefer Bazzite's native Decky setup with an official fallback.

    Both Bazzite Desktop and Bazzite-Deck expose Steam's Deck UI, but custom or
    older images may omit the native ``setup-decky`` recipe. In that case use
    the same reviewable official installer path as other systemd platforms.
    """
    install_path = Path(installer)
    url = shlex.quote(DECKY_OFFICIAL_INSTALLER_URL)
    return "\n".join((
        "set -Eeuo pipefail",
        "test \"$(id -u)\" -ne 0 || { echo 'ERROR: run this workflow as the Desktop Mode user, not root'; exit 60; }",
        f"test -x {_quoted(install_path)} || {{ echo 'ERROR: BC250 Quick Access installer is unavailable'; exit 61; }}",
        "command -v curl >/dev/null 2>&1 || { echo 'ERROR: curl is required to install Decky'; exit 62; }",
        "test -r /etc/os-release || { echo 'ERROR: /etc/os-release is unavailable'; exit 64; }",
        ". /etc/os-release",
        "test \"${ID:-}\" = bazzite || { echo 'ERROR: the native ujust Decky workflow is available only on Bazzite'; exit 64; }",
        f"/usr/bin/bash {_quoted(install_path)} --preflight-immutable-host",
        "if ! command -v jq >/dev/null 2>&1; then "
        "  if command -v rpm-ostree >/dev/null 2>&1; then sudo rpm-ostree install --idempotent jq; "
        "  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y jq; "
        "  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --needed --noconfirm jq; "
        "  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y jq; "
        "  else echo 'ERROR: jq is required by the official Decky installer and no supported package manager is available'; exit 66; fi; "
        "fi",
        "command -v jq >/dev/null 2>&1 || { echo 'ERROR: jq requires the updated deployment. Reboot and retry Decky installation.'; exit 66; }",
        "echo '== Game Mode Quick Access Beta: Bazzite native Decky setup =='",
        "workspace=$(mktemp -d \"${XDG_RUNTIME_DIR:-/tmp}/bc250-decky-beta.XXXXXX\")",
        "trap 'rm -rf -- \"$workspace\"' EXIT",
        "if command -v ujust >/dev/null 2>&1 && ujust setup-decky status >/dev/null 2>&1; then",
        "  echo 'Using Bazzite native setup-decky recipe.'",
        # The no-argument recipe opens a chooser. The explicit action works in
        # Desktop terminals on both the Desktop and Bazzite-Deck variants.
        "  ujust setup-decky install",
        "  test \"$(ujust setup-decky status 2>/dev/null)\" = install || { echo 'ERROR: Bazzite did not report Decky as installed'; exit 65; }",
        "else",
        "  echo 'Bazzite setup-decky recipe is unavailable; using the official stable Decky installer.'",
        f"  curl --fail --location --proto '=https' --tlsv1.2 --retry 2 --output \"$workspace/decky-install.sh\" {url}",
        "  test -s \"$workspace/decky-install.sh\" || { echo 'ERROR: official Decky installer download is empty'; exit 63; }",
        "  chmod 0700 \"$workspace/decky-install.sh\"",
        "  echo 'Downloaded installer SHA-256:'",
        "  sha256sum \"$workspace/decky-install.sh\"",
        "  decky_user=\"$(id -un)\"; sudo env UID=0 SUDO_USER=\"$decky_user\" /usr/bin/bash \"$workspace/decky-install.sh\"",
        "fi",
        *_frontend_compatibility_repair_lines(),
        "for _attempt in {1..20}; do test -d \"$HOME/homebrew/plugins\" && break; sleep 0.25; done",
        "test -d \"$HOME/homebrew/plugins\" || { echo 'ERROR: Bazzite did not create the Decky plugin directory; BC250 plugin was not installed'; exit 65; }",
        "test -x \"$HOME/homebrew/services/PluginLoader\" || { echo 'ERROR: Decky PluginLoader is missing after installation'; exit 65; }",
        f"/usr/bin/bash {_quoted(install_path)}",
        "echo 'OK: restart Steam/Game Mode or reload Decky to discover BC250 Quick Access.'",
    ))
