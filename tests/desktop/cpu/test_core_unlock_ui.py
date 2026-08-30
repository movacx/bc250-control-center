from frontends.desktop.pages.cpu_smu import CpuSmuPage


def test_core_unlock_button_survives_a_transient_eligibility_refresh_failure(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    ready = {
        "physical_cores": 6,
        "logical_cpus": 12,
        "supported_stock_shape": True,
        "helper_ready": True,
        "repository_ready": True,
        "repository_path": "/home/user/.local/share/bc250-control-center/tools/bc250-core-unlock",
        "cores": [],
    }
    payload = {
        "performance": {},
        "tools": {},
        "persistent": {},
        "detection": {},
        "scale_live": {},
        "quick_access": {},
        "core_unlock": ready,
        "_errors": {},
    }
    page._apply_refresh_payload(payload)
    assert page.core_unlock_button.isEnabled()

    payload["core_unlock"] = {}
    payload["_errors"] = {"core_unlock": "temporary service probe failure"}
    page._apply_refresh_payload(payload)

    assert page.core_unlock_button.isEnabled()


def test_core_unlock_button_explains_missing_privileged_helper():
    calls = []
    page = type("Page", (), {
        "_request_core_unlock": CpuSmuPage._request_core_unlock,
        "process": None,
        "current_state": {
            "core_unlock_repository_ready": True,
            "core_unlock_helper_ready": False,
        },
        "_show_info": lambda self, title, message, **options: calls.append(
            (title, message, options)
        ),
    })()
    page._request_core_unlock()
    assert calls
    assert calls[0][0] == "CPU core unlock support is not installed"
    assert "reinstall" in calls[0][1].lower()
    assert calls[0][2]["tone"] == "orange"


def test_core_unlock_button_requires_official_upstream_clone_first():
    calls = []
    page = type("Page", (), {
        "_request_core_unlock": CpuSmuPage._request_core_unlock,
        "process": None,
        "current_state": {
            "core_unlock_repository_ready": False,
            "core_unlock_helper_ready": True,
        },
        "_show_info": lambda self, title, message, **options: calls.append(
            (title, message, options)
        ),
    })()
    page._request_core_unlock()
    assert calls
    assert calls[0][0] == "Official CPU core unlock tool is not prepared"
    assert "rw-r-r-0644/bc250-core-unlock" in calls[0][1]
    assert calls[0][2]["tone"] == "orange"
