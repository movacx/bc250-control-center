"""Handbook integrity and the search decisions that select user-facing advice."""
import json
import re
import shlex
import subprocess

import pytest

from bc250cc.shared import known_errors as handbook


def test_complete_public_catalog_schema_and_privacy():
    catalog = handbook.catalog()
    assert catalog["schema_version"] == 1
    modules = {module["id"] for module in catalog["modules"]}
    entries = handbook.load()
    assert len(modules) == 15 and len(entries) == 83
    assert len({entry["id"] for entry in entries}) == len(entries)
    assert not re.search(r"R-[0-9a-f]{8}|/home/movacx|\"reports\"", json.dumps(catalog))
    expected = {"fixed", "fixed-dev", "user", "pending", "expected", "analysis"}
    for entry in entries:
        assert entry["module"] in modules
        assert entry["owner"] in {"user", "developer", "both", "expected"}
        assert entry["status"] in expected
        assert set(entry["status_flags"]) <= expected
        for field in ("title", "symptom", "cause", "developer"):
            assert set(entry[field]) == {"en", "es"}
            assert all(isinstance(text, str) and text.strip() for text in entry[field].values())
        for text in (entry["guide"]["title"], entry["guide"]["summary"]):
            assert set(text) == {"en", "es"} and all(text.values())
        assert all(re.fullmatch(r"BC250-[A-Z0-9]+-\d{3}", code) for code in entry["codes"])
        assert all(isinstance(words, list) for words in entry["keywords"].values())
        for pattern in entry["match"]:
            re.compile(pattern)
        assert set(entry["fix"]) == set(handbook.FAMILIES)
        for fix in entry["fix"].values():
            if fix is None:
                continue
            assert set(fix["steps"]) == {"en", "es"}
            assert all(fix["steps"].values())
            assert isinstance(fix["command"], str)
            assert fix["scope"] in {"applicable", "equivalent", "conditional"}
            assert fix["article"]
            for block in fix["article"]:
                assert set(block["text"]) == {"en", "es"}
                assert all(block["text"].values())
                assert isinstance(block["commands"], list)
                assert all(isinstance(command, str) and command.strip() for command in block["commands"])
                assert not any(re.search(r"<[^>]+>|rm -rf|pacman -Rdd", command) for command in block["commands"])
        assert entry["fixed_in"] is None or re.fullmatch(r"\d+\.\d+\.\d+", entry["fixed_in"])


@pytest.mark.parametrize("query,identity", [
    ("BC250-PKG-006", "PKG-05"), ("pkg 006", "PKG-05"), ("PKG006", "PKG-05"),
    ("inst 09", "INST-09"), ("paquete corrupto", "PKG-05"),
    ("PACOTE CORROMPIDO", "PKG-05"), ("повреждённый пакет", "PKG-05"),
    ("beschädigtes Paket", "PKG-05"), ("디스크 사용량", "IDEA-02"),
    ("Not authorized", "AUTH-01"), ("Internal compiler error: access violation", "UPS-03"),
    ("force=1 refused: chip ID 0xffff", "FAN-01"),
])
def test_searches_codes_raw_messages_and_multilingual_keywords(query, identity):
    assert handbook.search(query, "es")[0]["id"] == identity


def test_search_normalizes_accents_and_hyphens_and_filters_modules():
    assert handbook.search("AUTORIZACION", "es")[0]["id"] == "AUTH-01"
    assert handbook.search("not authorized", module="fans") == ()
    assert {entry["id"] for entry in handbook.search("", module="fans")} == {
        "FAN-01", "FAN-02", "FAN-03", "FAN-04",
    }
    assert handbook.search("unrecognised nonsense qxzxq") == ()


def test_shared_codes_keep_both_install_and_runtime_candidates():
    assert {entry["id"] for entry in handbook.for_code("BC250-UMR-001")} == {"CU-01", "CU-02"}
    assert handbook.for_message("cannot find the UMR executable")[0]["id"] == "CU-01"
    assert handbook.for_message("umr: error while loading shared libraries: libLLVM.so")[0]["id"] == "CU-02"


def test_actual_error_outranks_a_historically_wrong_code():
    entries = handbook.for_message("BC250-DBUS-001 curl: (22) The requested URL returned error: 504")
    assert entries[0]["id"] == "GFX-03"
    assert {entry["id"] for entry in handbook.for_message("BC250-GPU-900 Not authorized")} == {"AUTH-01"}


def test_distro_specific_advice_does_not_fall_through_to_another_backend():
    ppa = handbook.for_id("PKG-10")
    assert handbook.fix_for(ppa, "linuxmint") is not None
    assert handbook.fix_for(ppa, "debian") is None
    assert handbook.fix_for(ppa, "bazzite") is None
    umr = handbook.for_id("CU-01")
    assert "pacman" in handbook.fix_for(umr, "cachyos")["command"]
    assert "rpm-ostree" in handbook.fix_for(umr, "bazzite")["command"]
    assert "apt" in handbook.fix_for(umr, "debian")["command"]
    assert handbook.fix_for(umr, "steamos")["command"] == ""
    assert handbook.fix_for(umr, "unsupported")["command"] == ""


def test_english_fallback_and_update_versions():
    entry = handbook.for_id("UPS-01")
    assert handbook.localized(entry["title"], "ko") == entry["title"]["en"]
    assert handbook.localized(entry["title"], "es-419") == entry["title"]["es"]
    assert handbook.needs_update(entry, "1.22.6")
    assert not handbook.needs_update(entry, "1.22.10")
    assert not handbook.needs_update(handbook.for_id("GOV-12"), "1.0.0")


def test_guides_distinguish_reading_the_state_from_the_actual_repair():
    steps = handbook.for_id("INST-01")["fix"]["bazzite"]["article"]
    assert steps[0]["commands"] == ["rpm-ostree status"]
    assert steps[1]["commands"] == ["rpm-ostree uninstall coolercontrol"]
    assert "reinicia" in steps[2]["text"]["es"].lower()
    assert "error nombra coolercontrol" in steps[1]["text"]["es"]


def test_mutating_commands_stay_with_their_own_package_backend():
    for entry in handbook.load():
        for family, fix in entry["fix"].items():
            if fix is None:
                continue
            commands = "\n".join(command for block in fix["article"] for command in block["commands"])
            if family in {"ubuntu", "debian"}:
                assert not re.search(r"(?m)(?:^|&&\s*|\|\|\s*)(?:sudo )?(?:pacman |rpm-ostree |dnf )", commands)
            if family == "bazzite":
                assert not re.search(r"(?m)(?:^|&&\s*|\|\|\s*)(?:sudo )?(?:pacman |apt |dnf )", commands)
            if family == "other":
                assert commands == ""


def test_cyan_article_backs_up_edits_and_guards_restart_with_validation(tmp_path):
    article = handbook.for_id("GOV-02")["fix"]["arch"]["article"]
    commands = [command for block in article for command in block["commands"]]
    backup = next(command for command in commands if "cp -a" in command)
    assert ".bak-$(date" in backup and "&&\nsudoedit" in backup
    guarded = next(command for command in commands if "systemctl restart" in command)
    assert 'print("TOML OK")' in guarded
    assert "&&\nsudo systemctl restart" in guarded
    for command in commands:
        assert subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True).returncode == 0
    # Run only the read-only validator against throwaway files. None of the
    # backup, editing or service commands execute in this test.
    argv = shlex.split(guarded.partition("&&")[0].strip())
    config = tmp_path / "config.toml"
    argv[2] = argv[2].replace("/etc/cyan-skillfish-governor-smu/config.toml", str(config))
    config.write_text("[gpu-usage]\nfix-freq = true\n")
    valid = subprocess.run(argv, text=True, capture_output=True)
    assert valid.returncode == 0 and valid.stdout.strip() == "TOML OK"
    config.write_text("gpu-usage = 1\n[gpu-usage]\nfix-freq = true\n")
    invalid = subprocess.run(argv, text=True, capture_output=True)
    assert invalid.returncode != 0 and "TOML OK" not in invalid.stdout


@pytest.mark.parametrize("text,identity", [
    ("ERROR: Cyan fix-freq is missing or invalid in config.toml", "GOV-13"),
    ("RuntimeError: The local bc250_smu_oc repository was not found. Use Prepare dependencies first", "CPU-01"),
    ("error: database already registered", "PKG-11"),
    ("dracut[F]: image generation failed for kernel '7.0.0-30-generic'.", "GFX-04"),
    ("unexpected core mask 0xb7, expected 0x77; aborting", "CU-03"),
    ("RuntimeError: no game (.exe) found in ~/.local/share/Steam/steamapps/common/Hogwarts Legacy", "UPS-07"),
])
def test_the_2026_11_19_reports_find_their_entries(text, identity):
    assert handbook.search(text)[0]["id"] == identity
