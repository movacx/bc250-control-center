"""The package manager's lock and the kernel headers, read from files, for every frontend."""

from bc250cc.infrastructure.kernel_headers import headers_state
from bc250cc.infrastructure.pacman_lock import lock_state

__all__ = ["headers_state", "lock_state"]
