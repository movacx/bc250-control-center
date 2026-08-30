"""Distro metadata; capabilities decide feature availability."""

from .identity import DistroIdentity, read_os_release

__all__ = ["DistroIdentity", "read_os_release"]
