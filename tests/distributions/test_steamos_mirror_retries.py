"""Slow SteamOS mirrors must not bypass package verification or leave a lock retry loop."""
import os
import subprocess
from pathlib import Path

import pytest

GUARD = Path('packaging/common/os-scripts/common/steamos-root.sh').resolve()


@pytest.mark.parametrize('failure,expected_calls,expected_status', [
    ('failed retrieving file: Operation too slow', 2, 0),
    ('failed to synchronize all databases (download library error)', 2, 0),
    ('could not lock database: File exists', 1, 1),
    ('invalid or corrupted database (PGP signature)', 1, 1),
    ('persistent download library error', 3, 1),
])
def test_database_refresh_retries_transport_only(tmp_path, failure, expected_calls, expected_status):
    count = tmp_path / 'calls'
    script = r'''
source "$GUARD"
sleep() { :; }
bc250_steamos_root_command() {
  printf '%s\n' "$*" >> "$COUNT"
  if [[ "$(wc -l < "$COUNT")" -eq 1 || "$FAILURE" == persistent* ]]; then
    printf '%s\n' "$FAILURE"
    return 1
  fi
}
bc250_steamos_sync_databases
'''
    result = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
                            env={**os.environ, 'GUARD': str(GUARD), 'COUNT': str(count), 'FAILURE': failure})
    assert result.returncode == expected_status, result.stdout + result.stderr
    calls = count.read_text().splitlines()
    assert len(calls) == expected_calls
    assert all('--disable-download-timeout' in call and '-Syy --noconfirm' in call for call in calls)
    assert all('--disable-signature' not in call for call in calls)
