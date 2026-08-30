from bc250cc.infrastructure.governor_conflicts import (
    KNOWN_INCOMPATIBLE_GOVERNORS,
    GovernorConflictError,
    ensure_no_incompatible_governors,
)


class FakeRepository:
    def __init__(self, states):
        self.states = states

    def _ejecutar(self, command, timeout=3):
        key = tuple(command)
        return self.states.get(key, (1, "", "not found"))


def test_oberon_active_blocks_governor(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: type("Init", (), {"kind": "systemd"})(),
    )
    repo = FakeRepository({
        ("systemctl", "is-active", "oberon-governor.service"): (0, "active", ""),
        ("systemctl", "is-enabled", "oberon-governor.service"): (0, "enabled", ""),
    })
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts.shutil.which", lambda _name: None)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")

    try:
        ensure_no_incompatible_governors(repo)
    except GovernorConflictError as error:
        assert error.conflicts[0]["identifier"] == "oberon-governor"
        assert error.conflicts[0]["active"] is True
        assert "green screen" in str(error)
    else:
        raise AssertionError("The incompatible governor must block the operation")


def test_explicit_confirmation_allows_detected_governor(monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.governor_conflicts.detect_init_manager",
        lambda: type("Init", (), {"kind": "systemd"})(),
    )
    repo = FakeRepository({
        ("systemctl", "is-active", "oberon-governor.service"): (0, "active", ""),
    })
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts.shutil.which", lambda _name: None)
    monkeypatch.setattr("bc250cc.infrastructure.governor_conflicts._find_unit", lambda _service: "")
    conflicts = ensure_no_incompatible_governors(repo, confirmed=True)
    assert conflicts and conflicts[0]["active"] is True


def test_known_oberon_forks_share_the_detected_runtime_contract():
    sources = KNOWN_INCOMPATIBLE_GOVERNORS[0]["known_sources"]
    assert "gitlab.com/mothenjoyer69/oberon-governor" in sources
    assert "github.com/filippor/oberon-governor" in sources
    assert "github.com/alexghow903/oberon-governor" in sources
