"""A compatibility change that applied must not be undone by a quiet D-Bus.

Cyan can be running with the requested settings while its bus answers nothing:
``gpu-usage.method = "process"`` pins a core on a stock BC-250 and starves the
D-Bus thread, so every property read times out. The flow used to treat that as
"Cyan rejected the settings", roll the TOML back, and restart the governor
again — throwing away a change that had in fact been applied.

Restoring the previous runtime range is best effort. Only a governor that will
not come back up is a rejection.
"""

from __future__ import annotations

import pytest

from bc250cc.infrastructure.gpu_repository import GPURepository


class _Repo(GPURepository):
    """Drives the real method with every side effect stubbed out."""

    def __init__(self, *, restart_ok=True, range_ok=True, read_range=(1000, 1850)):
        self._restart_ok = restart_ok
        self._range_ok = range_ok
        self._read_range = read_range
        self.toml_writes = []
        self.restarts = 0
        self.estado_bc250_cache = None

    # -- collaborators the method reaches for -----------------------------
    def _current_cyan_compatibility(self):
        return ("smu", "busy-flag", False, False)

    def _service_is_active(self, _service):
        return True

    def _cyan_metrics_overlay_available(self):
        return True

    def _cyan_kernel_usage_available(self):
        return True

    def _cyan_kernel_set_method_available(self):
        return True

    def _leer_rango_governor(self, _kind):
        return self._read_range

    def _editar_governor_toml(self, *args):
        self.toml_writes.append(args)
        return "TOML updated."

    def _restart_governor_if_active(self, _service):
        self.restarts += 1
        if not self._restart_ok:
            raise RuntimeError("Cyan failed to start with the new configuration.")
        return True

    def _restart_governor(self, _service):
        self.restarts += 1

    def _restaurar_rango_governor(self, _previous, **_kwargs):
        if not self._range_ok:
            raise RuntimeError(
                "The governor restarted, but its previous runtime range could not "
                "be restored safely. D-Bus range objects did not become ready."
            )
        return self._read_range


def _apply(repo, set_method="kernel", usage="process"):
    return repo.configurar_compatibilidad_gpu_cyan(set_method, usage, False, False)


def test_a_silent_dbus_keeps_the_settings_the_user_asked_for():
    repo = _Repo(range_ok=False)
    message = _apply(repo)

    assert "rejected" not in message.lower()
    assert "are active" in message
    # One write, no rollback write, and no second restart.
    assert len(repo.toml_writes) == 1
    assert repo.toml_writes[0][1:] == ("kernel", "process", False, False)
    assert repo.restarts == 1


def test_the_message_still_says_the_range_was_not_restored():
    repo = _Repo(range_ok=False)
    message = _apply(repo)
    assert "runtime range could not be put back" in message
    assert "D-Bus range objects did not become ready" in message


def test_a_governor_that_will_not_start_is_still_a_rejection():
    repo = _Repo(restart_ok=False)
    with pytest.raises(RuntimeError, match="rejected the requested compatibility"):
        _apply(repo)
    # The previous settings were written back.
    assert repo.toml_writes[-1][1:] == ("smu", "busy-flag", False, False)


def test_the_happy_path_still_reports_the_preserved_range():
    repo = _Repo()
    message = _apply(repo)
    assert "Runtime range preserved at 1000-1850 MHz" in message
    assert repo.restarts == 1


@pytest.mark.parametrize(
    "set_method, usage",
    [("smu", "busy-flag"), ("smu", "process"), ("kernel", "busy-flag"), ("kernel", "process")],
)
def test_every_combination_cyan_accepts_is_accepted_here(set_method, usage):
    """Measured against the daemon on a stock BC-250: only usage=kernel fails."""
    repo = _Repo()
    message = _apply(repo, set_method, usage)
    assert "rejected" not in message.lower()
    assert repo.toml_writes[0][1:] == (set_method, usage, False, False)


class _MuteBusRepo(_Repo):
    """Cyan is running and configured, but its bus answers nothing at all."""

    def _leer_rango_governor(self, _kind):
        return None


def test_a_mute_bus_does_not_trap_the_user_on_the_broken_method():
    """The read that protects the range must not block the escape from it.

    ``gpu-usage.method = "process"`` starves Cyan's D-Bus thread. Refusing to
    change compatibility because the range cannot be read left the only way
    out of that method behind the very thing it had broken.
    """
    repo = _MuteBusRepo()
    message = _apply(repo, "smu", "busy-flag")

    assert "are active" in message
    assert repo.toml_writes[0][1:] == ("smu", "busy-flag", False, False)
    assert repo.restarts == 1


def test_a_mute_bus_says_the_range_has_to_be_reapplied():
    repo = _MuteBusRepo()
    message = _apply(repo, "smu", "busy-flag")
    assert "did not answer" in message
    assert "apply a range from the GPU page" in message


def test_the_privileged_write_is_actually_reached_with_a_mute_bus():
    """It used to raise first, so no privileged call ran and Polkit never asked."""
    repo = _MuteBusRepo()
    _apply(repo, "smu", "busy-flag")
    assert repo.toml_writes, "the TOML write never ran, so no authorization was requested"


def test_a_mute_bus_plus_a_dead_governor_is_still_a_rejection():
    repo = _MuteBusRepo(restart_ok=False)
    with pytest.raises(RuntimeError, match="rejected the requested compatibility"):
        _apply(repo, "smu", "busy-flag")
    assert repo.toml_writes[-1][1:] == ("smu", "busy-flag", False, False)
