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


def test_restore_plan_queues_each_existing_install_once_in_dependency_order():
    assert providers.toolkit_restore_actions([
        {'component': 'ac3', 'action': 'ac3-install'},
        {'component': 'radv', 'action': 'combined-install'},
        {'component': 'amdgpu', 'action': 'combined-install'},
        {'component': 'aic8800', 'action': 'aic8800-legacy-install'},
        {'component': 'acpi', 'action': 'acpi-revert'},
    ]) == ('combined-install', 'ac3-install', 'aic8800-legacy-install')


def test_ownership_identifies_providers_from_their_distinct_evidence():
    toolkit = {'graphics': {'state': 'configured', 'kernel_override_installed': True},
               'components': {'acpi': True, 'cpu': True},
               'native_ownership': {'cpu': ['/etc/native-cpu']}}
    alternative = {'kernel': {'installed': True}}
    assert providers.steamos_ownership(toolkit, alternative) == {
        'real-toolkit': ('acpi', 'radv'), 'keyboardspecialist': ('amdgpu',), 'native': ('cpu',),
    }
