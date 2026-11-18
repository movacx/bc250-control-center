"""The interface learns the SteamOS providers only through the application layer."""
from bc250cc.application.preparation import steamos_providers as providers


def test_nothing_is_protected_when_no_native_configuration_claims_a_component():
    assert providers.protected_actions({}) == frozenset()
    assert providers.protected_actions(None) == frozenset()
    assert providers.protected_actions({'acpi': [], 'video': None}) == frozenset()


def test_a_claimed_component_protects_only_its_own_actions():
    protected = providers.protected_actions({'acpi': ['/etc/native-acpi']})
    assert protected == {'acpi-install', 'acpi-revert'}
    video = providers.protected_actions({'video': ['native VA-API environment']})
    assert video == {'video-install', 'video-revert'}


def test_cec_keeps_its_read_only_status_available():
    protected = providers.protected_actions({'cec': ['native CEC configuration']})
    assert 'cec-setup' in protected and 'cec-wake-install' in protected
    assert 'cec-status' not in protected


def test_the_closed_action_sets_come_from_the_adapters():
    assert 'proton-install' in providers.real_toolkit_action_keys()
    assert 'graphics-install' in providers.alternative_action_keys()
    assert set(providers.alternative_action_keys()) == set(providers.ALTERNATIVE_ACTIONS)
