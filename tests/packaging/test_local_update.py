from pathlib import Path

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

ROOT = Path(__file__).resolve().parents[2]


def test_update_script_reuses_checkout_and_preserves_external_state():
    script = (ROOT / "scripts" / "update-local.sh").read_text(encoding="utf-8")

    assert "git -C \"$UPDATE_SOURCE\" pull --ff-only" in script
    assert "status --porcelain" in script
    assert "unexpected origin" in script
    assert "ResourceTools are preserved" in script
    assert 'source/frontends/desktop' in script
    assert 'source/packaging/common' in script
    assert "uninstall-local.sh" not in script
    assert "rm -rf \"$UPDATE_SOURCE\"" not in script


def test_local_installer_stages_and_rolls_back_application_code():
    installer = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")

    assert "python3 -m compileall" in installer
    assert "APP_BACKUP" in installer
    assert "rolling back the application code" in installer
    assert 'APP_COMPONENTS=(src frontends privileged packaging assets)' in installer
    assert 'install -Dm755 "$ROOT_DIR/scripts/update-local.sh"' in installer
    assert 'privileged/policies' in installer
    assert 'packaging/common' in installer
    assert 'packaging/common' in installer
    assert 'packaging/common' in installer
    assert "bc250-privileged-backup" in installer
    assert '"${elevate[@]}" mktemp -d /var/tmp/bc250-privileged-backup.XXXXXX' in installer
    assert "restoring the previous privileged state" in installer
    assert "managed_targets" in installer
    assert '"/etc/cyan-skillfish-governor-smu/config.toml"' in installer


def test_repository_launches_updater_as_an_argv_safe_shell_path(monkeypatch, tmp_path):
    updater = tmp_path / "update-local.sh"
    updater.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    captured = []
    repository = DependenciasRepository()
    monkeypatch.setattr(repository, "_local_updater_path", lambda: updater)
    monkeypatch.setattr(
        repository,
        "_abrir_terminal",
        lambda command, title: captured.append((command, title)) or True,
    )

    assert repository.actualizar_aplicacion_local() is True
    assert captured == [(f"/usr/bin/bash {updater}", "Actualizar BC250 Control Center")]


def test_updater_refuses_to_overwrite_rpm_ostree_owned_install(tmp_path):
    import os
    import subprocess

    prefix = tmp_path / "usr"
    launcher = prefix / "bin" / "bc250-control-center"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    rpm = fakebin / "rpm"
    rpm.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -qf ]; then echo bc250-control-center-1.19.0-1; exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    rpm.chmod(0o755)
    ostree = fakebin / "rpm-ostree"
    ostree.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ostree.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
    result = subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "update-local.sh"),
            "--prefix",
            str(prefix),
            "--source",
            str(ROOT),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 6
    assert "owned by the system package manager" in result.stderr
    assert "rpm-ostree install ./bc250-control-center-NEW_VERSION.rpm" in result.stderr
    assert "systemctl reboot" in result.stderr


def test_updater_refuses_when_payload_is_package_owned_even_if_launcher_is_missing(tmp_path):
    import os
    import subprocess

    prefix = tmp_path / "usr"
    payload = prefix / "share" / "bc250-control-center" / "frontends" / "desktop" / "main.py"
    payload.parent.mkdir(parents=True)
    payload.write_text("# packaged payload\n", encoding="utf-8")

    fakebin = tmp_path / "fakebin-payload"
    fakebin.mkdir()
    rpm = fakebin / "rpm"
    rpm.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -qf ] && [ \"$2\" = \"$PAYLOAD\" ]; then "
        "echo bc250-control-center-1.19.0-1; exit 0; fi\n"
        "echo \"$2 is not owned by any package\"; exit 1\n",
        encoding="utf-8",
    )
    rpm.chmod(0o755)

    env = dict(os.environ)
    env["PAYLOAD"] = str(payload)
    env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
    result = subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "update-local.sh"),
            "--prefix",
            str(prefix),
            "--source",
            str(ROOT),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 6
    assert "owned by the system package manager" in result.stderr



def test_updater_refuses_when_package_owned_sentinel_was_manually_deleted(tmp_path):
    import os
    import subprocess

    prefix = tmp_path / "usr"
    missing_payload = prefix / "share" / "bc250-control-center" / "frontends" / "desktop" / "main.py"

    fakebin = tmp_path / "fakebin-deleted"
    fakebin.mkdir()
    rpm = fakebin / "rpm"
    rpm.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -qf ] && [ \"$2\" = \"$PAYLOAD\" ]; then "
        "echo bc250-control-center-1.19.0-1; exit 0; fi\n"
        "echo \"$2 is not owned by any package\"; exit 1\n",
        encoding="utf-8",
    )
    rpm.chmod(0o755)

    env = dict(os.environ)
    env["PAYLOAD"] = str(missing_payload)
    env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
    result = subprocess.run(
        [
            "/usr/bin/bash",
            str(ROOT / "scripts" / "update-local.sh"),
            "--prefix",
            str(prefix),
            "--source",
            str(ROOT),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 6
    assert "owned by the system package manager" in result.stderr

def test_updater_documents_package_manager_guard():
    script = (ROOT / "scripts" / "update-local.sh").read_text(encoding="utf-8")

    assert "detect_package_owner" in script
    assert "rpm -qf" in script
    assert "pacman -Qo" in script
    assert "dpkg-query -S" in script
    assert "refuse_package_managed_update" in script
