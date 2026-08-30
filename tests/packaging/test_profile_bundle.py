import json

import pytest

from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal
from bc250cc.infrastructure.persistence.profile_bundle import (
    MAX_BUNDLE_BYTES,
    ProfileBundleError,
    ProfileBundleRepository,
    _checksum,
)


@pytest.fixture
def configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return ConfiguracionLocal()


def test_bundle_round_trip_and_permissions(configuration, tmp_path):
    configuration.guardar_config({"idioma": "es", "gpu_temp_warning": 79})
    destination = ProfileBundleRepository(configuration).export(tmp_path / "portable.json")
    preview = ProfileBundleRepository(configuration).preview(destination)
    assert preview.schema == 1
    assert "idioma" in preview.config_keys
    assert destination.stat().st_mode & 0o777 == 0o600


def test_modified_bundle_is_rejected(configuration, tmp_path):
    repository = ProfileBundleRepository(configuration)
    destination = repository.export(tmp_path / "portable.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["config"]["idioma"] = "pl"
    destination.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProfileBundleError, match="checksum"):
        repository.preview(destination)


def test_import_replaces_config_and_creates_backup(configuration, tmp_path):
    repository = ProfileBundleRepository(configuration)
    configuration.guardar_config({"idioma": "es"})
    exported = repository.export(tmp_path / "portable.json")
    configuration.guardar_config({"idioma": "en"})
    backup = repository.import_bundle(exported)
    assert configuration.leer_config()["idioma"] == "es"
    assert backup.is_file()
    assert backup.parent == configuration.config_path().parent / "backups"
    assert backup.parent.stat().st_mode & 0o777 == 0o700
    assert backup.stat().st_mode & 0o777 == 0o600
    assert ProfileBundleRepository(configuration).preview(backup).schema == 1


def test_failed_second_write_restores_both_documents(configuration, tmp_path, monkeypatch):
    repository = ProfileBundleRepository(configuration)
    configuration.guardar_config({"idioma": "es"})
    exported = repository.export(tmp_path / "portable.json")
    configuration.guardar_config({"idioma": "en"})
    original_profiles = configuration.leer_perfiles()
    real_save_profiles = configuration.guardar_perfiles
    calls = 0

    def fail_once(data):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated profile write failure")
        return real_save_profiles(data)

    monkeypatch.setattr(configuration, "guardar_perfiles", fail_once)
    with pytest.raises(OSError, match="simulated"):
        repository.import_bundle(exported)
    assert configuration.leer_config()["idioma"] == "en"
    assert configuration.leer_perfiles() == original_profiles


def test_deep_or_foreign_bundle_fails_closed(configuration, tmp_path):
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"schema":1,"application":"other","sha256":"x"}', encoding="utf-8")
    with pytest.raises(ProfileBundleError, match="schema or application"):
        ProfileBundleRepository(configuration).preview(foreign)


def test_bundle_loader_rejects_symlinks_and_oversized_files(configuration, tmp_path):
    repository = ProfileBundleRepository(configuration)
    bundle = repository.export(tmp_path / "portable.json")
    link = tmp_path / "portable-link.json"
    link.symlink_to(bundle)
    with pytest.raises(ProfileBundleError, match="opened safely"):
        repository.preview(link)

    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as handle:
        handle.truncate(MAX_BUNDLE_BYTES + 1)
    with pytest.raises(ProfileBundleError, match="size limit"):
        repository.preview(oversized)


def test_bundle_loader_rejects_non_finite_json_numbers(configuration, tmp_path):
    repository = ProfileBundleRepository(configuration)
    bundle = repository.export(tmp_path / "portable.json")
    document = json.loads(bundle.read_text(encoding="utf-8"))
    document.pop("sha256")
    document["config"]["gpu_temp_warning"] = float("nan")
    document["sha256"] = _checksum(document)
    bundle.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ProfileBundleError, match="unsupported JSON constant"):
        repository.preview(bundle)


def test_import_reports_incomplete_rollback(configuration, tmp_path, monkeypatch):
    repository = ProfileBundleRepository(configuration)
    bundle = repository.export(tmp_path / "portable.json")

    def always_fail(_data):
        raise OSError("config storage unavailable")

    monkeypatch.setattr(configuration, "guardar_config_completa", always_fail)
    with pytest.raises(ProfileBundleError, match="rollback was incomplete") as captured:
        repository.import_bundle(bundle)
    assert isinstance(captured.value.__cause__, OSError)


def test_import_rejects_symlinked_private_backup_directory(
    configuration, tmp_path
):
    repository = ProfileBundleRepository(configuration)
    bundle = repository.export(tmp_path / "portable.json")
    backup_target = tmp_path / "redirected"
    backup_target.mkdir()
    backup_dir = configuration.config_path().parent / "backups"
    backup_dir.symlink_to(backup_target, target_is_directory=True)

    with pytest.raises(ProfileBundleError, match="cannot be a symbolic link"):
        repository.import_bundle(bundle)
