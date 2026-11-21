#!/usr/bin/env python3
"""Build the small, stdlib-only Python payload used by installed root helpers."""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / 'privileged/lib/bc250_steamos_toolkit_runtime.zip'
MODULES = (
    'infrastructure/hardware_identity.py', 'infrastructure/steamos_readonly.py',
    'infrastructure/steamos_root_guard.py',
    'infrastructure/steamos_real_toolkit.py', 'infrastructure/steamos_real_toolkit_runtime.py',
    'infrastructure/steamos_real_toolkit_recovery.py',
    'infrastructure/steamos_toolkit_conflicts.py', 'infrastructure/steamos_graphics_ownership.py',
    'shared/errors.py', 'shared/error_catalog.py',
)


def build_payload() -> bytes:
    files = {'bc250cc/' + name: (ROOT / 'src/bc250cc' / name).read_bytes() for name in MODULES}
    # Do not import the desktop application's facade or optional dependencies
    # under sudo. These namespace initializers intentionally have no imports.
    for package in ('bc250cc', 'bc250cc/infrastructure', 'bc250cc/shared'):
        files[package + '/__init__.py'] = b'"""Isolated Control Center privileged runtime."""\n'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return output.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    payload = build_payload()
    if args.check:
        if not DESTINATION.is_file() or DESTINATION.read_bytes() != payload:
            raise SystemExit('Stale privileged Toolkit runtime; run scripts/development/generate_steamos_toolkit_runtime.py')
    else:
        DESTINATION.write_bytes(payload)
