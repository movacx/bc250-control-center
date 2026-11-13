"""Pure shell builders for reviewed Cyan and Oberon installation workflows."""

from __future__ import annotations

import shlex
import textwrap
from pathlib import Path

from . import container_network


def cyan_upstream_runtime_command(
    os_repository,
    *,
    destination: Path,
    installer: Path,
    checkout_command: str,
    reviewed_release: str,
) -> str:
    if not installer.is_file():
        raise RuntimeError(f"Missing Cyan upstream integration script: {installer}")
    installer_command = (
        f"/usr/bin/bash {shlex.quote(str(installer))} {shlex.quote(str(destination))}"
    )
    # Every supported distribution receives the same reviewed release. A
    # privileged installer must never silently adopt upstream's mutable
    # ``latest`` release during a routine dependency refresh.
    family = str(os_repository.info.family)
    installer_command = (
        f"BC250_CYAN_RELEASE_TAG={shlex.quote(reviewed_release)} "
        f"BC250_CYAN_TARGET_FAMILY={shlex.quote(family)} " + installer_command
    )
    return "; ".join(
        (
            'echo "== Preparing official Cyan SMU frequency-reporting fix =="',
            checkout_command,
            (
                f"test -f {shlex.quote(str(destination / 'src/gpu_frequency_fix.rs'))} || "
                '{ echo "ERROR: the Cyan SMU checkout does not contain the frequency fix"; exit 61; }'
            ),
            installer_command,
            "hash -r",
        )
    )


def cyan_runtime_verification_command() -> str:
    return " ".join(  # noqa: FLY002
        (
            "  bc250_cyan_binary=/usr/local/bin/cyan-skillfish-governor-smu;",
            '  test -x "$bc250_cyan_binary" ||',
            '    { echo "ERROR: Cyan frequency-fix binary is missing"; exit 61; };',
            '  LC_ALL=C grep -aFq "GPU frequency fix enabled" "$bc250_cyan_binary" ||',
            '    { echo "ERROR: installed Cyan binary lacks the frequency-fix capability"; exit 61; };',
            "  bc250_cyan_openrc=0;",
            "  if [ -f /run/openrc/softlevel ] && command -v rc-service >/dev/null 2>&1; then bc250_cyan_openrc=1; fi;",
            (
                '  if [ "$bc250_cyan_openrc" -eq 1 ]; then '
                "bc250_cyan_exec=\"$(grep -E '^[[:space:]]*command=' /etc/init.d/cyan-skillfish-governor-smu 2>/dev/null | head -n 1 | cut -d= -f2- | tr -d '\"')\"; "
                'else bc250_cyan_exec="$(systemctl show cyan-skillfish-governor-smu.service -p ExecStart --value 2>/dev/null || true)"; fi;'
            ),
            '  case "$bc250_cyan_exec" in',
            '    *"$bc250_cyan_binary"*) ;;',
            '    *) echo "ERROR: active init service is not prepared to use the validated Cyan binary"; exit 61 ;;',
            "  esac;",
            "  bc250_cyan_config=/etc/cyan-skillfish-governor-smu/config.toml;",
            '  test -r "$bc250_cyan_config" ||',
            '    { echo "ERROR: Cyan configuration is not readable"; exit 61; };',
            '  grep -Eq "^[[:space:]]*(fix-freq|fix_freq)[[:space:]]*=[[:space:]]*(true|false)([[:space:]]*(#.*)?)?$" "$bc250_cyan_config" ||',
            '    { echo "ERROR: Cyan fix-freq is missing or invalid in config.toml"; exit 61; };',
            '  grep -Eq "^[[:space:]]*fix-metrics[[:space:]]*=[[:space:]]*(true|false)([[:space:]]*(#.*)?)?$" "$bc250_cyan_config" ||',
            '    { echo "ERROR: Cyan fix-metrics is missing or invalid in config.toml"; exit 61; };',
            '  if grep -Eq \'^[[:space:]]*method[[:space:]]*=\' "$bc250_cyan_config" && ! grep -Eq \'^[[:space:]]*method[[:space:]]*=[[:space:]]*"(busy-flag|process|kernel)"([[:space:]]*(#.*)?)?$\' "$bc250_cyan_config"; then',
            '    echo "ERROR: Cyan gpu-usage.method is invalid in config.toml"; exit 61; fi;',
            '  grep -Eq \'^[[:space:]]*set-method[[:space:]]*=[[:space:]]*"(smu|kernel)"([[:space:]]*(#.*)?)?$\' "$bc250_cyan_config" ||',
            '    { echo "ERROR: Cyan gpu.set-method is missing or invalid in config.toml"; exit 61; };',
            textwrap.dedent(r"""
                bc250_cyan_active=0;
                if [ "$bc250_cyan_openrc" -eq 1 ]; then
                    if rc-service cyan-skillfish-governor-smu status >/dev/null 2>&1; then bc250_cyan_active=1; fi;
                else
                    if systemctl is-active --quiet cyan-skillfish-governor-smu.service; then bc250_cyan_active=1; fi;
                fi;
                if [ "$bc250_cyan_active" -eq 1 ]; then
                    bc250_cyan_read_range() {
                        bc250_cyan_read_min="$(busctl --timeout=1s --system get-property com.cyanskillfish.Governor /com/cyanskillfish/Governor/Range/Current com.cyanskillfish.Governor.Range Min 2>/dev/null | awk '$1 == "u" && NF == 2 {print $2}')" || return 1;
                        bc250_cyan_read_max="$(busctl --timeout=1s --system get-property com.cyanskillfish.Governor /com/cyanskillfish/Governor/Range/Current com.cyanskillfish.Governor.Range Max 2>/dev/null | awk '$1 == "u" && NF == 2 {print $2}')" || return 1;
                        [[ "$bc250_cyan_read_min" =~ ^[0-9]+$ && "$bc250_cyan_read_max" =~ ^[0-9]+$ ]] &&
                            [ "$bc250_cyan_read_min" -le "$bc250_cyan_read_max" ];
                    };
                    bc250_cyan_previous_min=;
                    bc250_cyan_previous_max=;
                    if bc250_cyan_read_range; then
                        bc250_cyan_previous_min="$bc250_cyan_read_min";
                        bc250_cyan_previous_max="$bc250_cyan_read_max";
                    else
                        echo "NOTICE: Cyan's previous runtime range is unavailable; continuing with service restart.";
                    fi;
                    bc250_cyan_restart_ok=0;
                    if [ "$bc250_cyan_openrc" -eq 1 ]; then
                        if sudo rc-service cyan-skillfish-governor-smu restart; then bc250_cyan_restart_ok=1; fi;
                    else
                        if sudo systemctl restart cyan-skillfish-governor-smu.service; then bc250_cyan_restart_ok=1; fi;
                    fi;
                    if [ "$bc250_cyan_restart_ok" -ne 1 ]; then
                        echo "ERROR: Cyan service restart failed after configuration repair.";
                        if [ "$bc250_cyan_openrc" -eq 1 ]; then rc-service cyan-skillfish-governor-smu status || true;
                        else systemctl --no-pager --full status cyan-skillfish-governor-smu.service || true; fi;
                        exit 61;
                    fi;
                    bc250_cyan_ready=0;
                    bc250_cyan_deadline=$((SECONDS + 8));
                    for bc250_cyan_attempt in {1..25}; do
                        if [ "$bc250_cyan_openrc" -eq 1 ]; then
                            if rc-service cyan-skillfish-governor-smu status >/dev/null 2>&1; then bc250_cyan_ready=1; fi;
                        else
                            if systemctl is-active --quiet cyan-skillfish-governor-smu.service; then bc250_cyan_ready=1; fi;
                        fi;
                        if [ "$bc250_cyan_ready" -eq 1 ] && bc250_cyan_read_range; then break; fi;
                        bc250_cyan_ready=0;
                        [ "$SECONDS" -lt "$bc250_cyan_deadline" ] || break;
                        sleep 0.2;
                    done;
                    if [ "$bc250_cyan_ready" -ne 1 ]; then
                        echo "ERROR: Cyan D-Bus name is unavailable after restart; check [dbus] enabled = true and the service journal.";
                        if [ "$bc250_cyan_openrc" -eq 1 ]; then rc-service cyan-skillfish-governor-smu status || true;
                        else systemctl --no-pager --full status cyan-skillfish-governor-smu.service || true;
                            journalctl -u cyan-skillfish-governor-smu.service -n 30 --no-pager || true; fi;
                        exit 61;
                    fi;
                    if [ -n "$bc250_cyan_previous_min" ]; then
                        bc250_cyan_restore_ok=0;
                        bc250_cyan_deadline=$((SECONDS + 8));
                        for bc250_cyan_attempt in {1..25}; do
                            if busctl --timeout=1s --system call com.cyanskillfish.Governor /com/cyanskillfish/Governor com.cyanskillfish.Governor.PerformanceMode SetRange uu "$bc250_cyan_previous_min" "$bc250_cyan_previous_max" >/dev/null 2>&1 &&
                                bc250_cyan_read_range &&
                                [ "$bc250_cyan_read_min" = "$bc250_cyan_previous_min" ] &&
                                [ "$bc250_cyan_read_max" = "$bc250_cyan_previous_max" ]; then
                                bc250_cyan_restore_ok=1; break;
                            fi;
                            [ "$SECONDS" -lt "$bc250_cyan_deadline" ] || break;
                            sleep 0.2;
                        done;
                        if [ "$bc250_cyan_restore_ok" -ne 1 ]; then
                            echo "ERROR: Cyan restarted but its previous runtime range could not be restored and verified."; exit 61;
                        fi;
                        echo "OK: restored Cyan runtime range ${bc250_cyan_previous_min}-${bc250_cyan_previous_max} MHz.";
                        echo "OK: Cyan restarted with the selected compatibility switches; runtime range was preserved.";
                    else
                        echo "OK: Cyan restarted with the selected compatibility switches; D-Bus is ready. Using the configured initial range; the previous runtime range was unknown.";
                    fi;
                else
                    echo "OK: Cyan runtime is staged; the selected compatibility switches were preserved.";
                fi
            """).strip(),
        )
    )


def oberon_install_command(
    os_repository,
    *,
    destination: Path,
    checkout_command: str,
    yaml_cpp_revision: str,
) -> str:
    build = destination / "build"
    family = os_repository.info.family
    if family == "fedora":
        dependencies = (
            "sudo dnf install -y git cmake gcc-c++ make libdrm-devel pkgconf-pkg-config"
        )
        dependency_preflight = (
            "pkg-config --exists libdrm libdrm_amdgpu || "
            '{ echo "ERROR: Fedora installed libdrm-devel but its pkg-config metadata is unavailable"; exit 54; }'
        )
        build_command = (
            f"cmake -S {shlex.quote(str(destination))} -B {shlex.quote(str(build))} "
            "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5; "
            f"cmake --build {shlex.quote(str(build))} --parallel"
        )
    elif family in {"debian", "ubuntu"}:
        dependencies = (
            "sudo apt-get update; sudo apt-get install -y "
            "git cmake g++ make libdrm-dev pkg-config ca-certificates"
        )
        dependency_preflight = (
            "pkg-config --exists libdrm libdrm_amdgpu || "
            '{ echo "ERROR: libdrm-dev is installed but its pkg-config metadata is unavailable"; exit 54; }'
        )
        build_command = (
            f"cmake -S {shlex.quote(str(destination))} -B {shlex.quote(str(build))} "
            "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5; "
            f"cmake --build {shlex.quote(str(build))} --parallel"
        )
    elif family in {"arch", "manjaro", "cachyos", "steamos"}:
        dependencies = (
            "sudo pacman -S --needed --noconfirm git cmake base-devel libdrm pkgconf; "
            "if ! pkg-config --exists libdrm libdrm_amdgpu; then "
            'echo "[INFO] Restoring the libdrm development payload omitted by this deployment."; '
            "sudo pacman -S --noconfirm libdrm; fi; "
            # R-bb33f44b: SteamOS images can record linux-api-headers as
            # installed while omitting its files, so --needed skips it and the
            # build dies on <linux/types.h>. Probe the header, not the record.
            "if ! printf '#include <linux/types.h>\\n' | cc -fsyntax-only -x c - >/dev/null 2>&1; then "
            'echo "[INFO] Restoring the kernel API headers omitted by this deployment."; '
            "sudo pacman -S --noconfirm linux-api-headers; fi"
        )
        dependency_preflight = (
            "pkg-config --exists libdrm libdrm_amdgpu || "
            '{ echo "ERROR: libdrm pkg-config metadata is still unavailable after package repair"; exit 54; }; '
            "printf '#include <linux/types.h>\\n' | cc -fsyntax-only -x c - >/dev/null 2>&1 || "
            '{ echo "ERROR: linux/types.h is still missing after reinstalling linux-api-headers"; exit 54; }'
        )
        build_command = (
            f"cmake -S {shlex.quote(str(destination))} -B {shlex.quote(str(build))} "
            "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5; "
            f"cmake --build {shlex.quote(str(build))} --parallel"
        )
    elif family == "alpine":
        dependencies = "sudo apk add --no-cache git cmake build-base libdrm-dev pkgconf ca-certificates"
        dependency_preflight = (
            "pkg-config --exists libdrm libdrm_amdgpu || "
            '{ echo "ERROR: Alpine libdrm-dev metadata is unavailable"; exit 54; }'
        )
        build_command = (
            f"cmake -S {shlex.quote(str(destination))} -B {shlex.quote(str(build))} "
            "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5; "
            f"cmake --build {shlex.quote(str(build))} --parallel"
        )
    elif family == "gentoo":
        dependencies = (
            "sudo emerge --ask=n dev-vcs/git dev-build/cmake sys-devel/gcc "
            "sys-devel/make x11-libs/libdrm virtual/pkgconfig"
        )
        dependency_preflight = (
            "pkg-config --exists libdrm libdrm_amdgpu || "
            '{ echo "ERROR: Gentoo media-libs/libdrm metadata is unavailable"; exit 54; }'
        )
        build_command = (
            f"cmake -S {shlex.quote(str(destination))} -B {shlex.quote(str(build))} "
            "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5; "
            f"cmake --build {shlex.quote(str(build))} --parallel"
        )
    elif family == "bazzite":
        dependencies = (
            "command -v podman >/dev/null 2>&1 || "
            '{ echo "ERROR: podman is required to build Oberon on Bazzite"; exit 52; }'
        )
        mount = shlex.quote(f"{destination}:/source:Z")
        qbuild = shlex.quote(str(build))
        # R-53376560: built in fedora:latest, the binary needed a newer
        # libstdc++ (GLIBCXX_3.4.35) than the fc43 host had. Build in the
        # host's own Fedora release, and start over when that changes.
        build_command = (
            container_network.FUNCTIONS
            + "\n"
            + container_network.setup_lines("podman")[1]
            + "\n"
            + 'bc250_release="$(. /etc/os-release; printf %s "${VERSION_ID:-}")"; '
            'case "$bc250_release" in ""|*[!0-9]*) echo "ERROR: the Fedora release of this Bazzite could not be read"; exit 52;; esac; '
            f'if test "$(cat {qbuild}/.bc250-builder 2>/dev/null)" != "fedora:$bc250_release"; then rm -rf -- {qbuild}; fi; '
            + f"podman run --rm $bc250_net -v {mount} -w /source "
            '"registry.fedoraproject.org/fedora:$bc250_release" bash -lc '
            + shlex.quote(
                "dnf install -y git cmake gcc-c++ make libdrm-devel pkgconf-pkg-config && "
                "cmake -S . -B build -DCMAKE_BUILD_TYPE=Release "
                "-DCMAKE_POLICY_VERSION_MINIMUM=3.5 && "
                "cmake --build build --parallel"
            )
            + f'; printf %s "fedora:$bc250_release" > {qbuild}/.bc250-builder'
        )
        # Dependencies live inside the disposable Fedora build container.
        dependency_preflight = ":"
    else:
        raise RuntimeError(
            f"{os_repository.info.label} has no validated Oberon build strategy."
        )

    binary = build / "oberon-governor"
    config = build / "oberon-config.yaml"
    cmake = shlex.quote(str(destination / "CMakeLists.txt"))
    # The reviewed yaml-cpp commit predates current GCC headers and refers to
    # uint16_t without including <cstdint>.  Patch only the generated build
    # dependency after CMake fetches/configures it; the upstream checkout and
    # the project source remain immutable and the patch is reproducible.
    yaml_cpp_emitter = build / "_deps/yaml-cpp-src/src/emitterutils.cpp"
    # Bazzite builds inside a container where the checkout is mounted at
    # /source; all other strategies run directly against the host path.
    yaml_cpp_emitter_shell = (
        "build/_deps/yaml-cpp-src/src/emitterutils.cpp"
        if family == "bazzite"
        else str(yaml_cpp_emitter)
    )
    yaml_cpp_patch = (
        f"yaml_cpp_emitter={shlex.quote(yaml_cpp_emitter_shell)}; "
        'test -f "$yaml_cpp_emitter" || '
        '{ echo "ERROR: CMake did not fetch the reviewed yaml-cpp source"; exit 53; }; '
        'if ! grep -Fqx "#include <cstdint>" "$yaml_cpp_emitter"; then '
        'sed -i "1i#include <cstdint>" "$yaml_cpp_emitter"; '
        'fi; '
        'grep -Fqx "#include <cstdint>" "$yaml_cpp_emitter" || '
        '{ echo "ERROR: yaml-cpp GCC compatibility patch could not be applied"; exit 53; }'
    )
    build_command = build_command.replace(
        "cmake --build",
        f"{yaml_cpp_patch}; cmake --build",
        1,
    )
    return "; ".join(
        (
            "set -Eeuo pipefail",
            "export LC_ALL=C LANG=C",
            dependencies,
            dependency_preflight,
            'command -v git >/dev/null 2>&1 || { echo "ERROR: git is required for Oberon"; exit 29; }',
            'echo "== Preparing official Oberon Governor source =="',
            checkout_command,
            (
                f'grep -Fq "GIT_TAG master" {cmake} || '
                '{ echo "ERROR: reviewed Oberon yaml-cpp declaration changed"; exit 53; }'
            ),
            f'sed -i "s/GIT_TAG master/GIT_TAG {yaml_cpp_revision}/" {cmake}',
            (
                f'grep -Fq "GIT_TAG {yaml_cpp_revision}" {cmake} || '
                '{ echo "ERROR: yaml-cpp dependency was not pinned"; exit 53; }'
            ),
            build_command,
            f'test -x {shlex.quote(str(binary))} || {{ echo "ERROR: Oberon build did not produce a binary"; exit 53; }}',
            # The host must load what was built before it replaces the binary in use.
            (
                f'if ldd {shlex.quote(str(binary))} 2>&1 | grep -q "not found"; then '
                f'ldd {shlex.quote(str(binary))} 2>&1 | grep "not found" | sed "s/^/ERROR: /"; '
                'echo "ERROR: the new Oberon binary needs libraries this system does not have; the installed one was kept"; '
                "exit 53; fi"
            ),
            "sudo install -d -m 0755 /usr/local/bin",
            f"sudo install -m 0755 {shlex.quote(str(binary))} /usr/local/bin/oberon-governor",
            f"test -e /etc/oberon-config.yaml || sudo install -m 0644 {shlex.quote(str(config))} /etc/oberon-config.yaml",
            # The service is installed lazily by the active init adapter when the
            # user enables it from the GPU page.  Do not write a systemd unit on an
            # OpenRC host merely because the binary was built successfully.
            (
                "if [ -f /run/openrc/softlevel ] && command -v rc-service >/dev/null 2>&1; then "
                'echo "OK: Oberon Governor installed for OpenRC; enable it from GPU control."; '
                "else "
                f"sudo install -d -m 0755 /etc/systemd/system; "
                f"sed 's#/usr/bin/oberon-governor#/usr/local/bin/oberon-governor#' {shlex.quote(str(build / 'oberon-governor.service'))} | sudo tee /etc/systemd/system/oberon-governor.service >/dev/null; "
                "sudo chmod 0644 /etc/systemd/system/oberon-governor.service; "
                "sudo systemctl daemon-reload; "
                'echo "OK: Oberon Governor installed; existing /etc/oberon-config.yaml was preserved."; '
                "fi"
            ),
        )
    )
