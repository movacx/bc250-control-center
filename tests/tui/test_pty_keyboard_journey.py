"""Run the actual curses app on Linux-console and xterm PTYs."""
import fcntl
import os
import select
import signal
import struct
import sys
import termios
import time
from pathlib import Path

import pytest

pty = pytest.importorskip('pty')
ROOT = Path(__file__).resolve().parents[2]


def read_until(fd, needle, timeout=12):
    output = b''
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], .1)
        if ready:
            try:
                output += os.read(fd, 65536)
            except OSError:
                break
            if needle in output:
                return output
    assert needle in output, output[-4000:]
    return output


@pytest.mark.parametrize('terminal,width,height', [('xterm-256color', 80, 24), ('linux', 80, 25)])
def test_keyboard_journey_reaches_remote_and_every_resource_on_a_real_pty(tmp_path, terminal, width, height):
    config = tmp_path / 'config/bc250-control-center'
    config.mkdir(parents=True)
    (config / 'ui.conf').write_text('[settings]\nupdate_check=false\n')
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(TERM=terminal, LANG='C.UTF-8', HOME=str(tmp_path),
                          XDG_CONFIG_HOME=str(tmp_path / 'config'), XDG_STATE_HOME=str(tmp_path / 'state'),
                          XDG_DATA_HOME=str(tmp_path / 'data'), PYTHONPATH=f'{ROOT}/src:{ROOT}')
        os.chdir(ROOT)
        os.execv(sys.executable, [sys.executable, '-m', 'frontends.tui', '--lang', 'en', '--theme', 'mono'])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', height, width, 0, 0))
    output = b''
    try:
        output += read_until(fd, b'Dashboard')
        # Direct section shortcuts never require a mouse or a full-height sidebar.
        for shortcut in b'23457890':
            os.write(fd, bytes([shortcut]))
            time.sleep(.03)
        os.write(fd, b'.')
        output += read_until(fd, b'Information protected')
        os.write(fd, b'6')
        time.sleep(.1)
        # F3 task picker selects the final tab even when it does not fit the strip.
        f3 = b'\x1bOR' if terminal.startswith('xterm') else b'\x1b[[C'
        os.write(fd, f3)
        output += read_until(fd, b'Views')
        end = b'\x1bOF' if terminal.startswith('xterm') else b'\x1b[4~'
        os.write(fd, end + b'\r')  # terminal-specific End, Enter -> Network
        output += read_until(fd, b'Network')
        os.write(fd, b'[\x0c')  # previous task -> Disk; redraw for full-frame assertions
        output += read_until(fd, b'Disk')
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 14, 60, 0, 0))
        os.kill(pid, signal.SIGWINCH)
        os.write(fd, b'\x0c')  # Ctrl+L redraw, then quit normally
        time.sleep(.1)
        os.write(fd, b'q')
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, output[-3000:]
                break
            ready, _, _ = select.select([fd], [], [], .1)
            if ready:
                try:
                    output += os.read(fd, 65536)
                except OSError:
                    pass
        else:
            pytest.fail('TUI did not restore the terminal and exit after q')
        assert b'Traceback' not in output
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        os.close(fd)


def test_mouse_sgr_opens_remote_and_pinned_settings_on_an_actual_terminal(tmp_path):
    config = tmp_path / 'config/bc250-control-center'
    config.mkdir(parents=True)
    (config / 'ui.conf').write_text('[settings]\nupdate_check=false\n')
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(TERM='xterm-256color', LANG='C.UTF-8', HOME=str(tmp_path),
                          XDG_CONFIG_HOME=str(tmp_path / 'config'), XDG_STATE_HOME=str(tmp_path / 'state'),
                          XDG_DATA_HOME=str(tmp_path / 'data'), PYTHONPATH=f'{ROOT}/src:{ROOT}')
        os.chdir(ROOT)
        os.execv(sys.executable, [sys.executable, '-m', 'frontends.tui', '--lang', 'en', '--theme', 'mono'])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    try:
        read_until(fd, b'Dashboard')
        # At 30 rows, the full grouped sidebar places Remote access at y=14.
        os.write(fd, b'\x1b[<0;4;15M\x1b[<0;4;15m')
        read_until(fd, b'Information protected')
        # Settings is anchored at height-2 regardless of scroll/selection.
        # Let the preceding click release finish before the next physical click;
        # ncurses coalesces simultaneous mouse reports in its input queue.
        time.sleep(.15)
        os.write(fd, b'\x1b[<0;4;29M')
        time.sleep(.05)
        os.write(fd, b'\x1b[<0;4;29m')
        read_until(fd, b'General')
        os.write(fd, b'q')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
                break
            time.sleep(.1)
        else:
            pytest.fail('mouse navigation left the TUI unable to quit with the keyboard')
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        os.close(fd)
