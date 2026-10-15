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


def setup_lines(podman: str = "podman") -> tuple[str, str]:
    """The function and the line that sets ``$bc250_net`` for the Podman command in ``podman``.

    ``podman`` is shell text: a command (``podman``) or a variable that holds
    one (``"$bc250_podman"``).
    """
    return FUNCTION, f'{VARIABLE}="$({FUNCTION_NAME} {podman})"'
