from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from bc250cc.infrastructure.cpu_telemetry import build_cpu_telemetry, parse_cpuinfo
from frontends.desktop.pages.cpu_smu import CpuSmuPage

CPUINFO = """
processor : 0
vendor_id : AuthenticAMD
cpu family : 23
model : 71
model name : AMD BC-250
stepping : 0
microcode : 0x8407007
cpu MHz : 3800.000
physical id : 0
core id : 0
flags : aes avx2 sha_ni svm

processor : 1
vendor_id : AuthenticAMD
cpu family : 23
model : 71
model name : AMD BC-250
stepping : 0
microcode : 0x8407007
cpu MHz : 3700.000
physical id : 0
core id : 0
flags : aes avx2 sha_ni svm

processor : 2
vendor_id : AuthenticAMD
cpu family : 23
model : 71
model name : AMD BC-250
stepping : 0
microcode : 0x8407007
cpu MHz : 3900.000
physical id : 0
core id : 1
flags : aes avx2 sha_ni svm
"""


def test_cpuinfo_parser_and_core_aggregation(tmp_path):
    cache = tmp_path / "cpu0" / "cache"
    for index, level, cache_type, size in (
        (0, "1", "Data", "32K"),
        (1, "1", "Instruction", "32K"),
        (2, "2", "Unified", "512K"),
        (3, "3", "Unified", "4096K"),
    ):
        root = cache / f"index{index}"
        root.mkdir(parents=True)
        (root / "level").write_text(level, encoding="utf-8")
        (root / "type").write_text(cache_type, encoding="utf-8")
        (root / "size").write_text(size, encoding="utf-8")

    assert len(parse_cpuinfo(CPUINFO)) == 3
    result = build_cpu_telemetry(CPUINFO, [10, 30, 60], tmp_path)
    processor = result["processor"]
    cores = result["cores"]
    assert processor["model_name"] == "AMD BC-250"
    assert processor["family_model_stepping"] == "23 / 71 / 0"
    assert processor["platform_process"] == "Zen 2 · TSMC N7FF"
    assert processor["microcode"] == "0x8407007"
    assert processor["topology"] == "2 cores / 3 threads"
    assert processor["cache"] == "L1D 32K · L1I 32K · L2 512K · L3 4M"
    assert processor["features"] == "AVX2 · AES · SHA_NI · SVM"
    assert round(processor["total_usage_percent"], 2) == 33.33
    assert cores[0]["threads"] == (0, 1)
    assert cores[0]["frequency_mhz"] == 3750
    assert cores[0]["usage_percent"] == 20
    assert cores[1]["threads"] == (2,)


def test_the_cpu_page_opens_on_the_unified_workspace(qtbot):
    """One screen, and the legacy grids still built behind it.

    The legacy cards keep being constructed and fed, because every tested
    tuning, persistence and core-unlock method writes into them. What changed
    is that none of them is what the user looks at.
    """
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    page.resize(1400, 1000)
    page._reflow(1400)

    assert page.workspace_stack.currentWidget() is page.unified_cpu_page
    assert page.unified_cpu_page.isAncestorOf(page._unified_cpu_control)
    assert len(page.core_stats) == 8

    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert "Upstream reference and credits" not in button_texts
    assert "Prepare upstream tool" not in button_texts
    assert "Unlock cores and restart" in button_texts

    labels = {label.text() for label in page.findChildren(QLabel)}
    assert any("CPU core unlocking is experimental" in text for text in labels)
    assert "Family / model / stepping" not in labels
    assert "Telemetry update" not in labels
    assert "Platform / process" in labels
    assert "Total CPU load" in labels


def test_live_metrics_and_core_cards_are_dense_and_have_no_explanatory_copy(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    labels = {label.text() for label in page.findChildren(QLabel)}

    assert (
        "Passive CPU telemetry aligned with the governor page layout and refreshed from the validated backend."
        not in labels
    )
    assert (
        "Metrics are read-only. Frequency, VID, and the temperature cap are only changed after the review dialog is confirmed."
        not in labels
    )
    assert (
        "All eight BC-250 core positions remain visible. Frequency and utilization are averaged across each core's logical threads."
        not in labels
    )
    metric_margins = page.metrics_card.root.contentsMargins()
    core_margins = page.cores_card.root.contentsMargins()
    assert (metric_margins.left(), metric_margins.top()) == (12, 9)
    assert (core_margins.left(), core_margins.top()) == (12, 9)
    assert all(tile.minimumHeight() == tile.maximumHeight() == 76 for tile in page.metric_tiles)
    assert all(stat.minimumHeight() == stat.maximumHeight() == 76 for stat in page.core_stats)
    assert page.metrics_card.sizeHint().height() == page.cores_card.sizeHint().height()


def test_cpu_paired_cards_share_the_same_vertical_edges(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    page.resize(1600, 1000)
    page.show()
    page._reflow(1550)

    page._select_workspace("overview")
    QApplication.processEvents()
    processor_rect = page.processor_card.geometry()
    unlock_rect = page.core_unlock_card.geometry()
    assert processor_rect.top() == unlock_rect.top()
    assert processor_rect.bottom() == unlock_rect.bottom()
    assert page.workspace.rowStretch(3) == 1

    page._select_workspace("configuration")
    QApplication.processEvents()
    configuration_rect = page.configuration_left_column.geometry()
    runtime_rect = page.runtime_card.geometry()
    assert configuration_rect.top() == runtime_rect.top()
    assert configuration_rect.bottom() == runtime_rect.bottom()
    assert page.configuration_workspace.rowStretch(2) == 1


def test_monitoring_and_configuration_are_no_longer_two_places(qtbot):
    """The tab bar is gone, and neither tab name can strand the user.

    Reading a temperature and changing a frequency belong to the same moment,
    so the split that used to separate them is the thing this guards against
    coming back.
    """
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    page.resize(1400, 1000)
    page._reflow(1400)

    assert page.workspace_tabs.isHidden()
    for workspace in ("overview", "configuration"):
        page._select_workspace(workspace)
        assert page.workspace_stack.currentWidget() is page.unified_cpu_page

    view = page._unified_cpu_control
    # Both halves are reachable without switching anything: the controls that
    # change the hardware and the readings that say what it is doing.
    assert view._profile_cards[0].isVisibleTo(view)
    assert view.apply_button.isVisibleTo(view)
    assert view.runtime_cards["persistence"].isVisibleTo(view)
    assert view.core_grid.isVisibleTo(view)
    assert view.runtime_cards["live"].isVisibleTo(view)
    assert view.unlock_button.isVisibleTo(view)

    # Advanced detail is one disclosure on the same screen, not a third place.
    assert not view._advanced_body.isVisible()
    view._advanced_toggle.setChecked(True)
    assert view._advanced_body.isVisibleTo(view)


def test_cpu_live_frequency_is_displayed_in_ghz(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)

    page._apply_refresh_payload(
        {
            "performance": {
                "cpu_freq": 3487,
                "cpu_voltage": 1.1,
                "cpu_temp": 55,
            },
            "tools": {},
            "persistent": {},
            "core_unlock": {
                "physical_cores": 6,
                "logical_cpus": 12,
                "cores": [
                    {
                        "index": 0,
                        "frequency_mhz": 3525,
                        "usage_percent": 25,
                        "threads": (0, 6),
                    }
                ],
            },
        }
    )

    assert page.frequency_metric.value.text() == "3.49 GHz"
    assert "3.52 GHz" in page.core_stats[0].value.text()
