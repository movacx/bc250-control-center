"""Explicit keyboardspecialist lifecycle routes; never a fallback on failure."""

ALTERNATIVE_ACTIONS = {
    'kernel-install': ('Prepare kernel compatibility', 'Preparar compatibilidad del kernel'),
    'kernel-status': ('Check kernel compatibility', 'Verificar compatibilidad del kernel'),
    'kernel-rollback': ('Restore the stock module for the running kernel', 'Restaurar módulo original del kernel actual'),
    'graphics-status': ('Check Mesa / RADV', 'Verificar Mesa / RADV'),
    'graphics-install': ('Install Mesa / RADV', 'Instalar Mesa / RADV'),
    'graphics-uninstall': ('Remove Mesa / RADV', 'Quitar Mesa / RADV'),
    'graphics-install-fsr4': ('Install per-game FSR4', 'Instalar FSR4 por juego'),
    'graphics-uninstall-fsr4': ('Remove per-game FSR4', 'Quitar FSR4 por juego'),
    'proton-status': ('Check BC-250 GE-Proton', 'Verificar BC-250 GE-Proton'),
    'proton-install': ('Install / update BC-250 GE-Proton', 'Instalar / actualizar BC-250 GE-Proton'),
    'proton-uninstall': ('Remove BC-250 GE-Proton', 'Quitar BC-250 GE-Proton'),
}


def run_alternative(repository, action: str):
    if action not in ALTERNATIVE_ACTIONS:
        raise ValueError('Unknown SteamOS alternative action: ' + str(action))
    if repository._os_repository().info.family != 'steamos':
        raise RuntimeError('The alternative backend is available only on SteamOS.')
    if action == 'kernel-install':
        return repository.preparar_compatibilidad_steamos_alternativo()
    if action == 'kernel-status':
        return repository._abrir_terminal(
            repository._steamos_compatibility_stage_command(install=False),
            'SteamOS · keyboardspecialist · kernel status')
    if action == 'kernel-rollback':
        return repository.restaurar_kernel_steamos_alternativo()
    component, _, operation = action.partition('-')
    if component == 'graphics':
        return repository.gestionar_graficos_steamos_alternativo(operation)
    return repository.gestionar_proton_steamos_alternativo(operation)
