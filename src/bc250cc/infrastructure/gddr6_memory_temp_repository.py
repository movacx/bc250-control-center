"""Client-side orchestration for the reviewed GDDR6 memory-temperature tool.

Mirrors the CPU core-unlock pattern: this module never talks to SMU hardware
itself. It locates the packaged, root-owned helper, validates the desktop
user's own checkout of the reviewed upstream tool, and builds the exact
pkexec argv the helper expects. All hardware access happens inside
bc250-gddr6-temp-helper, run through Polkit.
"""
from __future__ import annotations

import os
from pathlib import Path

from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOLS
from bc250cc.infrastructure.gddr6_memory_temp_trust import REVIEWED_REVISION
from bc250cc.infrastructure.hardware_identity import is_bc250_platform
from bc250cc.infrastructure.polkit_session import pkexec_argv

GDDR6_MEMORY_TEMP_REPOSITORY = EXTERNAL_TOOLS["gddr6_memory_temp"].upstream
GDDR6_MEMORY_TEMP_DIRECTORY = "bc250-memory-temperature"
GDDR6_MEMORY_TEMP_ORIGINS = frozenset({
    GDDR6_MEMORY_TEMP_REPOSITORY,
    f"{GDDR6_MEMORY_TEMP_REPOSITORY}.git",
})


class Gddr6MemoryTempRepository:
    def _gddr6_temp_helper_path(self):
        """Return the installed root-owned GDDR6 memory-temperature launcher."""
        candidates = (
            Path('/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-gddr6-temp-helper'),
        )
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if os.access(candidate, os.X_OK):
                return str(candidate)
        return ''

    def _gddr6_temp_repository(self):
        return self._tool_dir() / GDDR6_MEMORY_TEMP_DIRECTORY

    def _gddr6_temp_repository_state(self, repository):
        """Return (origin, clean, revision_matches) for the desktop user's checkout."""
        if not (repository / '.git').is_dir():
            return '', False, False
        git = ['git', '-C', str(repository)]
        rc_origin, origin, _ = self._ejecutar(git + ['remote', 'get-url', 'origin'])
        rc_status, status, _ = self._ejecutar(
            git + ['status', '--porcelain', '--untracked-files=all']
        )
        rc_head, head, _ = self._ejecutar(git + ['rev-parse', 'HEAD'])
        clean = rc_status == 0 and not status.strip()
        revision_matches = rc_head == 0 and head.strip() == REVIEWED_REVISION
        return (origin.strip() if rc_origin == 0 else ''), clean, revision_matches

    def estado_gddr6_memory_temp(self):
        """Read-only status for the GDDR6 memory-temperature inspection page."""
        repository = self._gddr6_temp_repository()
        origin, clean, revision_matches = self._gddr6_temp_repository_state(repository)
        repository_ready = bool(
            origin in GDDR6_MEMORY_TEMP_ORIGINS and clean and revision_matches
        )
        return {
            'hardware_detected': is_bc250_platform(),
            'helper_ready': bool(self._gddr6_temp_helper_path()),
            'repository_ready': repository_ready,
            'payload_present': (repository / 'SMUPayload.bin').is_file(),
            'repository_path': str(repository),
            'reference_url': GDDR6_MEMORY_TEMP_REPOSITORY,
            'reviewed_revision': REVIEWED_REVISION,
            'integration': 'official-upstream-clone',
            'volatile_after_power_off': True,
        }

    def comando_preparar_gddr6_memory_temp(self):
        """Clone/update the reviewed checkout in the embedded terminal panel."""
        repository = self._gddr6_temp_repository()
        command = self._hardware_source_checkout_command(
            GDDR6_MEMORY_TEMP_REPOSITORY, repository
        )
        return self._abrir_terminal(command, 'BC250 GDDR6 memory temperature')

    def _gddr6_temp_pkexec_command(self, action):
        helper = self._gddr6_temp_helper_path()
        if not helper:
            raise RuntimeError(
                'The privileged GDDR6 memory-temperature helper is not installed. '
                'Reinstall BC250 Control Center before using this action.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError(
                'polkit/pkexec was not found. It is required for this action.'
            )
        repository = self._gddr6_temp_repository()
        if not (repository / '.git').is_dir():
            raise RuntimeError(
                'The official bc250-memory-temperature repository is not prepared. '
                'Clone it from this page before using this action.'
            )
        origin, clean, revision_matches = self._gddr6_temp_repository_state(repository)
        if origin not in GDDR6_MEMORY_TEMP_ORIGINS or not clean or not revision_matches:
            raise RuntimeError(
                'The official bc250-memory-temperature clone did not pass origin, '
                'revision, and integrity validation.'
            )
        return pkexec_argv('pkexec', helper, '--repo', str(repository), '--action', action)

    def comando_verificar_gddr6_memory_temp(self):
        return self._gddr6_temp_pkexec_command('check')

    def comando_leer_temperatura_vram(self):
        return self._gddr6_temp_pkexec_command('read')

    def comando_aplicar_parche_vram(self):
        return self._gddr6_temp_pkexec_command('apply')
