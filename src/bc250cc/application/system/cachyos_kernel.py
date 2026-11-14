"""MastaG's BC-250 kernel stack, as the interface sees it.

The detection and the dependency note live in infrastructure; the desktop and
the TUI go through here so they never import infrastructure directly.
"""

from __future__ import annotations

from bc250cc.infrastructure.cachyos_bc250_kernel import running_bc250_kernel_variant
from bc250cc.infrastructure.cachyos_pahole import DEPENDENCY_NOTE

__all__ = ["DEPENDENCY_NOTE", "running_bc250_kernel_variant"]
