"""Vocabulary coverage and relevance regressions for offline support search."""
import json
import re

import pytest

from bc250cc.shared import known_errors as handbook
from bc250cc.shared import known_errors_search as engine


@pytest.mark.parametrize("module", [item["id"] for item in handbook.modules()])
def test_every_supplied_term_finds_its_module(module):
    failures = []
    for category, terms in engine.vocabulary()[module]["categories"].items():
        for term in terms:
            if not engine._words(term):
                continue
            if not any(entry["module"] == module for entry in handbook.search(term)):
                failures.append((category, term))
    assert failures == []


def test_bundled_vocabulary_is_public_and_covers_all_modules():
    data = engine.vocabulary()
    assert set(data) == {module["id"] for module in handbook.modules()}
    assert sum(len(terms) for metadata in data.values()
               for terms in metadata["categories"].values()) == 8116
    assert not re.search(r"R-[0-9a-f]{8}|/home/movacx", json.dumps(data))


@pytest.mark.parametrize("query", ["BC250-PKG-006", "pkg006", "pkg 6", "PKG-6", "pkg_006"])
def test_zero_padded_diagnostic_codes_keep_the_same_candidates(query):
    assert [entry["id"] for entry in handbook.search(query)] == ["PKG-05"]
    assert [entry["id"] for entry in handbook.for_code(query)] == ["PKG-05"]


@pytest.mark.parametrize("query,identity", [("cu1", "CU-01"), ("cu 1", "CU-01"),
                                          ("ficha CU-01", "CU-01"), ("gov12", "GOV-12"),
                                          ("PKG-06", "PKG-06")])
def test_entry_ids_outrank_diagnostic_codes(query, identity):
    match = handbook.search_matches(query)[0]
    assert match.entry["id"] == identity and match.kind == "id"


@pytest.mark.parametrize("query,module", [("no gira", "fans"), ("no gira el ventilador", "fans"),
                                        ("no hay sonido", "audio_tv"), ("cian", "governor"),
                                        ("ventoinha", "fans"), ("comput", "compute_units"),
                                        ("fsr4", "upscaling"), ("风扇", "fans")])
def test_colloquial_multilingual_and_partial_searches_prioritize_the_module(query, module):
    assert handbook.search(query)[0]["module"] == module


def test_prefixes_do_not_match_host_suffixes_or_inside_words():
    assert engine._words("https://github.com/telecom") == {"https", "github", "telecom"}
    assert len(handbook.search("com")) < 76
    assert {entry["id"] for entry in handbook.search("comput")} == {"CU-01", "CU-02", "CU-03"}
    assert handbook.normalize("VA_API / VA-API") == "va api va api"


def test_raw_multiline_error_outranks_a_historical_code_and_module_aliases():
    query = "BC250-DBUS-001\nDownload failed: curl: (22) The requested URL returned error: 504\nPlease retry."
    assert handbook.search_matches(query)[0].entry["id"] == "GFX-03"
    assert handbook.search_matches(query)[0].kind == "message"
    assert {entry["id"] for entry in handbook.for_message("BC250-UMR-001")} == {"CU-01", "CU-02"}


def test_spelling_uses_bounded_edits_and_never_changes_strict_message_lookup():
    assert handbook.search_matches("ventiladr")[0].entry["module"] == "fans"
    assert handbook.search_matches("ventiladr")[0].kind == "spelling"
    assert handbook.for_message("ventiladr") == ()
    assert engine._near("abcd") == ()
    assert engine._distance("governer", "governor", 2) == 1
    assert engine._distance("ventiladro", "ventilador", 2) == 1


def test_storage_and_video_aliases_reach_specific_guides():
    assert {"STOR-01", "MEM-02"} <= {entry["id"] for entry in handbook.search("no space left")}
    assert {entry["id"] for entry in handbook.search("vaapi")[:2]} == {"VID-03", "VID-04"}


def test_versions_use_only_published_fixed_in_and_distro_aliases_use_applicability():
    for version in ("1.22.5", "1.22.7", "1.22.9"):
        assert {entry["id"] for entry in handbook.search(version)} == {
            entry["id"] for entry in handbook.load() if entry["fixed_in"] == version}
    assert {entry["id"] for entry in handbook.search("fixed_in")} == {
        entry["id"] for entry in handbook.load() if entry["fixed_in"]}
    assert handbook.search("Mint") and handbook.search("CachyOS")


def test_empty_queries_and_stopwords_do_not_guess_a_repair():
    assert len(handbook.search("")) == 83
    assert handbook.search("el la no the") == ()
    assert handbook.search("qxzxq wvwvw xyzxyz") == ()
    assert handbook.search("no gira", module="packages") == ()
    assert handbook.search_suggestions("ventiladr", module="packages") == ()
    assert "fans" in engine.suggested_modules("ventiladres")
