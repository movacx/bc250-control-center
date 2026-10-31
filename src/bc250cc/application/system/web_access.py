"""The local web interface (its settings, key and user service) for the frontends."""

from bc250cc.infrastructure.web_control import (
    DEFAULT_PORT,
    access_key,
    configure,
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
from bc250cc.infrastructure.web_control import (
    _command as launch_command,
)
from bc250cc.infrastructure.web_devices import (
    deadline,
    devices,
    revoke,
    revoke_all,
    set_control,
    set_lifetime,
)
from bc250cc.infrastructure.web_runtime import require_supported_version
from bc250cc.infrastructure.web_tls import trust_certificate

__all__ = ["launch_command", "require_supported_version", "DEFAULT_PORT", "access_key", "options", "read_settings", "save_settings", "set_autostart", "start", "status",
           "stop", "write_pid", "pairing_svg", "ssh_target", "tls_certificate", "configure", "devices", "revoke", "revoke_all", "set_control", "set_lifetime", "deadline", "trust_certificate"]
