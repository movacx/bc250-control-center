from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


class ProbeRepository(DependenciasRepository):
    def __init__(self, root):
        self.root = root
        self.failures = set()

    def _tool_dir(self):
        return self.root

    def _command_path(self, _name):
        if "command" in self.failures:
            raise OSError("command probe failed")
        return ""

    def _cu_script_local(self, folder):
        if folder in self.failures:
            raise OSError("local probe failed")
        return ""

    def _cu_steamos_installed_script(self, _preferred=""):
        if "installed" in self.failures:
            raise RuntimeError("installed probe failed")
        return ""

    def _buscar_archivo(self, _pattern):
        if "search" in self.failures:
            raise ValueError("search failed")
        return ""

    def _buscar_directorio_con(self, *_args):
        if "directory" in self.failures:
            raise OSError("directory search failed")
        return ""


def test_all_optional_cu_probe_failures_return_a_stable_steamos_missing_state(tmp_path):
    repo = ProbeRepository(tmp_path)
    repo.failures = {
        "command", "bc250-cu-live-manager", "bc250-cu-live-manager-steamos",
        "installed", "search", "directory",
    }

    probe = repo._probe_cu_inventory(is_steamos=True)

    assert probe["command"] == ""
    assert probe["standard_path"] == ""
    assert probe["steamos_path"] == ""
    assert probe["selection"].backend == "steamos"
    assert probe["selection"].exists is False
    assert probe["selection"].blocked is True
    assert probe["expected_steamos_repository"] == tmp_path / "bc250-cu-live-manager-steamos"


def test_standard_backend_failure_does_not_hide_a_valid_steamos_backend(tmp_path):
    steamos = tmp_path / "bc250-cu-live-manager-steamos" / "bc250-cu-live-manager-bc250.sh"
    steamos.parent.mkdir()
    steamos.write_text("#!/bin/sh\n", encoding="utf-8")
    repo = ProbeRepository(tmp_path)
    repo._cu_script_local = lambda folder: (
        str(steamos) if folder == "bc250-cu-live-manager-steamos" else ""
    )
    repo._buscar_archivo = lambda _pattern: (_ for _ in ()).throw(OSError("search failed"))

    probe = repo._probe_cu_inventory(is_steamos=True)

    assert probe["steamos_exists"] is True
    assert probe["selection"].manager == str(steamos)
    assert probe["selection"].exists is True
    assert probe["selection"].blocked is False


def test_non_steamos_probe_keeps_standard_backend_selection(tmp_path):
    standard = tmp_path / "bc250-cu-live-manager" / "bc250-cu-live-manager.sh"
    standard.parent.mkdir()
    standard.write_text(
        "BC-250 live CU/WGP manager\nenable-wgp\nwrite-service-table\n",
        encoding="utf-8",
    )
    repo = ProbeRepository(tmp_path)
    repo._cu_script_local = lambda folder: (
        str(standard) if folder == "bc250-cu-live-manager" else ""
    )

    probe = repo._probe_cu_inventory(is_steamos=False)

    assert probe["standard_exists"] is True
    assert probe["standard_backend"] == "standard"
    assert probe["selection"].manager == str(standard)
    assert probe["selection"].blocked is False
