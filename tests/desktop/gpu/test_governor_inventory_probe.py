from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


class Config:
    def __init__(self, value="auto", error=None):
        self.value = value
        self.error = error

    def leer_config(self):
        if self.error:
            raise self.error
        return {"gpu_governor": self.value}


class ProbeRepository(DependenciasRepository):
    def __init__(self, preference="auto"):
        self.configuracion = Config(preference)

    def _command_path(self, _name):
        return ""

    def _ejecutar(self, *_args, **_kwargs):
        raise OSError("systemctl probe unavailable")


def test_governor_probe_failure_returns_complete_conservative_context():
    probe = ProbeRepository()._probe_governor_inventory()
    context = probe["context"]

    assert context["selected"] == "cyan-skillfish-governor-smu"
    assert context["preference"] == "auto"
    assert context["reason"] == "probe-failed"
    assert context["conflicts"] == []
    assert set(context["detected"]) == {
        "cyan-skillfish-governor-smu", "oberon-governor",
    }
    assert not any(item["detected"] for item in context["detected"].values())
    assert probe["command"] == ""


def test_explicit_oberon_preference_survives_probe_failure_for_preparation():
    probe = ProbeRepository("oberon")._probe_governor_inventory()

    assert probe["context"]["preference"] == "oberon-governor"
    assert probe["context"]["selected"] == "oberon-governor"
    assert probe["context"]["reason"] == "probe-failed"


def test_configuration_read_failure_falls_back_to_auto_cyan():
    repo = ProbeRepository()
    repo.configuracion = Config(error=ValueError("invalid config"))

    probe = repo._probe_governor_inventory()

    assert probe["context"]["preference"] == "auto"
    assert probe["context"]["selected"] == "cyan-skillfish-governor-smu"
