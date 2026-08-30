from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frontends.desktop.i18n import localize_widget_tree, tr


def _localized_tree(qtbot):
    root = QWidget()
    root.setWindowTitle("Settings")
    root.fit_calls = 0
    root.fit_to_content = lambda: setattr(root, "fit_calls", root.fit_calls + 1)
    layout = QVBoxLayout(root)
    label = QLabel("Apply")
    line = QLineEdit()
    line.setPlaceholderText("Settings")
    combo = QComboBox()
    combo.addItems(("Apply", "Cancel"))
    tabs = QTabWidget()
    tabs.addTab(QWidget(), "Settings")
    table = QTableWidget(0, 2)
    table.setHorizontalHeaderItem(0, QTableWidgetItem("Apply"))
    table.setHorizontalHeaderItem(1, QTableWidgetItem("Cancel"))
    for widget in (label, line, combo, tabs, table):
        layout.addWidget(widget)
    qtbot.addWidget(root)
    return root, label, line, combo, tabs, table


def test_widget_tree_localizes_and_round_trips_cached_sources(qtbot):
    root, label, line, combo, tabs, table = _localized_tree(qtbot)

    localize_widget_tree(root, "es")
    assert label.text() == tr("Apply", "es")
    assert line.placeholderText() == tr("Settings", "es")
    assert combo.itemText(1) == tr("Cancel", "es")
    assert tabs.tabText(0) == tr("Settings", "es")
    assert table.horizontalHeaderItem(0).text() == tr("Apply", "es")
    assert root.windowTitle() == tr("Settings", "es")

    localize_widget_tree(root, "de")
    assert label.text() == tr("Apply", "de")
    assert combo.itemText(1) == tr("Cancel", "de")
    assert root.fit_calls == 2


def test_widget_tree_preserves_literal_and_collapsed_explicit_text(qtbot):
    root = QWidget()
    layout = QVBoxLayout(root)
    literal = QPushButton("Upstream command")
    literal.setProperty("i18nLiteral", True)
    explicit = QLabel("visible")
    explicit.source_text = "Settings"
    explicit.setProperty("collapsed", True)
    layout.addWidget(literal)
    layout.addWidget(explicit)
    qtbot.addWidget(root)

    localize_widget_tree(root, "es")

    assert literal.text() == "Upstream command"
    assert explicit.text() == ""
    assert explicit.property("i18nSourceText") == "Settings"
