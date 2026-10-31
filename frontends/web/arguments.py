"""CLI arguments available even before optional web dependencies are installed."""
from __future__ import annotations

import argparse

from bc250cc.application.system.web_access import DEFAULT_PORT


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='bc250-control-center web',
                                     description='BC250 Control Center local web interface')
    parser.add_argument('--host', default='', help='address to listen on (default: this computer only, or the '
                                                  'local network when it was turned on in Remote access)')
    parser.add_argument('--port', type=int, default=0, help=f'port (default {DEFAULT_PORT})')
    parser.add_argument('--http', action='store_true', help='disable local HTTPS (for development or an SSH tunnel)')
    return parser
