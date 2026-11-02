"""Construction must never map child controls as independent desktop windows."""
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class StartupWindowFlashTest(unittest.TestCase):
    def test_hidden_components_do_not_show_top_level_windows(self):
        # A fresh Qt process isolates the test from other windows and preferences.
        program = textwrap.dedent('''
            import os
            import tempfile
            from PyQt6.QtCore import QObject, QEvent
            from PyQt6.QtWidgets import QApplication, QWidget

            with tempfile.TemporaryDirectory() as config:
                os.environ['XDG_CONFIG_HOME'] = config
                app = QApplication([])
                shown = []
                class Watch(QObject):
                    def eventFilter(self, obj, event):
                        if (event.type() == QEvent.Type.Show
                                and isinstance(obj, QWidget) and obj.isWindow()):
                            shown.append(type(obj).__name__)
                        return False
                watch = Watch()
                app.installEventFilter(watch)
                from frontends.desktop.components.dashboard_widgets import (
                    DashboardMemorySummary, PreparationSidebar,
                )
                from frontends.desktop.components.page_widgets import MetricTile
                from frontends.desktop.pages.firmware import FirmwareCard, FIRMWARE_FAMILIES
                widgets = [DashboardMemorySummary(live_action=True),
                           PreparationSidebar(), PreparationSidebar(standalone=True),
                           MetricTile('Test', detail='Visible detail')]
                widgets.extend(FirmwareCard(family) for family in FIRMWARE_FAMILIES)
                app.processEvents()
                assert not shown, f'Unexpected windows during construction: {shown}'
                # The controls still become visible inside their intended owner.
                tile = widgets[3]
                assert not tile.detail.isWindow()
                tile.show()
                app.processEvents()
                assert tile.detail.isVisible()
                assert shown == ['MetricTile'], shown
                for widget in widgets:
                    widget.close()
        ''')
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONPATH': str(ROOT / 'src')}
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
