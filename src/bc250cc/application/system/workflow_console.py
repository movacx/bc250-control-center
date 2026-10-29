"""What a frontend needs to run reviewed workflows in a console it draws itself.

The repositories hand every workflow to the registered embedded launcher before
they try a terminal emulator, so a frontend that registers one keeps them all.
"""

from bc250cc.infrastructure.polkit_session import TERMINAL_AUTH_ENV
from bc250cc.infrastructure.terminal_plan import set_translator
from bc250cc.infrastructure.terminal_repository import (
    EmbeddedTerminalRequest,
    TerminalLaunchResult,
    set_embedded_terminal_launcher,
)
from bc250cc.infrastructure.terminal_transcript import TranscriptLog

__all__ = ["TERMINAL_AUTH_ENV", "EmbeddedTerminalRequest", "TerminalLaunchResult", "TranscriptLog",
           "set_embedded_terminal_launcher", "set_translator"]
