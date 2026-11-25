"""One action prepares the connection: only what is missing, in order, stopping at a failure."""

import pytest

from bc250cc.application.system import web_access, web_setup
from bc250cc.shared.errors import ActionNeeded


class Board:
    """A board whose pieces change as the steps run."""

    def __init__(self, monkeypatch, **state):
        self.state = {"running": False, "lan": False, "tls": True, "firewall": {"state": "disabled"},
                      "name_health": {"status": "disabled", "repairable": False}, **state}
        self.calls = []
        monkeypatch.setattr(web_access, "configure", self.configure)
        monkeypatch.setattr(web_access, "start", self.start)
        monkeypatch.setattr(web_access, "repair_firewall", self.firewall)
        monkeypatch.setattr(web_access, "repair_local_name", self.name)

    def status(self):
        return dict(self.state)

    def configure(self, **changes):
        self.calls.append(("configure", changes))
        self.state.update(changes, firewall={"state": "blocked", "repairable": True})

    def start(self):
        self.calls.append("start")
        self.state.update(running=True)

    def firewall(self):
        self.calls.append("firewall")
        self.state["firewall"] = {"state": "ready", "repairable": False}
        return self.state["firewall"]

    def name(self):
        self.calls.append("name")
        self.state["name_health"] = {"status": "ready", "repairable": False}

    def apply(self, said=None):
        now = [0.0]
        return web_setup.apply((said if said is not None else []).append, status=self.status,
                               sleep=lambda seconds: now.__setitem__(0, now[0] + seconds), clock=lambda: now[0])


def test_from_nothing_to_a_ready_connection_in_one_go(monkeypatch):
    board, said = Board(monkeypatch), []
    assert web_setup.pending(board.status()) == [web_setup.LAN, web_setup.START]
    board.state["name_health"] = {"status": "resolver_failed", "repairable": True}
    final = board.apply(said)
    assert board.calls == [("configure", {"lan": True, "tls": True}), "start", "firewall", "name"]
    assert said == [web_setup.LAN, web_setup.START, web_setup.FIREWALL, web_setup.NAME]
    assert web_setup.pending(final) == []


def test_what_is_right_is_left_alone(monkeypatch):
    board = Board(monkeypatch, running=True, lan=True, firewall={"state": "ready"})
    assert web_setup.pending(board.status()) == []
    board.apply()
    assert board.calls == []


def test_only_the_two_network_repairs_are_offered_together(monkeypatch):
    board = Board(monkeypatch, running=True, lan=True, firewall={"state": "blocked", "repairable": True},
                  name_health={"status": "publication_failed", "repairable": True})
    assert web_setup.pending(board.status()) == [web_setup.FIREWALL, web_setup.NAME]
    board.apply()
    assert board.calls == ["firewall", "name"]


def test_a_name_that_only_needs_a_moment_is_not_repaired(monkeypatch):
    board = Board(monkeypatch, running=True, lan=True, name_health={"status": "publication_failed", "repairable": True})
    left = [3]

    def status():
        left[0] -= 1
        if left[0] < 0:
            board.state["name_health"] = {"status": "ready", "repairable": False}
        return dict(board.state)

    board.status = status
    board.apply()
    assert board.calls == []


def test_a_failure_ends_it_there(monkeypatch):
    board = Board(monkeypatch, running=True, lan=True, firewall={"state": "blocked", "repairable": True},
                  name_health={"status": "resolver_failed", "repairable": True})

    def refuse():
        raise ActionNeeded("LAN firewall repair was cancelled or failed.")

    monkeypatch.setattr(web_access, "repair_firewall", refuse)
    with pytest.raises(ActionNeeded, match="cancelled"):
        board.apply()
    assert board.calls == []


def test_the_port_can_be_changed_and_only_to_a_valid_one(monkeypatch, tmp_path):
    from bc250cc.infrastructure import web_control

    monkeypatch.setattr(web_control, "settings_path", lambda: tmp_path / "web.json")
    monkeypatch.setattr(web_control, "_listening", lambda port: False)
    assert web_control.configure(port=9000)["port"] == 9000
    for bad in (80, 70000, True, "9001"):
        with pytest.raises(ValueError):
            web_control.configure(port=bad)
