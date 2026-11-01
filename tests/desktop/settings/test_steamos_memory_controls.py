"""SteamOS's full memory controls use the helper's real capabilities."""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton

from frontends.desktop.components.system_setup_controls import update_memory_controls


class SteamOSMemoryControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def owner(self):
        owner = SimpleNamespace(memory_policy_combo=QComboBox(), ttm_limit_combo=QComboBox(),
                                memory_swap_apply_button=QPushButton(), memory_ttm_apply_button=QPushButton())
        for label, value in [('Keep', 0), ('Restore', -1), ('8 GiB', 8), ('10 GiB', 10), ('12 GiB', 12)]:
            owner.ttm_limit_combo.addItem(label, value)
        return owner

    def tools(self):
        return {'os_family': 'steamos', 'system_setup': {
            'helper_available': True,
            'memory': {'supported': True, 'policies': ['preserve', 'swap-16', 'swap-32', 'zram', 'zswap-16', 'zswap-32'],
                       'default_swap_mount': '/home'},
            'ttm': {'supported': True, 'presets_gib': [8, 10, 12]},
        }}

    def test_swap32_zram_and_ttm_can_be_selected_on_steamos(self):
        owner = self.owner()
        tools = self.tools()
        update_memory_controls(owner, tools)
        for policy in ('swap-32', 'zram'):
            with self.subTest(policy=policy):
                index = owner.memory_policy_combo.findData(policy)
                self.assertGreaterEqual(index, 0)
                self.assertTrue(owner.memory_policy_combo.model().item(index).isEnabled())
                owner.memory_policy_combo.setCurrentIndex(index)
                update_memory_controls(owner, tools)
                self.assertTrue(owner.memory_swap_apply_button.isEnabled())
        owner.ttm_limit_combo.setCurrentIndex(owner.ttm_limit_combo.findData(10))
        update_memory_controls(owner, tools)
        self.assertTrue(owner.memory_ttm_apply_button.isEnabled())

    def test_existing_zram_and_unsupported_ttm_remain_protected(self):
        owner = self.owner()
        tools = self.tools()
        tools['system_setup']['memory']['policies'].remove('zram')
        tools['system_setup']['ttm']['supported'] = False
        update_memory_controls(owner, tools)
        self.assertFalse(owner.memory_policy_combo.model().item(owner.memory_policy_combo.findData('zram')).isEnabled())
        self.assertFalse(owner.ttm_limit_combo.isEnabled())
        self.assertFalse(owner.memory_ttm_apply_button.isEnabled())


if __name__ == '__main__':
    unittest.main()
