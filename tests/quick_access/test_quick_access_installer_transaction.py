"""Filesystem-isolated transaction tests for the optional Decky installer."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _write_fake_sudo(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == mktemp && \"${2:-}\" == -d && ( \"${3:-}\" == /var/tmp/bc250-decky-backup.XXXXXX || \"${3:-}\" == /var/tmp/bc250-decky-stage.XXXXXX ) ]]; then\n"
        "  name=\"${3##*/}\"\n"
        "  exec /usr/bin/mktemp -d \"${BC250_QAM_TEST_BACKUP_ROOT}/${name}\"\n"
        "fi\n"
        "if [[ \"${1:-}\" == stat && \"${2:-}\" == -c && \"${3:-}\" == '%u:%a' ]]; then\n"
        "  case \"${4:-}\" in\n"
        "    *.zip|*governor_toml.py) echo '0:644' ;;\n"
        "    *bc250-quick-access-helper|*bc250-cpu-smu-helper|*bc250-governor-config-helper|*homebrew/plugins/bc250-quick-access) echo '0:755' ;;\n"
        "    *) echo \"${BC250_QAM_TEST_PARENT_MODE:-0:755}\" ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _prepare_project(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    plugin = project / "integrations/decky/bc250-quick-access"
    shutil.copytree(
        ROOT / "integrations/decky/bc250-quick-access",
        plugin,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".ruff_cache"),
    )
    helper_source = project / "privileged/helpers/bc250-quick-access-helper"
    helper_source.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "privileged/helpers/bc250-quick-access-helper", helper_source)
    helper_source.chmod(0o755)
    cpu_helper_source = project / "privileged/helpers/bc250-cpu-smu-helper"
    shutil.copy2(ROOT / "privileged/helpers/bc250-cpu-smu-helper", cpu_helper_source)
    cpu_helper_source.chmod(0o755)
    cpu_vendor_source = project / "privileged/lib/bc250_smu_oc_vendor.zip"
    cpu_vendor_source.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "privileged/lib/bc250_smu_oc_vendor.zip", cpu_vendor_source)
    governor_helper_source = project / "privileged/helpers/bc250-governor-config-helper"
    shutil.copy2(ROOT / "privileged/helpers/bc250-governor-config-helper", governor_helper_source)
    governor_helper_source.chmod(0o755)
    governor_editor_source = project / "privileged/lib/governor_toml.py"
    governor_editor_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "privileged/lib/governor_toml.py", governor_editor_source)

    helper_dest = tmp_path / "protected/bc250-quick-access-helper"
    helper_dest.parent.mkdir(parents=True)
    cpu_helper_dest = tmp_path / "protected/bc250-cpu-smu-helper"
    cpu_vendor_dest = tmp_path / "protected/lib/bc250_smu_oc_vendor.zip"
    cpu_vendor_dest.parent.mkdir(parents=True)
    governor_helper_dest = tmp_path / "protected/bc250-governor-config-helper"
    governor_editor_dest = tmp_path / "protected/lib/governor_toml.py"
    shutil.copy2(governor_helper_source, governor_helper_dest)
    shutil.copy2(governor_editor_source, governor_editor_dest)
    source = (ROOT / "scripts/install-decky-quick-access.sh").read_text(encoding="utf-8")
    # The transaction fixture uses a complete temporary protected-helper tree.
    # Do not let the host running pytest (for example Bazzite) select the
    # immutable-host deployment branch for this isolated mutable fixture.
    source = source.replace(
        'if [[ -e /run/ostree-booted ]]; then\n  IMMUTABLE_OSTREE=1\nfi',
        'if false; then\n  IMMUTABLE_OSTREE=1\nfi',
    )
    source = source.replace(
        'HELPER_DEST="/usr/libexec/bc250-control-center/bc250-quick-access-helper"',
        f'HELPER_DEST="{helper_dest}"',
    )
    source = source.replace(
        'CPU_HELPER_DEST="/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"',
        f'CPU_HELPER_DEST="{cpu_helper_dest}"',
    )
    source = source.replace(
        'CPU_VENDOR_DEST="/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip"',
        f'CPU_VENDOR_DEST="{cpu_vendor_dest}"',
    )
    source = source.replace(
        'GOVERNOR_HELPER_DEST="/usr/libexec/bc250-control-center/bc250-governor-config-helper"',
        f'GOVERNOR_HELPER_DEST="{governor_helper_dest}"',
    )
    source = source.replace(
        'GOVERNOR_EDITOR_DEST="/usr/libexec/bc250-control-center/lib/governor_toml.py"',
        f'GOVERNOR_EDITOR_DEST="{governor_editor_dest}"',
    )
    script = project / "scripts/install-decky-quick-access.sh"
    script.write_text(source, encoding="utf-8")
    script.chmod(0o755)

    plugins = tmp_path / "homebrew/plugins"
    plugins.mkdir(parents=True)
    return project, script, helper_source, helper_dest


def _environment(tmp_path: Path, plugins: Path, *, fail_final_move: bool = False) -> dict[str, str]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _write_fake_sudo(binaries / "sudo")
    (binaries / "systemctl").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == is-active && \"${2:-}\" == --quiet && \"${3:-}\" == plugin_loader.service ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == restart && \"${2:-}\" == plugin_loader.service ]]; then\n"
        "  printf '%s\\n' \"$*\" >> \"${BC250_QAM_TEST_SYSTEMCTL_LOG}\"\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected systemctl invocation: $*\" >&2\n"
        "exit 97\n",
        encoding="utf-8",
    )
    (binaries / "systemctl").chmod(0o755)
    if fail_final_move:
        (binaries / "mv").write_text(
            "#!/usr/bin/env bash\n"
            "if [[ \"${1:-}\" == -- ]]; then shift; fi\n"
            "if [[ \"${1:-}\" == *'bc250-decky-stage.'* ]]; then exit 77; fi\n"
            "exec /usr/bin/mv \"$@\"\n",
            encoding="utf-8",
        )
        (binaries / "mv").chmod(0o755)
    return os.environ | {
        "DECKY_PLUGIN_ROOT": str(plugins),
        "BC250_QAM_TEST_BACKUP_ROOT": str(tmp_path),
        "BC250_QAM_TEST_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        "PATH": f"{binaries}:{os.environ['PATH']}",
    }


def _write_existing_plugin(plugins: Path) -> Path:
    existing = plugins / "bc250-quick-access"
    (existing / "dist").mkdir(parents=True)
    (existing / "plugin.json").write_text("old-manifest", encoding="utf-8")
    (existing / "package.json").write_text("old-package", encoding="utf-8")
    (existing / "main.py").write_text("old-backend", encoding="utf-8")
    (existing / "dist/index.js").write_text("old-bundle", encoding="utf-8")
    return existing


def _payload_files(plugin: Path) -> list[str]:
    return sorted(
        path.relative_to(plugin).as_posix()
        for path in plugin.rglob("*")
        if path.is_file()
    )


def test_decky_installer_commits_user_plugin_and_fixed_helper_atomically(tmp_path):
    _project, script, helper_source, helper_dest = _prepare_project(tmp_path)
    plugins = tmp_path / "homebrew/plugins"
    existing = _write_existing_plugin(plugins)
    helper_dest.write_text("old-helper", encoding="utf-8")

    result = subprocess.run(
        ["/usr/bin/bash", str(script)],
        env=_environment(tmp_path, plugins),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (existing / "plugin.json").read_text(encoding="utf-8") != "old-manifest"
    assert (existing / "main.py").is_file()
    assert (existing / "dist/index.js").is_file()
    assert _payload_files(existing) == [
        "bc250cc/__init__.py",
        "bc250cc/domain/__init__.py",
        "bc250cc/domain/gpu/__init__.py",
        "bc250cc/domain/gpu/profiles.py",
        "dist/index.js",
        "main.py",
        "package.json",
        "plugin.json",
    ]
    assert helper_dest.read_bytes() == helper_source.read_bytes()
    assert (tmp_path / "protected/bc250-cpu-smu-helper").read_bytes() == (
        ROOT / "privileged/helpers/bc250-cpu-smu-helper"
    ).read_bytes()
    assert (tmp_path / "protected/lib/bc250_smu_oc_vendor.zip").read_bytes() == (
        ROOT / "privileged/lib/bc250_smu_oc_vendor.zip"
    ).read_bytes()
    assert not list(plugins.glob(".bc250-decky-stage.*"))
    assert not list(plugins.glob(".bc250-decky-backup.*"))
    assert (tmp_path / "systemctl.log").read_text(encoding="utf-8") == "restart plugin_loader.service\n"


def test_decky_installer_removes_only_its_stale_plugin_root_transactions(tmp_path):
    _project, script, _helper_source, _helper_dest = _prepare_project(tmp_path)
    plugins = tmp_path / "homebrew/plugins"
    stale_stage = plugins / ".bc250-decky-stage.previous"
    stale_backup = plugins / ".bc250-decky-backup.previous"
    stale_stage.mkdir()
    stale_backup.mkdir()
    (stale_stage / "plugin.json").write_text("stale", encoding="utf-8")

    result = subprocess.run(
        ["/usr/bin/bash", str(script)],
        env=_environment(tmp_path, plugins),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not stale_stage.exists()
    assert not stale_backup.exists()
    assert "Removing stale BC250 Decky transaction entry" in result.stdout


def test_decky_installer_restores_plugin_and_helper_when_final_plugin_move_fails(tmp_path):
    _project, script, _helper_source, helper_dest = _prepare_project(tmp_path)
    plugins = tmp_path / "homebrew/plugins"
    existing = _write_existing_plugin(plugins)
    helper_dest.write_text("old-helper", encoding="utf-8")
    cpu_helper_dest = tmp_path / "protected/bc250-cpu-smu-helper"
    cpu_vendor_dest = tmp_path / "protected/lib/bc250_smu_oc_vendor.zip"
    cpu_helper_dest.write_text("old-cpu-helper", encoding="utf-8")
    cpu_vendor_dest.write_text("old-cpu-vendor", encoding="utf-8")

    result = subprocess.run(
        ["/usr/bin/bash", str(script)],
        env=_environment(tmp_path, plugins, fail_final_move=True),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 77
    assert (existing / "plugin.json").read_text(encoding="utf-8") == "old-manifest"
    assert (existing / "package.json").read_text(encoding="utf-8") == "old-package"
    assert (existing / "main.py").read_text(encoding="utf-8") == "old-backend"
    assert helper_dest.read_text(encoding="utf-8") == "old-helper"
    assert cpu_helper_dest.read_text(encoding="utf-8") == "old-cpu-helper"
    assert cpu_vendor_dest.read_text(encoding="utf-8") == "old-cpu-vendor"
    assert not list(plugins.glob(".bc250-decky-stage.*"))
    assert not list(plugins.glob(".bc250-decky-backup.*"))


def test_decky_installer_cleans_backups_without_touching_payload_on_preflight_failure(tmp_path):
    _project, script, _helper_source, helper_dest = _prepare_project(tmp_path)
    plugins = tmp_path / "homebrew/plugins"
    existing = _write_existing_plugin(plugins)
    helper_dest.write_text("old-helper", encoding="utf-8")
    environment = _environment(tmp_path, plugins) | {"BC250_QAM_TEST_PARENT_MODE": "0:777"}

    result = subprocess.run(
        ["/usr/bin/bash", str(script)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 8
    assert "protected-helper directory is missing or untrusted" in result.stderr
    assert (existing / "plugin.json").read_text(encoding="utf-8") == "old-manifest"
    assert helper_dest.read_text(encoding="utf-8") == "old-helper"
    assert not list(plugins.glob(".bc250-decky-stage.*"))
    assert not list(plugins.glob(".bc250-decky-backup.*"))
    assert not list(tmp_path.glob("bc250-decky-backup.*"))
