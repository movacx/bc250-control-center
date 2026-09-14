"""The redesigned CPU overview: what it offers, and when it refuses to.

The GDDR6 readings are deliberately not here. They belong to the board rather
than the processor, and the dashboard strip drives them; this page only
mirrors the average in one telemetry tile.
"""

from frontends.desktop.core.gddr6_monitor import Gddr6Chip
from frontends.desktop.core.gddr6_monitor import Gddr6Reading as Gddr6State
from frontends.desktop.pages.cpu_overview_view import (
    CoreReading,
    CoreUnlockState,
    CpuOverviewState,
    CpuOverviewView,
)

READY = dict(
    hardware_detected=True,
    repository_ready=True,
    reader_ready=True,
    helper_ready=True,
    payload_present=True,
    firmware_supported=True,
)

CHIPS = tuple(Gddr6Chip(index=index, code=0x26, temperature_c=36.0) for index in range(8))


def _view(qtbot) -> CpuOverviewView:
    view = CpuOverviewView()
    qtbot.addWidget(view)
    return view


def test_hidden_cores_are_shown_as_offline_rather_than_omitted(qtbot):
    """A stock board exposes six of eight slots; the other two must say so."""
    view = _view(qtbot)

    view.apply_state(CpuOverviewState(
        topology="6 cores / 12 threads",
        cores=tuple(CoreReading(index, 3490, 10, "0, 1", True) for index in range(6)),
    ))

    labels = [item.text() for item in view.core_summary.core_frequency_labels]
    assert len(labels) == 8
    assert labels[0] == "3.49 GHz"
    assert labels[6] == labels[7] != "3.49 GHz"


def test_the_core_shape_is_shown_translated_not_as_the_backend_spells_it(qtbot):
    """The backend formats it in English; the unlock card composes it properly."""
    view = _view(qtbot)

    view.apply_state(CpuOverviewState(
        topology="6 cores / 12 threads",
        core_unlock=CoreUnlockState(detected_shape="6 núcleos / 12 hilos"),
    ))

    assert view.core_summary.value.text() == "6 núcleos / 12 hilos"


def test_the_vrm_tile_reads_the_flat_key_the_performance_payload_publishes(qtbot):
    """``vrm_temp`` is where it lives; only the dashboard state nests it."""
    from frontends.desktop.pages.cpu_overview_integration import _overview_state

    class FakeTile:
        def __init__(self):
            self.value = self.label = self.detail = type(
                "L", (), {"text": staticmethod(lambda: "--")}
            )()

    page = type("P", (), {
        "frequency_metric": FakeTile(), "voltage_metric": FakeTile(),
        "temperature_metric": FakeTile(), "power_metric": FakeTile(),
        "core_unlock_button": type("B", (), {"isEnabled": staticmethod(lambda: False)})(),
    })()

    state = _overview_state(page, {"performance": {"vrm_temp": 51.5}}, Gddr6State())

    assert state.vrm_temperature_c == 51.5


def test_the_telemetry_tile_mirrors_the_shared_gddr6_reading(qtbot):
    """The card is gone, but the average still belongs on the metrics strip."""
    view = _view(qtbot)
    chips = tuple(Gddr6Chip(index=index, code=0x31, temperature_c=58.0) for index in range(8))

    view.apply_state(CpuOverviewState(gddr6=Gddr6State(
        **READY, patch_active=True, chips=chips, average_c=58.0, hotspot_c=60.0,
    )))

    assert view.memory_tile.value.text() == "58.0 °C"
    assert "60.0 °C" in view.memory_tile.detail.text()


def test_the_telemetry_tile_waits_rather_than_inventing_a_number(qtbot):
    view = _view(qtbot)

    view.apply_state(CpuOverviewState(gddr6=Gddr6State(**READY)))

    assert view.memory_tile.value.text() != "0.0 °C"
