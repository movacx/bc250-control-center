"""Operating-system-specific integration strategies for BC250 Control Center."""

from .factory import create_os_repository
from .detector import OSInfo, detect_os_info

__all__ = ["OSInfo", "create_os_repository", "detect_os_info"]
