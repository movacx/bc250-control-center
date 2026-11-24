from pathlib import Path

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

ROOT = Path(__file__).resolve().parents[2]


def test_update_script_reuses_checkout_and_preserves_external_state():
    script = (ROOT / "scripts" / "maintenance" / "update-local.sh").read_text(encoding="utf-8")

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
    assert 'APP_COMPONENTS=(src frontends privileged packaging assets scripts integrations requirements-web.txt BUILD_REVISION BUILD_TYPE)' in installer
    assert 'LEGACY_COMPONENTS=(mvc)' in installer
    assert 'cp -a -- "$APP_DIR/$component" "$APP_BACKUP/$component"' in installer
    assert 'install -Dm755 "$ROOT_DIR/scripts/maintenance/update-local.sh"' in installer
    assert 'privileged/policies' in installer
    assert 'packaging/common' in installer
    assert 'packaging/common' in installer
    assert 'packaging/common' in installer
    assert "bc250-privileged-backup" in installer
    assert '"${elevate[@]}" mktemp -d /var/tmp/bc250-privileged-backup.XXXXXX' in installer
    assert "restoring the previous privileged state" in installer
    assert "managed_targets" in installer
    assert '"/etc/cyan-skillfish-governor-smu/config.toml"' in installer


def test_local_installer_matches_modern_debian_ubuntu_runtime_dependencies():
    installer = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")

    # The terminal profile installs the first list; the desktop adds polkit and the Qt packages.
    assert 'apt-get install -y python3 python3-psutil git jq)' in installer
    assert 'missing_python_deps_command+=("$debian_polkit_package" python3-pyqt6 python3-pyqt6.qtsvg libqt6svg6 python3-pip python3-venv openssl ca-certificates)' in installer
    assert 'debian_polkit_package="pkexec"' in installer
    assert 'debian_polkit_package="policykit-1"' in installer
    assert "python-is-python3" not in installer


def test_local_installer_normalizes_privileged_directory_trust_boundary():
    installer = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")

    assert "install -d -m0755 /usr/libexec/bc250-control-center /usr/libexec/bc250-control-center/lib" in installer
    assert "privileged directory must be root-owned mode 0755" in installer


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
            str(ROOT / "scripts" / "maintenance" / "update-local.sh"),
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
            str(ROOT / "scripts" / "maintenance" / "update-local.sh"),
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
            str(ROOT / "scripts" / "maintenance" / "update-local.sh"),
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
    script = (ROOT / "scripts" / "maintenance" / "update-local.sh").read_text(encoding="utf-8")

    assert "detect_package_owner" in script
    assert "rpm -qf" in script
    assert "pacman -Qo" in script
    assert "dpkg-query -S" in script
    assert "refuse_package_managed_update" in script


def test_updater_detects_a_pacman_install_whatever_the_language(tmp_path):
    """SteamOS in Spanish: ``pacman -Qo`` says "está contenido en", not "is owned by".

    The check matched the English sentence, so a package install went
    unnoticed and the Git updater would overwrite package-managed files.
    """
    import os
    import subprocess

    prefix = tmp_path / "usr"
    payload = prefix / "share" / "bc250-control-center" / "frontends" / "desktop" / "main.py"
    payload.parent.mkdir(parents=True)
    payload.write_text("# packaged payload\n", encoding="utf-8")

    fakebin = tmp_path / "fakebin-localized"
    fakebin.mkdir()
    for name in ("rpm", "dpkg-query"):
        tool = fakebin / name
        tool.write_text("#!/bin/sh\necho \"$2: no pertenece a ningún paquete\"; exit 1\n", encoding="utf-8")
        tool.chmod(0o755)
    pacman = fakebin / "pacman"
    pacman.write_text(
        "#!/bin/sh\n"
        "last=\"\"; for arg in \"$@\"; do last=\"$arg\"; done\n"
        "[ \"$last\" = \"$PAYLOAD\" ] || { echo \"error: Ningún paquete contiene $last\" >&2; exit 1; }\n"
        "case \"$1\" in\n"
        "  -Qoq) echo bc250-control-center ;;\n"
        "  -Qo) echo \"$last está contenido en bc250-control-center 1.22.9-3\" ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    pacman.chmod(0o755)

    env = dict(os.environ, PAYLOAD=str(payload), PATH=f"{fakebin}:{os.environ.get('PATH', '')}", LANG="es_MX.UTF-8")
    result = subprocess.run(
        ["/usr/bin/bash", str(ROOT / "scripts" / "maintenance" / "update-local.sh"),
         "--prefix", str(prefix), "--source", str(ROOT)],
        text=True, capture_output=True, env=env, check=False,
    )

    assert result.returncode == 6, result.stderr
    assert "owned by the system package manager (bc250-control-center)" in result.stderr
    assert "through pacman" in result.stderr


def test_local_installer_warns_before_overlaying_a_system_package(tmp_path):
    """pacman -U of a local build owns /usr/libexec; a local install on top mixes versions."""
    import os
    import re
    import subprocess

    installer = (ROOT / "scripts" / "install-local.sh").read_text(encoding="utf-8")
    function = re.search(r"^system_package_owner\(\) \{\n.*?^\}\n", installer, re.M | re.S).group()
    # Inside the helper installer, before the SteamOS unlock and the first helper is replaced.
    helpers = installer[installer.index("install_privileged_pwm_components() {"):]
    assert helpers.index("system_package_owner /usr/libexec") < helpers.index("bc250_steamos_unlock_root")
    assert helpers.index("system_package_owner /usr/libexec") < helpers.index('install -Dm755 "$helper_source"')
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    (fakebin / "pacman").write_text(
        "#!/bin/sh\n"
        "case \"$1\" in -Qoq) [ \"$3\" = /owned ] && { echo bc250-control-center; exit 0; }; exit 1 ;;\n"
        "  -Qo) echo \"$3 está contenido en bc250-control-center 1.22.9-3\" ;; esac\n", encoding="utf-8")
    (fakebin / "pacman").chmod(0o755)
    for name in ("rpm", "dpkg-query"):
        (fakebin / name).write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (fakebin / name).chmod(0o755)
    script = function + 'system_package_owner /owned; echo "rc=$?"; system_package_owner /free; echo "rc=$?"\n'
    result = subprocess.run(["/usr/bin/bash", "-c", script], text=True, capture_output=True,
                            env=dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}"))
    assert result.stdout.splitlines() == ["bc250-control-center", "rc=0", "rc=1"]
    assert "also installed as the system package" in installer
