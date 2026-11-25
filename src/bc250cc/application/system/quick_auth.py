"""What every interface says about running the hardware helpers without the password."""

from bc250cc.infrastructure.quick_auth import enabled

__all__ = ["DETAIL", "TITLE", "WARNING", "enabled"]

TITLE = "Actions without password"
DETAIL = "CPU, compute units, GPU and fans stop asking for the Linux password. Everything else keeps asking."
WARNING = (
    "Anyone using your session, or a paired device with hardware control, will be able to run these actions. "
    "You can turn it off at any time."
)
