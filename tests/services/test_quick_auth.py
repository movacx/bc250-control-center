"""The rules that skip the password name one account, protected helpers and exact commands only."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "privileged/lib"))
import system_setup_quick_auth as qa
from system_setup_common import Host, SetupError


class QuickAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("etc/sudoers.d", "etc/polkit-1/rules.d", qa.LIBEXEC.strip("/")):
            (self.root / folder).mkdir(parents=True)
        for name in qa.HELPERS:
            (self.root / qa.LIBEXEC.strip("/") / name).write_text("#!/usr/bin/python3 -I\n", encoding="utf-8")
        self.listed = qa.LIBEXEC + "bc250-cpu-smu-helper"
        self.reject = False
        self.host = Host(self.root, runner=self.run_command)

    def run_command(self, *args, **_kwargs):
        if args[:2] == ("visudo", "-cf") and self.reject:
            raise SetupError("visudo failed")
        return self.listed if args[0] == "sudo" else ""

    def file(self, name):
        return self.root / name.strip("/")

    def test_enable_writes_both_rules_and_disable_removes_them(self):
        self.assertTrue(qa.enable(self.host, "gamer")["enabled"])
        self.assertEqual(self.file(qa.SUDOERS).stat().st_mode & 0o777, 0o440)
        self.assertIn('subject.user == "gamer"', self.file(qa.POLKIT).read_text(encoding="utf-8"))
        self.assertFalse(qa.disable(self.host)["enabled"])
        self.assertFalse(self.file(qa.SUDOERS).exists() or self.file(qa.POLKIT).exists())

    def test_only_the_hardware_helpers_and_no_wildcards(self):
        text = qa.sudoers_text(self.host, "gamer")
        for line in text.splitlines()[1:]:
            self.assertTrue(line.startswith("gamer ALL=(root) NOPASSWD: /usr/"))
        for word in ("*", "core-unlock", "system-setup", "maintenance", "gddr6", "quick-access", "/bin/bash", "ALL\n"):
            self.assertNotIn(word, text)
        self.assertNotIn("core-unlock", qa.polkit_text(self.host, "gamer"))

    def test_the_rules_of_sudo_accept_the_text(self):
        if not shutil.which("visudo"):
            self.skipTest("visudo is not installed")
        path = self.root / "check"
        path.write_text(qa.sudoers_text(self.host, "gamer"), encoding="utf-8")
        result = subprocess.run(["visudo", "-cf", str(path)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nothing_stays_when_sudo_rejects_or_ignores_it(self):
        self.reject = True
        with self.assertRaises(SetupError):
            qa.enable(self.host, "gamer")
        self.assertFalse(self.file(qa.SUDOERS).exists())
        self.reject, self.listed = False, "nothing"
        with self.assertRaises(SetupError):
            qa.enable(self.host, "gamer")
        self.assertFalse(self.file(qa.SUDOERS).exists())

    def test_someone_elses_file_is_kept(self):
        self.file(qa.SUDOERS).write_text("# mine\n", encoding="utf-8")
        with self.assertRaises(SetupError):
            qa.enable(self.host, "gamer")
        self.assertEqual(self.file(qa.SUDOERS).read_text(encoding="utf-8"), "# mine\n")

    def test_the_account_is_the_one_that_authorized(self):
        with self.assertRaises(SetupError):
            qa.account({})
        with self.assertRaises(SetupError):
            qa.account({"SUDO_UID": "0"})
        with patch.object(qa.pwd, "getpwuid") as lookup:
            lookup.return_value.pw_name = 'x") return polkit.Result.YES;//'
            with self.assertRaises(SetupError):
                qa.account({"SUDO_UID": "1000"})

    def test_openrc_names_its_own_commands(self):
        softlevel = self.root / "run/openrc/softlevel"
        softlevel.parent.mkdir(parents=True)
        softlevel.touch()
        service = self.root / "sbin/rc-service"
        service.parent.mkdir()
        service.touch()
        text = "\n".join(qa.commands(self.host))
        self.assertIn("/sbin/rc-service oberon-governor restart", text)
        self.assertNotIn("systemctl", text)


class StateTests(unittest.TestCase):
    def test_the_note_is_only_for_its_account(self):
        from bc250cc.infrastructure import quick_auth

        with tempfile.TemporaryDirectory() as folder:
            note = Path(folder) / "quick-auth.json"
            with patch.object(quick_auth, "STATE", note):
                self.assertFalse(quick_auth.enabled())
                note.write_text(json.dumps({"user": quick_auth.getpass.getuser()}), encoding="utf-8")
                self.assertTrue(quick_auth.enabled())
                note.write_text(json.dumps({"user": "someone-else"}), encoding="utf-8")
                self.assertFalse(quick_auth.enabled())


if __name__ == "__main__":
    unittest.main()
