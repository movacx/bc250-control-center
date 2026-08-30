#!/usr/bin/env bash
set -Eeuo pipefail

OFFICIAL_REPOSITORY="https://github.com/movacx/bc250-control-center.git"
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
SCRIPT_ROOT="$(dirname "$SCRIPT_DIR")"
UPDATE_CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center"
UPDATE_SOURCE="$UPDATE_CACHE_ROOT/update-source"
SOURCE_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage: update-local.sh [--source PATH] [--prefix PATH]

Updates BC250 Control Center in place without touching user configuration,
hardware profiles, community tool repositories, or enabled services.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      [[ $# -ge 2 ]] || { echo "ERROR: --source requires a path" >&2; exit 2; }
      SOURCE_OVERRIDE="$2"
      shift 2
      ;;
    --prefix)
      [[ $# -ge 2 ]] || { echo "ERROR: --prefix requires a path" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${PREFIX:-}" ]]; then
  case "$SCRIPT_PATH" in
    */share/bc250-control-center/scripts/update-local.sh)
      PREFIX="${SCRIPT_PATH%/share/bc250-control-center/scripts/update-local.sh}"
      ;;
    *) PREFIX="$HOME/.local" ;;
  esac
fi

detect_package_owner() {
  local candidate owner=""
  # Do not trust a single launcher sentinel: a stale/replaced launcher must not
  # let the Git updater overwrite an otherwise package-managed application.
  for candidate in \
    "$PREFIX/bin/bc250-control-center" \
    "$PREFIX/share/bc250-control-center/frontends/desktop/main.py" \
    "$PREFIX/share/doc/bc250-control-center/README.md"; do
    # Query package databases even when a file was manually removed.  Package
    # ownership is metadata, not a property of the current filesystem entry.
    if command -v rpm >/dev/null 2>&1; then
      owner="$(rpm -qf "$candidate" 2>/dev/null || true)"
      if [[ -n "$owner" && "$owner" != *"is not owned by any package"* ]]; then
        printf 'rpm:%s\n' "$owner"
        return 0
      fi
    fi

    if command -v pacman >/dev/null 2>&1; then
      owner="$(pacman -Qo "$candidate" 2>/dev/null || true)"
      if [[ "$owner" == *" is owned by "* ]]; then
        printf 'pacman:%s\n' "${owner##* is owned by }"
        return 0
      fi
    fi

    if command -v dpkg-query >/dev/null 2>&1; then
      owner="$(dpkg-query -S "$candidate" 2>/dev/null | head -n1 || true)"
      if [[ "$owner" == *:* ]]; then
        printf 'dpkg:%s\n' "${owner%%:*}"
        return 0
      fi
    fi
  done
  return 1
}

refuse_package_managed_update() {
  local ownership manager package
  ownership="$(detect_package_owner || true)"
  [[ -n "$ownership" ]] || return 0
  manager="${ownership%%:*}"
  package="${ownership#*:}"

  echo "ERROR: this BC250 Control Center installation is owned by the system package manager ($package)." >&2
  echo "The Git in-place updater will not overwrite package-managed files under $PREFIX." >&2
  case "$manager" in
    rpm)
      if command -v rpm-ostree >/dev/null 2>&1; then
        echo "Install the newer BC250 Control Center RPM with rpm-ostree, then reboot:" >&2
        echo "  sudo rpm-ostree install ./bc250-control-center-NEW_VERSION.rpm" >&2
        echo "  systemctl reboot" >&2
      else
        echo "Install/upgrade the newer RPM with your RPM package manager, for example:" >&2
        echo "  sudo dnf upgrade ./bc250-control-center-NEW_VERSION.rpm" >&2
      fi
      ;;
    pacman)
      echo "Upgrade BC250 Control Center through pacman/AUR instead of overwriting its files." >&2
      ;;
    dpkg)
      echo "Install/upgrade the newer .deb through apt/dpkg instead of overwriting its files." >&2
      ;;
  esac
  exit 6
}

validate_source() {
  local source="$1" origin dirty
  [[ -d "$source/.git" ]] || { echo "ERROR: update source is not a Git checkout: $source" >&2; return 1; }
  [[ -x "$source/scripts/install-local.sh" \
    && -d "$source/frontends/desktop" \
    && -d "$source/src/bc250cc" \
    && -d "$source/frontends" \
    && -d "$source/privileged" \
    && -d "$source/packaging/common" \
    && -d "$source/privileged/helpers" ]] || {
    echo "ERROR: incomplete BC250 Control Center source tree: $source" >&2
    return 1
  }
  origin="$(git -C "$source" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    https://github.com/movacx/bc250-control-center|https://github.com/movacx/bc250-control-center.git|git@github.com:movacx/bc250-control-center.git) ;;
    *) echo "ERROR: refusing an update from an unexpected origin: ${origin:-missing}" >&2; return 1 ;;
  esac
  dirty="$(git -C "$source" status --porcelain --untracked-files=normal)"
  [[ -z "$dirty" ]] || {
    echo "ERROR: the update checkout contains local changes: $source" >&2
    echo "Move or commit those changes before updating." >&2
    return 1
  }
}

refuse_package_managed_update

if [[ -n "$SOURCE_OVERRIDE" ]]; then
  UPDATE_SOURCE="$(readlink -f "$SOURCE_OVERRIDE")"
elif [[ -d "$SCRIPT_ROOT/.git" ]]; then
  UPDATE_SOURCE="$SCRIPT_ROOT"
fi

if [[ -d "$UPDATE_SOURCE/.git" ]]; then
  validate_source "$UPDATE_SOURCE"
  echo "== Updating existing BC250 Control Center source =="
  git -C "$UPDATE_SOURCE" fetch --prune origin
  git -C "$UPDATE_SOURCE" pull --ff-only
else
  command -v git >/dev/null 2>&1 || { echo "ERROR: git is required for in-place updates" >&2; exit 3; }
  mkdir -p "$UPDATE_CACHE_ROOT"
  [[ ! -e "$UPDATE_SOURCE" ]] || {
    echo "ERROR: update cache exists but is not a valid Git checkout: $UPDATE_SOURCE" >&2
    exit 4
  }
  echo "== Downloading BC250 Control Center update source =="
  git clone --depth 1 "$OFFICIAL_REPOSITORY" "$UPDATE_SOURCE"
  validate_source "$UPDATE_SOURCE"
fi

echo "== Applying the update in place =="
echo "Configuration, profiles, services, and ResourceTools are preserved."
if [[ "$PREFIX" == /usr || "$PREFIX" == /usr/local ]]; then
  command -v sudo >/dev/null 2>&1 || { echo "ERROR: sudo is required for $PREFIX" >&2; exit 5; }
  sudo env PREFIX="$PREFIX" "$UPDATE_SOURCE/scripts/install-local.sh"
else
  env PREFIX="$PREFIX" "$UPDATE_SOURCE/scripts/install-local.sh"
fi

echo "== Update completed successfully =="
echo "Close and reopen BC250 Control Center to use the updated code."
