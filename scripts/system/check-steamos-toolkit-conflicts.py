#!/usr/bin/env python3
"""Installed read-only check used at toolkit component mutation boundaries."""
import os
import stat
import sys
from pathlib import Path

# The same protected runtime is installed by packages and local/source installs.
# -I prevents a caller's PYTHONPATH or user site from supplying privileged code.
runtime = Path(__file__).resolve().parent / 'lib/bc250_steamos_toolkit_runtime.zip'
try:
    metadata = runtime.stat(follow_symlinks=False)
except OSError:
    raise SystemExit('ERROR: Privileged Toolkit runtime is missing. Reinstall Control Center helpers.') from None
if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022
        or os.geteuid() == 0 and metadata.st_uid != 0):
    raise SystemExit('ERROR: Privileged Toolkit runtime is not protected.')
sys.path.insert(0, str(runtime))

from bc250cc.infrastructure.steamos_graphics_ownership import require_graphics_provider  # noqa: E402
from bc250cc.infrastructure.steamos_toolkit_conflicts import require_no_native_conflicts  # noqa: E402

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check-steamos-toolkit-conflicts.py COMPONENT')
    try:
        component = sys.argv[1]
        if component in {'graphics', 'all'}:
            require_graphics_provider('real-toolkit', all_kernels=component == 'all')
        if component == 'alternative-graphics':
            require_graphics_provider('keyboardspecialist')
        elif component != 'graphics':
            require_no_native_conflicts(component)
    except (OSError, ValueError, RuntimeError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(79)
