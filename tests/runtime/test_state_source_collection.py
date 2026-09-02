from frontends.desktop.core.state import (
    ControllerStateCache,
    _dashboard_sources,
    collect_named_sources,
)


def test_named_sources_keep_successful_data_when_one_loader_fails():
    def broken():
        raise AttributeError("missing persistence contract")

    payload, errors = collect_named_sources(
        (
            ("performance", lambda: {"cpu_freq": 3850}),
            ("persistent", broken),
            ("core_unlock", lambda: {"logical_cpus": 12}),
        )
    )

    assert payload["performance"] == {"cpu_freq": 3850}
    assert payload["persistent"] == {}
    assert payload["core_unlock"] == {"logical_cpus": 12}
    assert errors == {"persistent": "missing persistence contract"}


def test_named_sources_preserve_empty_success_without_false_error():
    payload, errors = collect_named_sources((("optional", lambda: {}),))
    assert payload == {"optional": {}}
    assert errors == {}


def test_core_unlock_status_is_short_lived_cached_between_cpu_refreshes():
    class Controller:
        def __init__(self):
            self.calls = 0

        def estado_desbloqueo_nucleos_cpu(self):
            self.calls += 1
            return {"supported_stock_shape": True, "helper_ready": True}

    controller = Controller()
    cache = ControllerStateCache(controller)

    assert cache.core_unlock()["helper_ready"] is True
    assert cache.core_unlock()["supported_stock_shape"] is True
    assert controller.calls == 1


def test_cpu_boot_tuning_exposes_only_verified_boot_persistence():
    class Controller:
        def estado_cpu_oc_persistente(self):
            return {
                "applied_this_boot": True,
                "config": {"valid": True, "frequency": 3900, "scale": -30},
            }

    active = ControllerStateCache(Controller()).cpu_boot_tuning()

    assert active["source"] == "boot"
    assert active["frequency"] == 3900
    assert active["scale"] == -30


def test_cpu_boot_tuning_hides_a_profile_not_applied_this_boot():
    class Controller:
        def estado_cpu_oc_persistente(self):
            return {
                "applied_this_boot": False,
                "config": {"valid": True, "frequency": 3850, "scale": -35},
            }

    assert ControllerStateCache(Controller()).cpu_boot_tuning() == {}


def test_dashboard_source_adapter_keeps_other_sources_when_events_fail():
    cache = type(
        "Cache",
        (),
        {
            "performance": lambda _self: {"cpu_freq": 3700},
            "gpu": lambda _self: {"device": "BC250"},
            "tools": lambda _self: {},
            "fans": lambda _self: {},
            "cu_cache": lambda _self: {"active_cus": 36},
            "cpu_boot_tuning": lambda _self: {"source": "boot", "frequency": 3700, "scale": -20},
            "events": lambda _self, _limit: (_ for _ in ()).throw(RuntimeError("history unavailable")),
        },
    )()

    performance, gpu, tools, fans, cu, cpu_tuning, events = _dashboard_sources(cache)

    assert performance == {"cpu_freq": 3700}
    assert gpu == {"device": "BC250"}
    assert cu == {"active_cus": 36}
    assert cpu_tuning == {"source": "boot", "frequency": 3700, "scale": -20}
    assert tools == fans == {}
    assert events == []


def test_dashboard_source_adapter_rejects_wrong_result_shapes():
    cache = type(
        "Cache",
        (),
        {
            "performance": lambda _self: "not a mapping",
            "gpu": lambda _self: None,
            "tools": lambda _self: [],
            "fans": lambda _self: 1,
            "cu_cache": lambda _self: object(),
            "cpu_boot_tuning": lambda _self: None,
            "events": lambda _self, _limit: [None, {"title": "valid"}],
        },
    )()

    *states, events = _dashboard_sources(cache)

    assert states == [{}, {}, {}, {}, {}, {}]
    assert events == [{"title": "valid"}]
