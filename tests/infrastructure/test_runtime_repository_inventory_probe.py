from types import SimpleNamespace

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


class RuntimeProbeRepository(DependenciasRepository):
    def _command_path(self, name):
        if name in {"umr", "stress"}:
            raise OSError(f"{name} probe failed")
        return f"/usr/bin/{name}" if name in {"python3", "git", "sensors"} else ""

    def _git_path(self):
        raise RuntimeError("git override probe failed")


class RepositoryProbeRepository(DependenciasRepository):
    def __init__(self, root):
        self.root = root

    def _tool_dir(self):
        return self.root

    def _buscar_directorio_con(self, *_args):
        raise OSError("repository search failed")

    def _gfx1013_compute_state(self, _os_repository):
        raise RuntimeError("compute policy probe failed")


def test_runtime_probe_keeps_independent_commands_when_optional_checks_fail():
    commands = RuntimeProbeRepository()._probe_runtime_inventory()

    assert commands["python3"] == "/usr/bin/python3"
    assert commands["git"] == "/usr/bin/git"
    assert commands["sensors"] == "/usr/bin/sensors"
    assert commands["umr"] == ""
    assert commands["stress"] == ""
    assert commands["bc250_detect"] == ""


def test_optional_dependency_status_reuses_snapshot_without_new_command_probes():
    repo = RuntimeProbeRepository()
    snapshot = {"sensors": "/usr/bin/sensors", "git": "/usr/bin/git"}
    repo._command_path = lambda _name: (_ for _ in ()).throw(
        AssertionError("inventory must reuse the supplied snapshot")
    )

    status = repo._optional_dependency_status(snapshot)

    assert status["sensors"]["available"] is True
    assert status["git"]["available"] is True
    assert status["stress"]["available"] is False


def test_system_dbus_probe_requires_a_working_bus_not_only_busctl_binary():
    calls = []

    def working(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    def offline(_argv, **_kwargs):
        return SimpleNamespace(returncode=1)

    assert DependenciasRepository._system_dbus_ready('/usr/bin/busctl', runner=working) is True
    assert calls[0][0] == ['/usr/bin/busctl', '--system', 'list']
    assert calls[0][1]['timeout'] == 2
    assert DependenciasRepository._system_dbus_ready('/usr/bin/busctl', runner=offline) is False
    assert DependenciasRepository._system_dbus_ready('', runner=working) is False


def test_repository_probe_localizes_search_and_compute_failures(tmp_path):
    cyan_marker = tmp_path / "cyan-skillfish-governor-smu" / "src" / "gpu_frequency_fix.rs"
    cyan_marker.parent.mkdir(parents=True)
    cyan_marker.write_text("// fixture\n", encoding="utf-8")
    repo = RepositoryProbeRepository(tmp_path)

    inventory = repo._probe_repository_inventory(SimpleNamespace())

    assert inventory["smu_path"] == ""
    assert inventory["smu_exists"] is False
    assert inventory["cyan_exists"] is True
    assert inventory["core_unlock_exists"] is False
    assert inventory["steamos_fix_exists"] is False
    assert inventory["gfx1013_compute"] == {
        "supported": False,
        "state": "probe-failed",
    }
