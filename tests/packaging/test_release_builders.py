import os
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _run(*argv, env=None):
    completed = subprocess.run(
        [str(item) for item in argv],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed


def test_release_builder_shell_is_valid():
    builders = sorted((ROOT / "packaging").rglob("*.sh"))

    assert builders
    _run("bash", "-n", *builders)


def test_package_license_metadata_matches_project_license():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    appstream = (ROOT / "packaging/common/io.github.movacx.bc250-control-center.metainfo.xml").read_text(encoding="utf-8")
    arch_builder = (ROOT / "packaging/scripts/build-local-pkg.sh").read_text(encoding="utf-8")
    rpm_builder = (ROOT / "packaging/scripts/build-rpm.sh").read_text(encoding="utf-8")
    deb_builder = (ROOT / "packaging/scripts/build-deb.sh").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License\n")
    assert "<project_license>MIT</project_license>" in appstream
    assert "license = MIT" in arch_builder
    assert "License:        MIT" in rpm_builder
    assert "python3-pyqt6" in rpm_builder
    assert "python3-qt6" not in rpm_builder
    assert "_buildhost bc250-control-center.invalid" in rpm_builder
    assert "use_source_date_epoch_as_buildtime 1" in rpm_builder
    assert "Architecture: all" in deb_builder
    assert "bc250-package-maintenance post-install" in deb_builder
    assert f'<release version="{VERSION}"' in appstream


def test_package_post_install_repairs_legacy_privileged_directory_modes():
    deb_builder = (ROOT / "packaging/scripts/build-deb.sh").read_text(encoding="utf-8")
    maintenance = (ROOT / "packaging/common/bc250-package-maintenance").read_text(encoding="utf-8")

    assert "install -d -o 0 -g 0 -m 0755" in deb_builder
    assert "/usr/libexec/bc250-control-center/lib" in deb_builder
    assert "old 0775 directory" in deb_builder
    assert "install -d -o 0 -g 0 -m0755" not in maintenance


def test_package_staging_contains_runtime_and_no_generated_or_retired_code(tmp_path):
    stage = tmp_path / "root"

    _run("bash", ROOT / "packaging/scripts/stage-package-root.sh", stage)

    assert (stage / "usr/bin/bc250-control-center-cli").stat().st_mode & 0o111
    assert (stage / "usr/libexec/bc250-control-center/bc250-cpu-smu-helper").stat().st_mode & 0o111
    assert (stage / "usr/libexec/bc250-control-center/bc250-service-helper").stat().st_mode & 0o111
    assert (stage / "usr/libexec/bc250-control-center/bc250-maintenance-helper").stat().st_mode & 0o111
    assert (stage / "usr/libexec/bc250-control-center/bc250-package-maintenance").stat().st_mode & 0o111
    privileged_root = stage / "usr/libexec/bc250-control-center"
    privileged_lib = privileged_root / "lib"
    assert privileged_root.stat().st_mode & 0o022 == 0
    assert privileged_lib.stat().st_mode & 0o022 == 0
    assert (stage / "usr/share/polkit-1/actions/io.github.movacx.bc250-control-center.policy").is_file()
    assert (stage / "usr/share/bc250-control-center/VERSION").read_text(encoding="utf-8").strip() == VERSION
    assert (stage / "usr/share/bc250-control-center/src/bc250cc/__init__.py").is_file()
    assert (stage / "usr/share/bc250-control-center/frontends/desktop/features/gpu/presenter.py").is_file()
    assert (stage / "usr/share/bc250-control-center/privileged/helpers/README.md").is_file()
    assert not (stage / "usr/share/bc250-control-center/src/src").exists()
    assert not (stage / "usr/share/bc250-control-center/src/bc250cc/infrastructure/core_unlock.py").exists()
    assert not list(stage.rglob("__pycache__"))
    assert not list(stage.rglob("*.pyc"))


def test_deb_dependencies_support_split_and_legacy_polkit_packages(tmp_path):
    if shutil.which("dpkg-deb") is None:
        return
    output = tmp_path / "dist"

    _run("bash", ROOT / "packaging/scripts/build-deb.sh", output)
    package = output / f"bc250-control-center_{VERSION}-1_all.deb"
    depends = _run("dpkg-deb", "--field", package, "Depends").stdout.strip()

    assert "python3-pyqt6" in depends
    assert "libqt6svg6" in depends
    assert "pkexec | policykit-1" in depends


def test_source_tarball_is_reproducible_and_excludes_qa_payload(tmp_path):
    environment = dict(os.environ, SOURCE_DATE_EPOCH="1786579200")
    output = tmp_path / "dist"

    _run("bash", ROOT / "packaging/scripts/build-tarball.sh", output, env=environment)
    archive = output / f"bc250-control-center-{VERSION}.tar.gz"
    first = archive.read_bytes()
    _run("bash", ROOT / "packaging/scripts/build-tarball.sh", output, env=environment)

    assert archive.read_bytes() == first
    with tarfile.open(archive, "r:gz") as bundle:
        names = bundle.getnames()
    assert any(name.endswith("/scripts/install-local.sh") for name in names)
    assert any(name.endswith("/VERSION") for name in names)
    assert any(name.endswith("/packaging/scripts/build-rpm.sh") for name in names)
    assert any(name.endswith("/packaging/scripts/build-deb.sh") for name in names)
    assert any(name.endswith("/src/bc250cc/__init__.py") for name in names)
    assert any(name.endswith("/frontends/desktop/features/gpu/presenter.py") for name in names)
    assert any(name.endswith("/privileged/helpers/README.md") for name in names)
    assert not any("/tests/" in name or "/archive/" in name for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_arch_package_has_canonical_metadata_and_is_accepted_by_pacman(tmp_path):
    if shutil.which("zstd") is None or shutil.which("pacman") is None:
        return

    output = tmp_path / "dist"
    _run("bash", ROOT / "packaging/scripts/build-local-pkg.sh", output)
    package = output / f"bc250-control-center-{VERSION}-1-any.pkg.tar.zst"

    query = _run("pacman", "-Qip", package).stdout
    assert "Name            : bc250-control-center" in query
    assert f"Version         : {VERSION}-1" in query

    archive_names = _run("bsdtar", "-tf", package).stdout.splitlines()
    assert ".PKGINFO" in archive_names
    assert "./.PKGINFO" not in archive_names


def test_release_builder_rejects_a_conflicting_version_override(tmp_path):
    environment = dict(os.environ, BC250_VERSION="999.0.0")
    completed = subprocess.run(
        ["bash", str(ROOT / "packaging/scripts/build-tarball.sh"), str(tmp_path)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 64
    assert f"must match the release VERSION file ({VERSION})" in completed.stderr
