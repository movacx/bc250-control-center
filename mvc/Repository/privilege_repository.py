from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess


class PrivilegeRepository:
    """Select the safest privileged execution path for the current session."""

    _STEAMOS_GAME_HELPER_PROTOCOL = 6

    def _steamos_game_helper_candidates(self):
        configured = os.environ.get('BC250_STEAMOS_GAME_HELPER', '').strip()
        candidates = []
        if configured:
            candidates.append(Path(configured))
        candidates.extend([
            Path('/usr/libexec/bc250-control-center/bc250-steamos-game-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-steamos-game-helper'),
        ])
        return candidates

    def _steamos_game_helper_path(self):
        for candidate in self._steamos_game_helper_candidates():
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return ''

    def _steamos_game_helper_protocol(self, helper):
        try:
            text = Path(helper).read_text(encoding='utf-8', errors='ignore')[:65536]
        except OSError:
            return 0
        match = re.search(r'^BC250_HELPER_PROTOCOL\s*=\s*(\d+)\s*$', text, re.MULTILINE)
        return int(match.group(1)) if match else 0

    def _steam_session_has_desktop_shell(self):
        text = ' '.join(
            os.environ.get(name, '')
            for name in ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')
        ).lower()
        desktop_tokens = ('kde', 'plasma', 'gnome', 'cinnamon', 'xfce', 'mate', 'lxqt')
        return any(token in text for token in desktop_tokens)

    def _steamos_game_mode_detected(self):
        try:
            if not self._es_steamos():
                return False
        except Exception:
            return False

        direct_markers = (
            'GAMESCOPE_WAYLAND_DISPLAY',
            'STEAM_GAMEPADUI',
            'SteamGamepadUI',
            'SteamTenfoot',
            'SteamDeck',
            'SteamClientLaunch',
        )
        if any(os.environ.get(name) for name in direct_markers):
            return True

        wayland = os.environ.get('WAYLAND_DISPLAY', '').lower()
        if any(token in wayland for token in ('gamescope', 'steam')):
            return True

        if self._process_tree_contains(os.getpid(), {'gamescope'}):
            return True

        if self._steam_session_has_desktop_shell():
            # Desktop Mode on SteamOS normally exports KDE/Plasma.  Keep the
            # traditional Polkit path there even when Steam is open.  SteamAppId
            # alone is not enough here because desktop Steam can set it too.
            return False

        steam_ids = any(os.environ.get(name) for name in ('SteamAppId', 'SteamGameId'))
        if steam_ids and self._process_tree_contains(os.getpid(), {'steam', 'steamwebhelper'}):
            return True

        if shutil.which('pgrep'):
            try:
                result = subprocess.run(['pgrep', '-x', 'gamescope'], text=True, capture_output=True, timeout=2, check=False)
                if result.returncode == 0 and result.stdout.strip() and steam_ids:
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _process_tree_contains(pid, names):
        try:
            current = int(pid)
        except (TypeError, ValueError):
            return False
        wanted = {str(name).lower() for name in names}
        seen = set()
        while current > 1 and current not in seen:
            seen.add(current)
            try:
                comm = Path(f'/proc/{current}/comm').read_text(encoding='utf-8', errors='ignore').strip().lower()
                if comm in wanted:
                    return True
                status = Path(f'/proc/{current}/status').read_text(encoding='utf-8', errors='ignore')
            except OSError:
                return False
            parent = 0
            for line in status.splitlines():
                if line.startswith('PPid:'):
                    try:
                        parent = int(line.split()[1])
                    except (IndexError, ValueError):
                        parent = 0
                    break
            if parent <= 0 or parent == current:
                return False
            current = parent
        return False

    def _usar_steamos_game_helper(self):
        return bool(self._steamos_game_mode_detected() and self._steamos_game_helper_path())

    def _comando_steamos_game_helper(self, *args):
        helper = self._steamos_game_helper_path()
        if not helper:
            raise RuntimeError(
                'HELPER_MISSING: SteamOS Game Mode helper is not installed. Reinstall BC250 Control Center '
                'from desktop mode, then launch it again from Steam.'
            )
        protocol = self._steamos_game_helper_protocol(helper)
        if protocol != self._STEAMOS_GAME_HELPER_PROTOCOL:
            raise RuntimeError(
                'HELPER_VERSION_MISMATCH: The root-owned SteamOS Game Mode helper is outdated '
                f'(installed protocol {protocol or "legacy"}, required {self._STEAMOS_GAME_HELPER_PROTOCOL}). '
                'Exit Game Mode, run scripts/install-local.sh from this build in Desktop Mode, and verify the '
                'installed helper before launching the app again.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit from desktop mode first.')
        forwarded = [
            '--origin-pid', str(os.getpid()),
            '--origin-uid', str(os.getuid()),
        ]
        for name in (
            'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION',
            'WAYLAND_DISPLAY', 'GAMESCOPE_WAYLAND_DISPLAY', 'SteamGamepadUI',
            'STEAM_GAMEPADUI', 'SteamTenfoot', 'SteamDeck', 'SteamAppId',
            'SteamGameId', 'SteamClientLaunch',
        ):
            value = os.environ.get(name)
            if value:
                forwarded.extend(['--origin-env', f'{name}={value}'])
        return ['pkexec', helper, *forwarded, '--', *[str(arg) for arg in args]]

    def _ejecutar_steamos_game_helper(self, *args, timeout=240):
        comando = self._comando_steamos_game_helper(*args)
        rc, out, err = self._ejecutar(comando, timeout=timeout)
        if rc != 0:
            detalle = err or out or f'exit code {rc}'
            raise RuntimeError(detalle)
        return (out or '').strip()
