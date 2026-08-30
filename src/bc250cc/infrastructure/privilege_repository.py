from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from bc250cc.infrastructure.session_privilege_policy import (
    SteamSessionSignals,
    classify_steamos_game_mode,
    has_desktop_shell,
    trusted_helper_metadata,
)


class PrivilegeRepository:
    """Select the safest privileged execution path for the current session."""

    # Keep this in lockstep with Resources/privileged/bc250-steamos-game-helper.
    # Protocol 18 adds bounded NCT PWM duty re-writes after the automatic ->
    # manual transition.  Accepting protocol 16 would silently acknowledge a
    # PWM4 value which the controller can still discard during that settle.
    # Protocol 20 adds gpu-usage.method to the finite Cyan compatibility action.
    # Protocol 19 adds the no-TTY CPU boot-service operation used when the
    # desktop application is launched as a Steam non-Steam game.
    _STEAMOS_GAME_HELPER_PROTOCOL = 20

    def _game_platform_supported(self):
        try:
            return str(self._os_repository().info.family or "").lower() in {"steamos", "bazzite", "cachyos"}
        except Exception:
            try:
                return bool(self._es_steamos())
            except Exception:
                return False

    def _steamos_game_helper_candidates(self):
        return [
            Path('/usr/libexec/bc250-control-center/bc250-steamos-game-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-steamos-game-helper'),
        ]

    def _steamos_game_helper_path(self):
        for candidate in self._steamos_game_helper_candidates():
            try:
                metadata = candidate.lstat()
            except OSError:
                continue
            if trusted_helper_metadata(
                is_regular=stat.S_ISREG(metadata.st_mode),
                is_symlink=stat.S_ISLNK(metadata.st_mode),
                owner_uid=metadata.st_uid,
                mode=metadata.st_mode,
                executable=os.access(candidate, os.X_OK),
            ):
                return str(candidate)
        return ''

    def _steamos_game_helper_protocol(self, helper):
        try:
            with Path(helper).open(encoding='utf-8', errors='ignore') as stream:
                text = stream.read(65536)
        except OSError:
            return 0
        match = re.search(r'^BC250_HELPER_PROTOCOL\s*=\s*(\d+)\s*$', text, re.MULTILINE)
        return int(match.group(1)) if match else 0

    def _steam_session_has_desktop_shell(self):
        text = ' '.join(
            os.environ.get(name, '')
            for name in ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')
        )
        return has_desktop_shell(text)

    def _steamos_game_mode_detected(self):
        try:
            is_steamos = self._game_platform_supported()
        except Exception:
            is_steamos = False
        direct_markers = (
            'GAMESCOPE_WAYLAND_DISPLAY', 'STEAM_GAMEPADUI', 'SteamGamepadUI',
            'SteamTenfoot', 'SteamDeck', 'SteamClientLaunch',
        )
        desktop = ' '.join(
            os.environ.get(name, '')
            for name in ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')
        )
        steam_ids = any(
            os.environ.get(name) for name in ('SteamAppId', 'SteamGameId')
        )
        return classify_steamos_game_mode(SteamSessionSignals(
            is_steamos=is_steamos,
            desktop=desktop,
            direct_game_marker=any(os.environ.get(name) for name in direct_markers),
            wayland_display=os.environ.get('WAYLAND_DISPLAY', ''),
            gamescope_ancestor=self._process_tree_contains(os.getpid(), {'gamescope'}),
            steam_ids=steam_ids,
            steam_ancestor=(
                self._process_tree_contains(os.getpid(), {'steam', 'steamwebhelper'})
                if steam_ids else False
            ),
        ))

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
                comm = Path(f'/proc/{current}/comm').read_text(
                    encoding='utf-8', errors='ignore'
                ).strip().lower()
                if comm in wanted:
                    return True
                status = Path(f'/proc/{current}/status').read_text(
                    encoding='utf-8', errors='ignore'
                )
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

    def _usar_steamos_cu_helper(self):
        """Use the narrow root-owned CU helper in Desktop and Game Mode."""
        try:
            return bool(self._game_platform_supported() and self._steamos_game_helper_path())
        except Exception:
            return False

    def _steamos_fan_daemon_detected(self):
        if os.environ.get('BC250_CONTROL_CENTER_DAEMON') != '1':
            return False
        try:
            return self._game_platform_supported()
        except Exception:
            return False

    def _usar_steamos_fan_daemon_helper(self):
        return bool(self._steamos_fan_daemon_detected() and self._steamos_game_helper_path())

    def _comando_steamos_game_helper(self, *args):
        helper = self._steamos_game_helper_path()
        if not helper:
            raise RuntimeError(
                'HELPER_MISSING: SteamOS Game Mode helper is not installed. Reinstall BC250 Control Center '
                'from desktop mode, then launch it again from Steam.'
            )
        protocol = self._steamos_game_helper_protocol(helper)
        # Protocol revisions are additive: a newer trusted helper keeps the
        # previous finite actions.  Treat the GUI value as a *minimum*, so an
        # older Game Mode process can safely use a just-installed newer helper
        # instead of failing with a misleading 15 -> 16 mismatch.
        if protocol < self._STEAMOS_GAME_HELPER_PROTOCOL:
            raise RuntimeError(
                'HELPER_VERSION_MISMATCH: The root-owned SteamOS Game Mode helper is incompatible '
                f'(installed protocol {protocol or "legacy"}, minimum required {self._STEAMOS_GAME_HELPER_PROTOCOL}). '
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

    def _ejecutar_steamos_fan_daemon_helper(self, pwm, value, timeout=120):
        if not self._steamos_fan_daemon_detected():
            raise RuntimeError('The dedicated SteamOS fan-daemon context was not detected.')
        comando = self._comando_steamos_game_helper('fan-daemon-pwm', int(pwm), int(value))
        rc, out, err = self._ejecutar(comando, timeout=timeout)
        if rc != 0:
            raise RuntimeError(err or out or f'exit code {rc}')
        return (out or '').strip()
