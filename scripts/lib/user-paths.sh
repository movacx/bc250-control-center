#!/usr/bin/env bash

# Shared XDG path resolution for local install, upgrade and uninstall scripts.
# Keep this file side-effect free: callers decide what should be created or
# removed.
bc250_resolve_user_paths() {
  if [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
    echo "Error: HOME must be an absolute path." >&2
    return 64
  fi

  BC250_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
  BC250_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
  BC250_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
  BC250_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
  local root
  for root in "$BC250_CONFIG_HOME" "$BC250_DATA_HOME" "$BC250_STATE_HOME" "$BC250_CACHE_HOME"; do
    if [[ "$root" != /* || "$root" == / ]]; then
      echo "Error: refusing unsafe XDG root: $root" >&2
      return 64
    fi
  done

  BC250_USER_CONFIG_DIR="$BC250_CONFIG_HOME/bc250-control-center"
  BC250_USER_DATA_DIR="$BC250_DATA_HOME/bc250-control-center"
  BC250_USER_STATE_DIR="$BC250_STATE_HOME/bc250-control-center"
  BC250_USER_CACHE_DIR="$BC250_CACHE_HOME/bc250-control-center"
  BC250_LEGACY_CONFIG_DIR="$BC250_CONFIG_HOME/modo-juego-ram"
  BC250_LEGACY_DATA_DIR="$BC250_DATA_HOME/modo-juego-ram"
  BC250_LEGACY_CACHE_DIR="$BC250_CACHE_HOME/modo-juego-ram"
  BC250_LEGACY_QT_CONFIG_DIR="$BC250_CONFIG_HOME/BC250ControlCenter"
  BC250_FSR4_DIR="$HOME/.local/share/bc250-fsr4"
  BC250_DECKY_PLUGIN_DIR="${DECKY_PLUGIN_ROOT:-$HOME/homebrew/plugins}/bc250-quick-access"
}
