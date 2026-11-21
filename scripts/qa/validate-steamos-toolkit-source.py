#!/usr/bin/env python3
"""Check a downloaded Toolkit archive against the adapter, without executing its installers.

Use it on the revision users will receive (the archive the application caches is named
after its commit). The inventory is the snapshot reviewed when the rows were chosen;
differences from it are reported as notes for a human to look at, not as failures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from bc250cc.infrastructure import steamos_real_toolkit as provider  # noqa: E402


def validate(archive: Path, revision: str) -> dict:
    inventory = json.loads((ROOT / 'docs/steamos-real-toolkit-inventory.json').read_text())
    report = {
        'schema_version': 1, 'status': 'passed', 'revision': revision, 'notes': [],
        'inventory_revision': inventory['revision'],
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'adapter_sha256': {
            name: hashlib.sha256((ROOT / 'src/bc250cc/infrastructure' / name).read_bytes()).hexdigest()
            for name in ('steamos_real_toolkit.py', 'steamos_real_toolkit_recovery.py')
        },
        'guarded_functions': len(provider.GUARDED_FUNCTIONS),
    }
    # prepare_snapshot checks the extraction boundaries and the entrypoint's
    # structure, adapts it, and checks its syntax.
    with tempfile.TemporaryDirectory(prefix='bc250-toolkit-source-') as folder:
        prepared = provider.prepare_snapshot(archive, Path(folder) / 'prepared', revision)
        external = sorted(path.name for path in (prepared / 'external').iterdir())
        if external != sorted(inventory['external_components']):
            report['notes'].append('Bundled components differ from the inventory snapshot: '
                                   + ', '.join(sorted(set(external) ^ set(inventory['external_components']))))
        report['external_components'] = external
        files = sorted(path for path in prepared.rglob('*') if path.is_file())
        report['file_count'] = len(files)
        checked, failures = [], []
        for path in files:
            with path.open('rb') as stream:
                first = stream.readline(256)
            if path.suffix != '.sh' and not (first.startswith(b'#!') and b'bash' in first):
                continue
            # Parse only. No upstream command, shell body or installer is run.
            result = subprocess.run(['/usr/bin/bash', '-n', str(path)],
                                    capture_output=True, text=True, timeout=15)
            relative = str(path.relative_to(prepared))
            checked.append(relative)
            if result.returncode:
                failures.append({'path': relative, 'error': result.stderr.strip()})
        report.update(shell_count=len(checked), shell_checks=checked,
                      failures=failures)
        if failures:
            report['status'] = 'failed'
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Downloaded source archive, named <commit>.tar.gz')
    parser.add_argument('--revision', help='Full commit hash (default: taken from the archive name)')
    parser.add_argument('--report', type=Path, help='Write the detailed JSON result, including failures')
    args = parser.parse_args()
    try:
        revision = args.revision or args.archive.name.removesuffix('.tar.gz')
        report = validate(args.archive, revision)
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        report = {'schema_version': 1, 'status': 'failed', 'revision': args.revision or args.archive.name,
                  'error': str(error)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'revision', 'file_count', 'shell_count', 'error')
                      if key in report}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
