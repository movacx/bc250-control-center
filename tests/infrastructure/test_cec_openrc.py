"""Build and exercise CEC lifecycle scripts without services or hardware."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bc250cc.infrastructure.accessories import hdmi_cec as cec


class CecOpenrcTests(unittest.TestCase):
    def test_install_inventory_and_remove_use_only_openrc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'
            tools = root / 'tools with spaces'
            flag = root / 'softlevel'
            flag.touch()
            build = ['mkdir -p "$bc250_stage/out"',
                     'cp /bin/true "$bc250_stage/out/cecd"',
                     'cp /bin/true "$bc250_stage/out/cectool"',
                     'touch "$bc250_stage/out/LICENSE" "$bc250_stage/out/LICENSE.linux-cec-sys"']
            env = {**os.environ, 'XDG_CONFIG_HOME': str(config), 'XDG_DATA_HOME': str(root / 'data'),
                   'XDG_RUNTIME_DIR': str(root / 'run'), 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/fake'}
            mocks = '''sudo() { :; }
rc-service() { echo "rc-service $*"; }
rc-update() { echo "rc-update $*"; }
systemctl() { echo 'UNEXPECTED SYSTEMD' >&2; return 99; }
'''
            with patch.dict(os.environ, env), patch.object(cec, 'supported', return_value=(True, '')), \
                 patch.object(cec, 'system_cecd', return_value=False), patch.object(cec, '_openrc_active', return_value=True), \
                 patch.object(cec, '_build_lines', return_value=build), patch.object(cec, 'CEC_CLASS', root / 'cec'), \
                 patch.object(cec, 'UDEV_RULE', root / 'udev/cec.rules'):
                for action in (cec.install_command, cec.remove_command):
                    script = action('arch', tools).replace('/run/openrc/softlevel', str(flag))
                    result = subprocess.run(['bash', '-c', mocks + script], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn('UNEXPECTED SYSTEMD', result.stderr)
                    self.assertIn('rc-update --user', result.stdout)
                    if action is cec.install_command:
                        service = cec.openrc_service_path()
                        self.assertTrue(service.is_file())
                        self.assertTrue(service.stat().st_mode & 0o100)
                        self.assertIn('supervise-daemon', service.read_text())
                        check = subprocess.run(['sh', '-n', str(service)], capture_output=True, text=True)
                        self.assertEqual(check.returncode, 0, check.stderr)
                        with patch.object(cec, 'command_output', return_value='* status: started'):
                            self.assertEqual(cec.inventory('arch', tools)['state'], 'active')
                    else:
                        self.assertFalse(cec.openrc_service_path().exists())
                        self.assertFalse((tools / cec.FOLDER).exists())

    def test_openrc_guard_preserves_foreign_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'rc/init.d/bc250-cecd'
            path.parent.mkdir(parents=True)
            path.write_text('# foreign')
            flag = root / 'softlevel'
            flag.touch()
            script = '\n'.join(cec._openrc_guard()).replace('/run/openrc/softlevel', str(flag))
            env = {**os.environ, 'XDG_CONFIG_HOME': directory, 'XDG_RUNTIME_DIR': directory,
                   'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/fake'}
            result = subprocess.run(['bash', '-c', 'rc-service() { :; }; rc-update() { :; };\n' + script],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 65)
            self.assertEqual(path.read_text(), '# foreign')


    def test_wake_automation_install_and_remove_without_systemd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {**os.environ, 'HOME': directory, 'XDG_CONFIG_HOME': str(root / 'config'),
                   'XDG_RUNTIME_DIR': directory, 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/fake'}
            flag = root / 'softlevel'
            flag.touch()
            mocks = 'rc-service() { :; }; rc-update() { :; }; gdbus() { :; };\n'
            with patch.dict(os.environ, env), patch.object(cec, '_openrc_active', return_value=True):
                for script in (cec.wake_install_command('arch'), cec.wake_remove_command()):
                    self.assertNotIn('systemctl --user', script)
                    result = subprocess.run(['bash', '-c', mocks + script.replace('/run/openrc/softlevel', str(flag))],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((root / cec.WAKE_HELPER).exists())
                self.assertFalse((root / 'config/rc/init.d' / cec.OPENRC_WAKE_NAME).exists())

    def test_shutdown_guard_excludes_reboot_suspend_and_manual_stop(self):
        mocks = '''ls() { echo /dev/cec-test; }
cec-ctl() {
  case "$*" in
    *--standby*) echo STANDBY ;;
    *--request-active-source*) echo 'phys-addr: 1.0.0.0' ;;
    *) echo 'Physical Address : 1.0.0.0' ;;
  esac
}
'''
        script = cec.poweroff_helper_text(openrc=True)
        self.assertNotIn('systemctl --user', script)
        for runlevel, reboot, expected in [('shutdown', 'NO', True), ('shutdown', 'YES', False),
                                           ('default', 'NO', False), ('single', 'NO', False)]:
            with self.subTest(runlevel=runlevel, reboot=reboot):
                env = {**os.environ, 'RC_RUNLEVEL': runlevel, 'RC_REBOOT': reboot}
                result = subprocess.run(['bash', '-c', mocks + script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual('STANDBY' in result.stdout, expected)

    def test_poweroff_install_and_remove_do_not_send_standby(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(cec, '_openrc_active', return_value=True), \
                 patch.object(cec, 'OPENRC_POWEROFF', root / 'init.d/bc250-cec-poweroff'), \
                 patch.object(cec, 'POWEROFF_HELPER', root / 'helpers/standby'), \
                 patch.object(cec, 'FOREIGN_POWEROFF', root / 'foreign'):
                mocks = '''sudo() { if [ "$1" = -v ]; then return 0; fi; "$@"; }
rc-update() { :; }
rc-service() { :; }
cec-ctl() { echo UNEXPECTED_HARDWARE; }
'''
                for script in (cec.poweroff_install_command('arch'), cec.poweroff_remove_command('arch')):
                    self.assertNotIn('systemctl --user', script)
                    result = subprocess.run(['bash', '-c', mocks + script], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn('UNEXPECTED_HARDWARE', result.stdout)
                self.assertFalse(cec.OPENRC_POWEROFF.exists())
                self.assertFalse(cec.POWEROFF_HELPER.exists())

    def test_openrc_wake_transport_and_polite_mode(self):
        for state, expected in [('0x01', True), ('0x00', False)]:
            mocks = '''ls() { echo cec0; }
gdbus() {
  case "$*" in
    *SendReceiveRawMessage*) echo '(byte STATE,)' ;;
    *SetActiveSource*) echo CLAIMED ;;
    *Wake*) echo WOKE ;;
  esac
}
'''.replace('STATE', state)
            result = subprocess.run(['bash', '-c', mocks + cec.openrc_wake_helper_text('polite')],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual('WOKE' in result.stdout, expected)
            self.assertEqual('CLAIMED' in result.stdout, expected)


if __name__ == '__main__':
    unittest.main()
