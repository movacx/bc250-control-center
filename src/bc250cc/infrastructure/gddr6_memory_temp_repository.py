"""Client-side orchestration for the reviewed GDDR6 memory-temperature tool.

Mirrors the CPU core-unlock pattern: this module never talks to SMU hardware
itself. It locates the packaged, root-owned helpers, validates the desktop
user's own checkout of the reviewed upstream tool, and builds the exact
pkexec argv each helper expects. All hardware access happens inside
bc250-gddr6-temp-reader (read-only) and bc250-gddr6-temp-helper (the runtime
SMU patch), run through Polkit under two separate actions.

The board firmware is read here rather than through a helper: DMI is
world-readable, so the desktop can tell whether the reviewed payload matches
this board without spending a Polkit prompt on the question.
"""
from __future__ import annotations

import json
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

#: The reviewed payload writes fixed SMU addresses that are only correct for
#: the board firmware it was built against.  Kept in step with the same
#: constant in both helpers.
GDDR6_SUPPORTED_BIOS_VERSIONS = frozenset({'p3.0', 'p3.00'})

#: How long one authenticated live-monitoring session lasts. Kept in step with
#: MONITOR_SECONDS in the helper, which is what actually enforces it.
MONITOR_SESSION_SECONDS = 600
BIOS_VERSION_PATH = Path('/sys/class/dmi/id/bios_version')


def board_bios_version():
    """Return the DMI board firmware version, or '' when it is unreadable."""
    try:
        return BIOS_VERSION_PATH.read_text(encoding='utf-8', errors='ignore').strip()
    except OSError:
        return ''


def gddr6_firmware_supported(version=None):
    """Whether the reviewed SMU payload matches this board's firmware."""
    detected = board_bios_version() if version is None else str(version)
    return detected.strip().lower() in GDDR6_SUPPORTED_BIOS_VERSIONS


class Gddr6MemoryTempRepository:
    def _gddr6_privileged_path(self, name):
        """Return an installed root-owned GDDR6 launcher, or '' when missing."""
        candidates = (
            Path(f'/usr/libexec/bc250-control-center/{name}'),
            Path(f'/usr/local/libexec/bc250-control-center/{name}'),
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

    def _board_bios_version(self):
        """Overridable seam: tests must not depend on the host's real DMI."""
        return board_bios_version()

    def _gddr6_temp_helper_path(self):
        """The patcher: unlocks the SMU debug gate and writes the payload."""
        return self._gddr6_privileged_path('bc250-gddr6-temp-helper')

    def _gddr6_temp_reader_path(self):
        """The reader: no write path at all, so its Polkit grant may be cached."""
        return self._gddr6_privileged_path('bc250-gddr6-temp-reader')

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
        bios_version = self._board_bios_version()
        return {
            'hardware_detected': is_bc250_platform(),
            'helper_ready': bool(self._gddr6_temp_helper_path()),
            'reader_ready': bool(self._gddr6_temp_reader_path()),
            'repository_ready': repository_ready,
            'payload_present': (repository / 'SMUPayload.bin').is_file(),
            'repository_path': str(repository),
            'reference_url': GDDR6_MEMORY_TEMP_REPOSITORY,
            'reviewed_revision': REVIEWED_REVISION,
            'bios_version': bios_version,
            'firmware_supported': gddr6_firmware_supported(bios_version),
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

    def _gddr6_temp_pkexec_command(self, action, *, helper):
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

    def comando_estado_smu_vram(self):
        """Read board/patch state only — no chip sampling, no writes."""
        return self._gddr6_temp_pkexec_command(
            'status', helper=self._gddr6_temp_reader_path()
        )

    def comando_leer_temperatura_vram(self):
        return self._gddr6_temp_pkexec_command(
            'read', helper=self._gddr6_temp_reader_path()
        )

    def comando_aplicar_parche_vram(self):
        """Refused up front when the payload does not match this firmware.

        The helper enforces this too — it is the only enforcement that counts,
        since it is the side holding root. Checking here as well means the
        button can say why instead of opening a Polkit prompt that ends in an
        error the user cannot act on.
        """
        detected = self._board_bios_version()
        if not gddr6_firmware_supported(detected):
            raise RuntimeError(
                'GDDR6_FIRMWARE_UNSUPPORTED: the reviewed SMU payload targets board '
                f"firmware P3.0; this board reports {detected or 'an unknown version'}."
            )
        return self._gddr6_temp_pkexec_command(
            'apply', helper=self._gddr6_temp_helper_path()
        )

    def ultima_temperatura_vram(self):
        """Return the most recent successful reading, without reading again.

        Every real read costs a Polkit check, so a passive consumer such as
        the dashboard must never trigger one: it shows what the last explicit
        read found, or nothing at all. The cache lives for the lifetime of the
        application process, which matches how long the SMU patch itself
        survives in the common case.
        """
        return dict(getattr(self, '_gddr6_last_sample', {}) or {})

    def comando_monitorizar_vram(self, seconds=MONITOR_SESSION_SECONDS):
        """One authenticated session that patches if needed, then samples.

        Live monitoring used to cost a Polkit check per sample. This is a
        single privileged run that ends by itself, so one prompt buys a
        bounded window of readings and nothing stays authenticated after it.
        """
        detected = self._board_bios_version()
        if not gddr6_firmware_supported(detected):
            raise RuntimeError(
                'GDDR6_FIRMWARE_UNSUPPORTED: the reviewed SMU payload targets board '
                f"firmware P3.0; this board reports {detected or 'an unknown version'}."
            )
        command = self._gddr6_temp_pkexec_command(
            'monitor', helper=self._gddr6_temp_helper_path()
        )
        return [*command, '--seconds', str(int(seconds))]

    def leer_temperatura_vram(self, *, chips=True):
        """Run the reader and return its parsed snapshot.

        Never raises: every failure becomes ``available: False`` plus the
        reason, because this feeds a live monitoring panel where an exception
        would be indistinguishable from "the board has no patch applied".
        """
        try:
            command = (
                self.comando_leer_temperatura_vram() if chips
                else self.comando_estado_smu_vram()
            )
        except Exception as error:
            return {'available': False, 'error': str(error), 'chips': []}

        codigo, salida, detalle = self._ejecutar(command, timeout=30)
        if codigo != 0:
            return {'available': False, 'error': detalle or salida, 'chips': []}
        try:
            snapshot = json.loads(salida)
        except ValueError:
            return {
                'available': False,
                'error': 'The GDDR6 reader returned output that was not valid JSON.',
                'chips': [],
            }
        snapshot['available'] = True
        snapshot.setdefault('chips', [])
        snapshot.setdefault('error', '')
        self._gddr6_last_sample = dict(snapshot)
        return snapshot
