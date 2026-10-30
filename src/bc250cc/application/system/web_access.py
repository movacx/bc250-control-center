"""The local web interface (its settings, key and user service) for the frontends."""

from bc250cc.infrastructure.web_control import (
    DEFAULT_PORT,
    access_key,
    options,
    pairing_svg,
    read_settings,
    save_settings,
    set_autostart,
    ssh_target,
    start,
    status,
    stop,
    tls_certificate,
    write_pid,
)

__all__ = ["DEFAULT_PORT", "access_key", "options", "read_settings", "save_settings", "set_autostart", "start", "status",
           "stop", "write_pid", "pairing_svg", "ssh_target", "tls_certificate"]
