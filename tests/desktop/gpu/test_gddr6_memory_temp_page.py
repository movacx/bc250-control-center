from types import SimpleNamespace

from frontends.desktop.pages.gddr6_memory_temp import Gddr6MemoryTempPage


class FakeController:
    def estado_gddr6_memory_temp(self):
        return {
            "hardware_detected": True,
            "helper_ready": False,
            "repository_ready": False,
            "payload_present": False,
            "repository_path": "/home/user/bc250-memory-temperature",
        }

    def comando_preparar_gddr6_memory_temp(self):
        return SimpleNamespace()

    def comando_leer_temperatura_vram(self):
        return []

    def comando_aplicar_parche_vram(self):
        return []


def test_page_constructs_and_disables_actions_when_not_ready(qtbot):
    page = Gddr6MemoryTempPage(FakeController())
    qtbot.addWidget(page)

    page._apply_status(page.controller.estado_gddr6_memory_temp())

    assert page.read_button.isEnabled() is False
    assert page.apply_button.isEnabled() is False


def test_page_enables_actions_once_repository_and_helper_are_ready(qtbot):
    page = Gddr6MemoryTempPage(FakeController())
    qtbot.addWidget(page)

    page._apply_status({
        "hardware_detected": True,
        "helper_ready": True,
        "repository_ready": True,
        "payload_present": True,
        "repository_path": "/home/user/bc250-memory-temperature",
    })

    assert page.read_button.isEnabled() is True
    assert page.apply_button.isEnabled() is True


def test_set_updates_active_starts_and_stops_the_status_poll(qtbot):
    page = Gddr6MemoryTempPage(FakeController())
    qtbot.addWidget(page)

    page.set_updates_active(True)
    assert page.auto_refresh_timer.isActive() is True

    page.set_updates_active(False)
    assert page.auto_refresh_timer.isActive() is False
