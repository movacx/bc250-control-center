import math

from frontends.desktop.core.performance_sample_presenter import (
    present_performance_sample,
)
from frontends.desktop.pages.performance import PerformancePage


def plans(sample):
    return {
        plan.key: plan
        for plan in present_performance_sample(
            sample,
            previous_peaks={},
            translate=lambda text: f"tr:{text}",
        )
    }


def test_nonfinite_values_never_enter_graph_series_or_visible_stats():
    result = plans(
        {
            "cpu": {"usage_percent": math.nan, "temperature_c": math.inf},
            "gpu": {"usage_percent": math.inf, "power_w": math.nan},
            "disk": {"read_bps": math.inf},
        }
    )

    assert dict(result["cpu"].graph_values) == {"Usage": 0.0}
    assert result["cpu"].stats[1] == "--"
    assert result["gpu"].primary == "--"
    assert result["gpu"].stats[2] == "--"
    assert dict(result["disk"].graph_values)["Read"] == 0.0


def test_vram_percentage_is_bounded_when_counters_are_inconsistent():
    result = plans({"gpu": {"vram_used": 12, "vram_total": 10}})

    assert result["vram"].primary == "100%"
    assert dict(result["vram"].graph_values) == {"Used": 100.0}
    assert result["vram"].stats[1] == "0 B"


def test_missing_capacity_and_interface_use_injected_translation():
    result = plans({})

    assert result["disk"].context.startswith("tr:Capacity unavailable")
    assert result["network"].stats[0] == "tr:not detected"


def test_peaks_include_current_sample_without_mutating_history():
    result = {
        plan.key: plan
        for plan in present_performance_sample(
            {"cpu": {"usage_percent": 72}},
            previous_peaks={"cpu": 60},
        )
    }

    assert result["cpu"].stats[3] == "72%"


def test_memory_context_exposes_compression_and_real_ttm_capacity():
    result = plans({
        "memory": {
            "used": 4 * 1024 ** 3,
            "total": 16 * 1024 ** 3,
            "zram_active": True,
            "zram_total_bytes": 8 * 1024 ** 3,
            "zswap_enabled": False,
            "ttm_limit_bytes": 12 * 1024 ** 3,
        }
    })

    assert "ZRAM 8.0 GiB" in result["memory"].context
    assert "ZSWAP" not in result["memory"].context
    assert "TTM 12 GiB" in result["memory"].context


def test_real_performance_page_appends_only_finite_normalized_series(qtbot):
    page = PerformancePage(object())
    qtbot.addWidget(page)

    page._sample_ready(
        {
            "cpu": {"usage_percent": math.nan},
            "gpu": {"usage_percent": math.inf, "vram_used": 20, "vram_total": 10},
            "disk": {"read_bps": math.inf, "write_bps": -20},
        }
    )

    assert list(page.histories["cpu"].values["Usage"]) == [0.0]
    assert list(page.histories["gpu"].values["Usage"]) == [0.0]
    assert list(page.histories["vram"].values["Used"]) == [100.0]
    assert list(page.histories["disk"].values["Read"]) == [0.0]
    assert page._sample_views["gpu"][0] == "--"
