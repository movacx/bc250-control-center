from bc250cc.infrastructure.cpu_repository import CPURepository


class _Repository(CPURepository):
    def __init__(self, immutable: bool):
        self._immutable = immutable

    def _es_ostree(self):
        return self._immutable


def test_bazzite_missing_cpu_helper_points_to_the_rpm_ostree_boundary():
    message = _Repository(True)._missing_cpu_smu_helper_message()

    assert "matching BC250 Control Center RPM" in message
    assert "rpm-ostree" in message
    assert "reboot" in message
    assert "install-local.sh cannot" in message


def test_mutable_distribution_keeps_the_local_installer_recovery_path():
    message = _Repository(False)._missing_cpu_smu_helper_message()

    assert "system package" in message
    assert "scripts/install-local.sh" in message
    assert "rpm-ostree" not in message
