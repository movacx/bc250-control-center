from types import SimpleNamespace

import pytest

from bc250cc.application.system.process_termination_policy import (
    ProcessIdentity,
    authorize_process_termination,
)
from bc250cc.domain.common.proceso import Proceso
from bc250cc.infrastructure.system_service import SistemaService


def _identity(**changes):
    values = {"pid": 400, "create_time": 12.5, "uid": 1000, "name": "game", "command": "game --run"}
    values.update(changes)
    return ProcessIdentity(**values)


@pytest.mark.parametrize(
    ("changes", "expected", "critical", "reason"),
    [
        ({"pid": 99}, 12.5, False, "controller-process"),
        ({"uid": 0}, 12.5, False, "different-owner"),
        ({}, 12.5, True, "critical-process"),
        ({"create_time": 13.0}, 12.5, False, "pid-reused"),
    ],
)
def test_termination_policy_rejects_unsafe_identity(changes, expected, critical, reason):
    decision = authorize_process_termination(
        _identity(**changes),
        expected_create_time=expected,
        owner_uid=1000,
        controller_pid=99,
        critical=critical,
    )

    assert (decision.allowed, decision.reason) == (False, reason)


def test_termination_policy_authorizes_matching_owned_noncritical_process():
    decision = authorize_process_termination(
        _identity(),
        expected_create_time=12.5,
        owner_uid=1000,
        controller_pid=99,
        critical=False,
    )

    assert (decision.allowed, decision.reason) == (True, "authorized")


def test_termination_policy_rejects_malformed_expected_birth_time():
    decision = authorize_process_termination(
        _identity(),
        expected_create_time="not-a-timestamp",
        owner_uid=1000,
        controller_pid=99,
        critical=False,
    )

    assert (decision.allowed, decision.reason) == (False, "invalid-identity")


def test_process_service_rechecks_identity_before_force_kill(monkeypatch):
    class FakeProcess:
        pid = 400

        def __init__(self):
            self.birth_reads = iter((12.5, 99.0))
            self.signals = []
            self.killed = False

        def create_time(self):
            return next(self.birth_reads)

        def uids(self):
            return SimpleNamespace(real=1000)

        def name(self):
            return "game"

        def cmdline(self):
            return ["game", "--run"]

        def send_signal(self, value):
            self.signals.append(value)

        def is_running(self):
            return True

        def kill(self):
            self.killed = True

    fake = FakeProcess()
    monkeypatch.setattr("bc250cc.infrastructure.system_service.psutil.Process", lambda _pid: fake)
    monkeypatch.setattr("bc250cc.infrastructure.system_service.psutil.wait_procs", lambda _items, timeout: ([], [fake]))
    service = SistemaService(object())
    service.uid = 1000
    service.pid_actual = 99

    forced = service.cerrar_procesos([Proceso(400, "game", 1, "game", create_time=12.5)])

    assert len(fake.signals) == 1
    assert fake.killed is False
    assert forced == []
