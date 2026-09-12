from bc250cc.domain.gpu.profiles import profiles_for_allowed_range


def test_cyan_profiles_follow_allowed_range():
    profiles = profiles_for_allowed_range(1000, 2000)

    assert [(item.key, item.minimum_mhz, item.maximum_mhz) for item in profiles] == [
        ("balanced", 1000, 1500),
        ("gaming", 1000, 1850),
        ("benchmark", 1000, 2000),
    ]


def test_mastag_range_does_not_leak_its_maximum_into_balanced():
    profiles = profiles_for_allowed_range(350, 2230)

    assert profiles[0].minimum_mhz == 500
    assert profiles[0].maximum_mhz == 1500
    assert profiles[-1].maximum_mhz == 2000


def test_oberon_has_only_its_reviewed_profiles():
    """Three now: Benchmark used to exist only in the Decky copy of this file."""
    profiles = profiles_for_allowed_range(1000, 2000, governor="oberon")

    assert [profile.key for profile in profiles] == [
        "oberon-1500",
        "oberon-1850",
        "oberon-2000",
    ]


def test_an_allowed_range_that_stops_short_hides_the_profiles_above_it():
    profiles = profiles_for_allowed_range(1000, 1850, governor="oberon")

    assert [profile.key for profile in profiles] == ["oberon-1500", "oberon-1850"]
