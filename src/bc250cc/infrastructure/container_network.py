"""Rootless containers on a BC-250 that has the governor's gpu_metrics overlay.

The Cyan governor's ``fix-metrics`` mounts a patched file over the GPU's
``gpu_metrics`` in /sys. While anything is mounted over the host's sysfs, the
kernel refuses to mount a *new* sysfs for an unprivileged container ("VFS:
Mount too revealing"), and a rootless Podman container with its own network
namespace needs one. ``podman run`` then stops with ``error mounting "sysfs"``
before running anything, so every build in a container failed on a machine
that was otherwise fine.

On the host network a container bind-mounts the host's /sys instead, which the
kernel allows. The shell function below asks the kernel directly whether it
would allow the mount and prints ``--network=host`` only when it would not, so
the isolated network stays the default and a machine without the overlay is
unchanged.
"""

from __future__ import annotations

FUNCTION_NAME = "bc250_container_network"
VARIABLE = "bc250_net"
SUBID_FUNCTION_NAME = "bc250_podman_subids"

#: Shell function: prints the network option a rootless container needs, if any.
#: Only rootless Podman (the command is exactly ``podman``) is subject to the check:
#: a rootful one mounts sysfs as root and anything else is left alone.
FUNCTION = f"""{FUNCTION_NAME}() {{
  [ "$1" = podman ] || return 0
  command -v unshare >/dev/null 2>&1 || return 0
  # Without user namespaces the answer is another one: leave it to Podman to say so.
  unshare -Urmn true >/dev/null 2>&1 || return 0
  local probe
  probe="$(mktemp -d)" || return 0
  if ! unshare -Urmn mount -t sysfs sysfs "$probe" >/dev/null 2>&1; then
    echo "[INFO] Something is mounted over /sys (the governor's gpu_metrics overlay), so a container cannot get its own: using the host network." >&2
    echo "--network=host"
  fi
  rmdir "$probe" 2>/dev/null || true
}}"""

#: Shell function: stops a rootless build, with the commands that fix it, when
#: the user has no subordinate IDs. R-32e499fb: ``podman info`` and the image
#: download both succeeded, and only unpacking the first layer failed, with
#: "potentially insufficient UIDs or GIDs available in user namespace". Podman's
#: own mapping is read (``podman unshare``), so IDs that come from sssd or LDAP
#: instead of /etc/subuid count too. Only a user with no range at all (Podman
#: maps just the user's own ID) is stopped: a small range may still be enough
#: for an image, and when it is not, Podman's own error names the same code.
SUBID_FUNCTION = f"""{SUBID_FUNCTION_NAME}() {{
  [ "$1" = podman ] || return 0
  [ "$(id -u)" -ne 0 ] || return 0
  local kind map mapped user start listed=1
  for kind in uid gid; do
    map="$(podman unshare cat "/proc/self/${{kind}}_map" 2>/dev/null)" || return 0
    mapped="$(printf '%s\\n' "$map" | awk '{{n += $3}} END {{print n + 0}}')"
    [ "$mapped" -gt 1 ] && continue
    user="$(id -un)"
    grep -qE "^($user|$(id -u)):" /etc/subuid 2>/dev/null || listed=0
    grep -qE "^($user|$(id -u)):" /etc/subgid 2>/dev/null || listed=0
    echo "ERROR: Rootless Podman has no subordinate user and group IDs for $user, so it cannot unpack container images (insufficient UIDs or GIDs available in user namespace)."
    if [ "$listed" -eq 1 ]; then
      echo "They are listed in /etc/subuid and /etc/subgid, but Podman has not picked them up yet. Run this, then start the action again:"
      echo "  podman system migrate"
    else
      start="$(awk -F: '{{e = $2 + $3; if (e > m) m = e}} END {{print (m > 100000 ? m : 100000)}}' /etc/subuid /etc/subgid 2>/dev/null)"
      echo "Run these two commands, then start the action again:"
      echo "  sudo usermod --add-subuids $start-$((start + 65535)) --add-subgids $start-$((start + 65535)) $user"
      echo "  podman system migrate"
    fi
    return 1
  done
  return 0
}}"""


#: Both functions; ``setup_lines`` uses them, and a caller that inlines the
#: definitions takes this.
FUNCTIONS = FUNCTION + "\n" + SUBID_FUNCTION


def setup_lines(podman: str = "podman") -> tuple[str, str]:
    """The functions, and the line that checks Podman and sets ``$bc250_net``.

    ``podman`` is shell text: a command (``podman``) or a variable that holds
    one (``"$bc250_podman"``). The line stops the script when rootless Podman
    has no subordinate IDs, before any image is downloaded.
    """
    return FUNCTIONS, (
        f"{SUBID_FUNCTION_NAME} {podman} || exit 1; "
        f'{VARIABLE}="$({FUNCTION_NAME} {podman})"'
    )
