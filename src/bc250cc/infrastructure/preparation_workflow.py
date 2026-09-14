"""Cross-distribution BC250 preparation command orchestration.

This module only assembles shell text from reviewed repository adapters. It
does not execute commands, open terminals, elevate privileges or touch hardware.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from bc250cc.application.preparation.component_engine import (
    preparation_plan,
    verification_shell,
)
from bc250cc.infrastructure import script_presentation
from bc250cc.infrastructure.governor_conflicts import (
    CYAN_GOVERNOR,
    GOVERNOR_SPECS,
    OBERON_GOVERNOR,
)
from bc250cc.infrastructure.steamos_shell import wrap_steamos_writable_command

BAZZITE_REBOOT_NOTICE_LINES = (
    "==========================================================================",
    "= REBOOT REQUIRED / REINICIO REQUERIDO / ТРЕБУЕТСЯ ПЕРЕЗАГРУЗКА",
    "=",
    "= EN: Restart the computer once to activate the new Bazzite deployment.",
    "=     After reboot, run ONLY 'NCT sensors and PWM' to finish setup.",
    "=",
    "= ES: Reinicia la computadora una vez para activar el nuevo deployment de Bazzite.",
    "=     Después del reinicio, ejecuta ÚNICAMENTE 'NCT sensors and PWM' para finalizar.",
    "=",
    "= RU: Перезагрузите компьютер один раз, чтобы активировать новое развёртывание Bazzite.",
    "=     После перезагрузки запустите ТОЛЬКО 'NCT sensors and PWM', чтобы завершить настройку.",
    "==========================================================================",
)


@dataclass(frozen=True)
class PreparationContext:
    repository: object
    os_repository: object
    selected_components: frozenset[str]
    selected_governor: str
    conflicts: tuple[dict, ...]
    disable_conflicts: bool
    include_pwm: bool
    paths: dict[str, str]
    tool_dir: Path
    cpu_destination: Path
    core_repository: str
    core_destination: Path
    core_script: Path
    cu_spec: dict
    prepare_cu_backend: str
    cpu_repository: str
    cpu_reviewed_revision: str
    cyan_directory: str
    steamos_fix_directory: str
    gddr6_repository: str = ''
    gddr6_destination: Path | None = None


def secure_cpu_checkout_command(destination: Path) -> str:
    qdestination = shlex.quote(str(destination))
    return (
        f'chmod u+rwx,go+rx,go-w {qdestination}; '
        f'if [ -d {qdestination}/.git ]; then '
        'while IFS= read -r -d "" bc250_cpu_file; do '
        f'  bc250_cpu_path={qdestination}/$bc250_cpu_file; '
        '  [ -e "$bc250_cpu_path" ] || continue; '
        '  [ ! -L "$bc250_cpu_path" ] || '
        '  { echo "ERROR: reviewed bc250_smu_oc file is a symbolic link: $bc250_cpu_file"; exit 30; }; '
        '  [ -O "$bc250_cpu_path" ] || '
        '  { echo "ERROR: reviewed bc250_smu_oc file is not owned by the desktop user: $bc250_cpu_file"; exit 30; }; '
        '  chmod u+rwX,go+rX,go-w "$bc250_cpu_path"; '
        f'done < <(git -C {qdestination} ls-files -z); '
        'else '
        f'find {qdestination} -xdev -user "$(id -u)" '
        '-exec chmod u+rwX,go+rX,go-w {} +; '
        'fi'
    )


def _immutable_commands(context: PreparationContext) -> list[str]:
    repo = context.repository
    os_repo = context.os_repository
    selected = context.selected_components
    cu_spec = context.cu_spec
    cu_destination = cu_spec['destination']
    cu_upstream_script = cu_spec['upstream_script']
    cu_script = cu_spec['script']
    commands = ['echo "== Preparing selected BC250 tools before the rpm-ostree reboot =="']
    if 'cpu_oc' in selected:
        commands.extend([
            repo._clone_or_update_commit_with_archive_command(
                context.cpu_repository,
                context.cpu_destination,
                context.cpu_reviewed_revision,
            ),
            secure_cpu_checkout_command(context.cpu_destination),
            f'test -f {shlex.quote(str(context.cpu_destination / "bc250_detect.py"))} || '
            '{ echo "ERROR: bc250_detect.py is missing"; exit 30; }',
        ])
    if 'core_unlock' in selected:
        commands.extend([
            'command -v git >/dev/null 2>&1 || { echo "ERROR: git is required to clone bc250-core-unlock"; exit 29; }',
            'echo "== Preparing official bc250-core-unlock source =="',
            repo._hardware_source_checkout_command(
                context.core_repository, context.core_destination, os_repo
            ),
            f'test -f {shlex.quote(str(context.core_script))} || '
            '{ echo "ERROR: bc250-unlock-cores.py is missing"; exit 36; }',
            f'chmod 0755 {shlex.quote(str(context.core_script))}',
        ])
    if 'cu_manager' in selected or 'umr' in selected:
        commands.extend([
            repo._clone_or_update_commit_with_archive_command(
                cu_spec['repository'], cu_destination, cu_spec['reviewed_commit']
            ),
            f'test -x {shlex.quote(str(cu_upstream_script))} || '
            '{ echo "ERROR: upstream 40CU manager script is missing"; exit 31; }',
            *([context.prepare_cu_backend] if context.prepare_cu_backend else []),
            f'chmod 0755 {shlex.quote(str(cu_script))}',
            f'test -x {shlex.quote(str(cu_script))} || '
            '{ echo "ERROR: 40CU runtime backend is missing"; exit 31; }',
        ])
        if not context.prepare_cu_backend:
            # Both the CU-manager and standalone UMR routes advertise a
            # usable Compute Units preparation. Immutable generic systems
            # therefore promote the reviewed manager in either case.
            commands.append(repo._generic_cu_privileged_backend_stage_command(cu_script))
    commands.append(repo._accept_reboot_required(
        os_repo.prepare_dependencies_command(
            'runtime', cu_manager_script=str(cu_script)
        ),
        'The Bazzite deployment was staged successfully. Reboot once to activate the host packages.',
    ))
    if 'umr' in selected:
        # Immutable preparation does not pass through _mutable_umr_commands.
        # Layer UMR explicitly, otherwise a Bazzite clean install prepares the
        # CU checkout but never installs the ``umr`` executable it requires.
        commands.append(repo._accept_reboot_required(
            os_repo.install_umr_command(str(cu_script)),
            'UMR was staged in the Bazzite deployment. Reboot once to activate it.',
        ))
    if 'governor' in selected:
        if context.selected_governor == OBERON_GOVERNOR:
            commands.append(repo._oberon_install_command(os_repo))
        else:
            commands.append(repo._accept_reboot_required(
                os_repo.prepare_dependencies_command('governor'),
                'The Cyan governor was staged for the next Bazzite deployment.',
            ))
    return commands


def _mutable_commands(context: PreparationContext) -> list[str]:
    os_repo = context.os_repository
    selected = context.selected_components
    commands = [
        os_repo.prepare_dependencies_command('runtime'),
        'command -v git >/dev/null 2>&1 || '
        '{ echo "ERROR: git is unavailable after dependency preparation"; exit 29; }',
    ]
    commands.extend(_mutable_governor_commands(context))
    commands.extend(_mutable_source_commands(context))
    commands.extend(_mutable_umr_commands(context))
    commands.extend(_steamos_user_space_commands(context))
    selected_binary = str(GOVERNOR_SPECS[context.selected_governor]['binary'])
    if context.selected_governor != CYAN_GOVERNOR and 'governor' in selected:
        commands.append(
            f'command -v {shlex.quote(selected_binary)} >/dev/null 2>&1 || '
            f'{{ echo "ERROR: {selected_binary} is unavailable after governor installation"; exit 33; }}'
        )
    return commands


def _mutable_governor_commands(context: PreparationContext) -> list[str]:
    if 'governor' not in context.selected_components:
        return []
    repo = context.repository
    os_repo = context.os_repository
    command = (
        wrap_steamos_writable_command(
            repo._oberon_install_command(os_repo), family=os_repo.info.family
        )
        if context.selected_governor == OBERON_GOVERNOR
        else os_repo.prepare_dependencies_command('governor')
    )
    commands = [command]
    if context.selected_governor == CYAN_GOVERNOR:
        commands.extend([
            repo._cyan_upstream_runtime_command(os_repo),
            repo._cyan_runtime_verification_command(),
        ])
    return commands


def _mutable_source_commands(context: PreparationContext) -> list[str]:
    repo = context.repository
    os_repo = context.os_repository
    selected = context.selected_components
    cu_spec = context.cu_spec
    cu_destination = cu_spec['destination']
    cu_upstream_script = cu_spec['upstream_script']
    cu_script = cu_spec['script']
    commands = []
    if 'cpu_oc' in selected:
        commands.extend([
            'echo "== Preparing bc250_smu_oc source =="',
            repo._hardware_source_checkout_command(
                context.cpu_repository, context.cpu_destination, os_repo
            ),
            # Runtime detector artifacts are untracked and may have been
            # created by an older privileged workflow. Secure the reviewed
            # Git files without trying to chmod those unrelated artifacts.
            secure_cpu_checkout_command(context.cpu_destination),
            f'test -f {shlex.quote(str(context.cpu_destination / "bc250_detect.py"))} || '
            '{ echo "ERROR: bc250_detect.py is missing"; exit 30; }',
        ])
    if 'core_unlock' in selected:
        commands.extend([
            'echo "== Preparing official bc250-core-unlock source =="',
            repo._hardware_source_checkout_command(
                context.core_repository, context.core_destination, os_repo
            ),
            f'test -d {shlex.quote(str(context.core_destination / ".git"))} || '
            '{ echo "ERROR: bc250-core-unlock is not a Git clone"; exit 36; }',
            f'test -f {shlex.quote(str(context.core_script))} || '
            '{ echo "ERROR: bc250-unlock-cores.py is missing"; exit 36; }',
            f'chmod 0755 {shlex.quote(str(context.core_script))}',
        ])
    if 'gddr6_temp' in selected and context.gddr6_destination is not None:
        commands.extend([
            'echo "== Preparing reviewed GDDR6 memory-temperature source =="',
            repo._hardware_source_checkout_command(
                context.gddr6_repository, context.gddr6_destination, os_repo
            ),
            f'test -d {shlex.quote(str(context.gddr6_destination / ".git"))} || '
            '{ echo "ERROR: bc250-memory-temperature is not a Git clone"; exit 37; }',
            # The privileged reader imports this package directly, and refuses
            # it unless every file belongs to the desktop user.
            f'test -d {shlex.quote(str(context.gddr6_destination / "bc250_smu"))} || '
            '{ echo "ERROR: the reviewed bc250_smu package is missing"; exit 37; }',
            f'test -f {shlex.quote(str(context.gddr6_destination / "SMUPayload.bin"))} || '
            '{ echo "ERROR: SMUPayload.bin is missing"; exit 37; }',
        ])
    if 'cu_manager' in selected:
        commands.extend([
            'echo "== Preparing 40CU live manager =="',
            repo._hardware_source_checkout_command(
                cu_spec['repository'], cu_destination, os_repo
            ),
            f'test -x {shlex.quote(str(cu_upstream_script))} || '
            '{ echo "ERROR: upstream 40CU manager script is missing"; exit 31; }',
            *([context.prepare_cu_backend] if context.prepare_cu_backend else []),
            f'chmod 0755 {shlex.quote(str(cu_script))}',
            f'test -x {shlex.quote(str(cu_script))} || '
            '{ echo "ERROR: 40CU runtime backend is missing"; exit 31; }',
        ])
        if not context.prepare_cu_backend:
            # Generic systemd and OpenRC integrations both execute only the
            # reviewed root-owned manager, never the mutable checkout above.
            commands.append(repo._generic_cu_privileged_backend_stage_command(cu_script))
    return commands


def _mutable_umr_commands(context: PreparationContext) -> list[str]:
    if 'umr' not in context.selected_components:
        return []
    repo = context.repository
    os_repo = context.os_repository
    selected = context.selected_components
    cu_spec = context.cu_spec
    cu_destination = cu_spec['destination']
    cu_script = cu_spec['script']
    commands = []
    if 'umr' in selected:
        if 'cu_manager' not in selected:
            commands.extend([
                'echo "== Preparing 40CU backend required for UMR validation =="',
                repo._hardware_source_checkout_command(
                    cu_spec['repository'], cu_destination, os_repo
                ),
                *([context.prepare_cu_backend] if context.prepare_cu_backend else []),
            ])
        commands.extend([
            os_repo.install_umr_command(str(cu_script)),
            'command -v umr >/dev/null 2>&1 || '
            '{ echo "ERROR: UMR is still unavailable"; exit 32; }',
        ])
        if 'cu_manager' not in selected and os_repo.info.family != 'steamos':
            # The standalone UMR action is exposed from the Compute Units
            # page.  On a clean generic installation it must leave that page
            # usable, not merely install the register utility while keeping
            # the reviewed manager in the user's writable checkout.
            commands.append(
                repo._generic_cu_privileged_backend_stage_command(cu_script)
            )
    return commands


def _steamos_user_space_commands(context: PreparationContext) -> list[str]:
    if context.os_repository.info.family != 'steamos':
        return []
    repo = context.repository
    selected = context.selected_components
    cu_script = context.cu_spec['script']
    commands = []
    if 'umr' in selected:
        commands.append(repo._steamos_umr_database_repair_command())
    if 'cu_manager' in selected:
        # Staging writes to /usr/libexec on SteamOS. Keep this operation inside
        # the same guarded writable-root window as the other privileged steps;
        # otherwise SteamOS remounts /usr read-only between components.
        commands.append(wrap_steamos_writable_command(
            repo._steamos_cu_privileged_backend_stage_command(cu_script),
            family='steamos',
        ))
        commands.append(wrap_steamos_writable_command(
            repo._steamos_cu_service_backend_update_command(cu_script),
            family='steamos',
        ))
    if {'umr', 'cu_manager'} <= selected:
        commands.append(repo._steamos_cu_status_probe_command(cu_script))
    return commands


def build_preparation_command(context: PreparationContext) -> str:
    repo = context.repository
    os_repo = context.os_repository
    selected = context.selected_components
    cu_script = context.cu_spec['script']
    commands = [
        'set -Eeuo pipefail',
        'export LC_ALL=C LANG=C',
        'if command -v flock >/dev/null 2>&1; then exec 9>"${XDG_RUNTIME_DIR:-/tmp}/bc250-control-center-$(id -u).lock"; flock -n 9 || { echo "ERROR: another BC250 system preparation is already running"; exit 40; }; fi',
        'BC250_REBOOT_REQUIRED=0',
        f'mkdir -p {shlex.quote(str(context.tool_dir))}',
        # A framed header with the detected system and the plan, so the user
        # can see what is about to happen instead of watching raw tool output
        # scroll past with no context.
        script_presentation.banner(
            'BC-250 Control Center - Prepare dependencies',
            f'{os_repo.info.label} - {os_repo.info.family}',
        ),
        script_presentation.note(
            'Components: ' + ', '.join(sorted(selected))
        ),
        script_presentation.note(
            'Plan: ' + ', '.join(
                item['component']
                for item in preparation_plan(selected, os_repo.info.family)
            )
        ),
        script_presentation.progress_note(
            'Downloads and builds can take several minutes; this is normal.'
        ),
    ]
    if context.disable_conflicts and context.conflicts:
        commands.append(repo._comando_desactivar_gobernadores_incompatibles(
            context.conflicts
        ))
    if 'cpu_oc' in selected:
        stress = os_repo.prepare_dependencies_command('stress')
        commands.append(
            repo._accept_reboot_required(
                stress,
                'The CPU stress dependency is staged for the next deployment.',
            )
            if os_repo.info.family == 'bazzite'
            else stress
        )
    commands.extend(
        _immutable_commands(context)
        if os_repo.info.family == 'bazzite'
        else _mutable_commands(context)
    )
    if (
        os_repo.info.family == 'bazzite'
        and context.selected_governor == CYAN_GOVERNOR
        and 'governor' in selected
    ):
        commands.append(repo._cyan_upstream_runtime_command(os_repo))
        binary = str(GOVERNOR_SPECS[context.selected_governor]['binary'])
        managed = f'/usr/local/bin/{binary}'
        commands.append(
            f'test -x {shlex.quote(managed)} || '
            f'{{ echo "ERROR: {managed} is unavailable after the verified Cyan runtime installation"; exit 33; }}'
        )
        commands.append(repo._cyan_runtime_verification_command())
    if context.include_pwm:
        pwm_builder = getattr(repo, '_comando_preparar_nct6687_control_pwm', None)
        if not callable(pwm_builder):
            raise RuntimeError(
                'The integrated nct6687 preparation workflow is unavailable.'
            )
        pwm_command = wrap_steamos_writable_command(
            pwm_builder(), family=os_repo.info.family
        )
        if os_repo.info.family == 'bazzite':
            # dkms and its compiler toolchain are layered into the deployment
            # above.  They do not exist in the currently booted deployment, so
            # a clean Bazzite installation must not try to build a module until
            # the required one-time reboot has activated them.
            commands.append(
                'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then '
                'echo "PENDING: fan PWM preparation will run after the Bazzite reboot activates dkms."; '
                'else echo "== Automatic setup: preparing CPU sensors and fan PWM =="; '
                + pwm_command
                + '; fi'
            )
        else:
            commands.extend([
                'echo "== Automatic setup: preparing CPU sensors and fan PWM =="',
                pwm_command,
            ])
    verification = verification_shell(
        selected,
        governor_binary=str(GOVERNOR_SPECS[context.selected_governor]['binary']),
        cpu_oc_script=context.cpu_destination / 'bc250_detect.py',
        core_unlock_script=context.core_script,
        cu_manager_script=cu_script,
    )
    report_lines = (
        f"Tools: {context.tool_dir}",
        f"Config: {context.paths.get('config', '')}",
        f"Profiles: {context.paths.get('perfiles', '')}",
        f"History: {context.paths.get('historial', '')}",
        f"CPU OC repo: {context.cpu_destination}",
        f"Cyan SMU repo: {context.tool_dir / context.cyan_directory}",
        f"CPU core unlock repo: {context.core_destination}",
        f"40CU repo: {context.cu_spec['destination']}",
    )
    commands.extend([
        'echo',
        'echo "== BC250 dependency verification =="',
        'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "PENDING: host packages will be verified after reboot."; else '
        + repo._join_shell_commands(verification) + '; fi',
        *(f"printf '%s\\n' {shlex.quote(line)}" for line in report_lines),
    ])
    if os_repo.info.family == 'steamos':
        commands.append(
            f"printf '%s\\n' "
            f"{shlex.quote(f'SteamOS fixes repo: {context.tool_dir / context.steamos_fix_directory}') }"
        )
    if os_repo.info.family == 'bazzite':
        reboot_notice = "printf '%s\\n' " + " ".join(
            shlex.quote(line) for line in BAZZITE_REBOOT_NOTICE_LINES
        )
        commands.append(
            'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then '
            + reboot_notice
            + '; '
            'else echo "== Finished successfully =="; fi'
        )
    else:
        commands.append(
            'if [ "$BC250_REBOOT_REQUIRED" = "1" ]; then echo "== Finished: reboot required =="; else echo "== Finished successfully =="; fi'
        )
    return repo._join_shell_commands(commands)
