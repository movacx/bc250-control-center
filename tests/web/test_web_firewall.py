"""Firewall changes are scoped, verified and reversible; no real firewall calls."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "privileged/lib"))
from system_setup_common import Host, SetupError
import system_setup_web_firewall as fw
from bc250cc.infrastructure import web_firewall


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.rules = []
        self.fail = False
        self.host = Host(Path(self.temp.name), runner=self.run_command)

    def run_command(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "ip":
            return json.dumps([{"ifname": "wlan0", "addr_info": [{"local": "192.168.0.8", "prefixlen": 24}]},
                               {"ifname": "wg0", "addr_info": [{"local": "10.0.0.2", "prefixlen": 24}]}])
        if args[:3] == ("ufw", "status", "verbose"):
            return "Status: active\nDefault: deny (incoming)\n1714:1764/udp ALLOW IN Anywhere\n" + "\n".join(self.rules)
        if args[:3] == ("ufw", "insert", "1"):
            self.rules.append("8250/tcp ALLOW IN 192.168.0.0/24")
            if self.fail:
                self.rules.append("8250/tcp DENY IN Anywhere")
            return "Rule inserted"
        if args[:3] == ("ufw", "--force", "delete"):
            self.rules.remove("8250/tcp ALLOW IN 192.168.0.0/24")
            return "Rule deleted"
        return ""

    def test_cachyos_blocked_then_scoped_idempotent_repair(self):
        self.assertEqual(fw.status(self.host, 8250)["state"], "blocked")
        result = fw.repair(self.host, 8250)
        self.assertTrue(result["changed"])
        self.assertEqual(result["networks"], ["192.168.0.0/24"])
        mutation = next(call for call in self.calls if call[:3] == ("ufw", "insert", "1"))
        self.assertEqual(mutation[3:], ("allow", "from", "192.168.0.0/24", "to", "any", "port", "8250", "proto", "tcp", "comment", fw.COMMENT))
        self.assertFalse(fw.repair(self.host, 8250)["changed"])
        self.assertEqual(sum(call[:3] == ("ufw", "insert", "1") for call in self.calls), 1)

    def test_existing_deny_then_allow_preserved(self):
        self.rules = ["8250/tcp DENY IN Anywhere", "8250/tcp ALLOW IN 192.168.0.0/24"]
        with self.assertRaises(SetupError):
            fw.repair(self.host, 8250)
        self.assertFalse(any(call[0] == "ufw" and "insert" in call for call in self.calls))

    def test_rule_order_protocol_and_ranges(self):
        for text, expected in [("8250/udp ALLOW IN Anywhere", None),
                               ("8200:8300/tcp ALLOW IN Anywhere", True),
                               ("8250/tcp DENY IN 192.168.0.7\n8250/tcp ALLOW IN Anywhere", False),
                               ("8250/tcp ALLOW IN Anywhere\n8250/tcp DENY IN Anywhere", True)]:
            self.assertIs(fw.ufw_rules(text, "192.168.0.0/24", 8250)[0], expected)

    def test_invalid_ports(self):
        for port in (True, 22, 65536, "8250"):
            with self.assertRaises(SetupError):
                fw.repair(self.host, port)
        self.assertEqual(self.calls, [])

    def test_unprivileged_fallback(self):
        self.host.write("/etc/ufw/ufw.conf", "ENABLED=yes")
        self.host.write("/etc/default/ufw", 'DEFAULT_INPUT_POLICY="DROP"')
        self.host.write("/etc/ufw/user.rules", "-A ufw-user-input -p udp --dport 1714:1764 -j ACCEPT")
        original = self.run_command
        def run(*args, **kwargs):
            if args[0] == "ufw":
                raise SetupError("root required")
            return original(*args, **kwargs)
        self.host.runner = run
        result = fw.status(self.host, 8250)
        self.assertEqual(result["state"], "blocked")
        self.assertFalse(result["verified"])
        self.assertTrue(result["repairable"])
        with self.assertRaises(SetupError):
            fw.repair(self.host, 8250)

    def test_custom_manager_preserved(self):
        with patch.object(fw, "_service_active", return_value=True):
            self.assertEqual(fw.status(self.host, 8250)["state"], "unsupported")
            with self.assertRaises(SetupError):
                fw.repair(self.host, 8250)

    def test_no_private_network(self):
        self.host.runner = lambda *a, **k: '[]'
        with self.assertRaises(SetupError):
            fw.repair(self.host, 8250)

    def test_failed_verification_rolls_back_added_rule(self):
        original = fw.status
        count = 0
        def status(*args):
            nonlocal count
            count += 1
            result = original(*args)
            return {**result, "state": "blocked"} if count > 1 else result
        with patch.object(fw, "status", side_effect=status):
            with self.assertRaises(SetupError):
                fw.repair(self.host, 8250)
        self.assertEqual(self.rules, [])

    def test_firewalld_runtime_and_permanent_scoped_rules(self):
        added = set()
        def runner(*args, **kwargs):
            if args[0] == 'ip':
                return self.run_command(*args)
            if args == ('firewall-cmd', '--state'):
                return 'running'
            if args[-1].startswith('--get-zone-of-interface'):
                return 'home'
            if args[-1].startswith('--query-rich-rule='):
                return 'yes' if (*args[:-1], args[-1].replace('--query-', '--add-')) in added else 'no'
            if args[-1].startswith('--add-rich-rule='):
                added.add(args)
            return ''
        self.host.runner = runner
        self.assertTrue(fw.repair(self.host, 8250)['changed'])
        self.assertEqual(len(added), 2)
        self.assertTrue(all('--zone=home' in rule and '192.168.0.0/24' in rule[-1] for rule in added))
        self.assertFalse(fw.repair(self.host, 8250)['changed'])

    def test_status_never_requests_privilege(self):
        with patch.object(web_firewall, 'HELPER') as helper, patch.object(web_firewall.subprocess, 'run') as run:
            helper.is_file.return_value = True
            helper.read_text.return_value = '"web-firewall-status"'
            run.return_value.returncode = 0
            run.return_value.stdout = '{"state":"blocked"}'
            self.assertEqual(web_firewall.inspect(8250)['state'], 'blocked')
            self.assertNotIn('pkexec', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
