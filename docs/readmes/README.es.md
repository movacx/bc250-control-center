# BC250 Control Center

[English](../../README.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centro de control para Linux y AMD BC-250: monitorización, control de GPU, ajuste de CPU, Unidades de Cómputo y ventiladores en una aplicación de escritorio.

## Capturas

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Panel de BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Instalación

### Desde código fuente

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center/scripts
./install-local.sh
```

Para eliminar una instalación local, ejecuta `./uninstall-local.sh` desde la misma carpeta.

### Arch, CachyOS y Manjaro

```bash
yay -S bc250-control-center-git
```

### Paquetes de lanzamiento

Descarga el paquete desde la [última versión](https://github.com/movacx/bc250-control-center/releases). Fedora, Nobara y Bazzite usan el mismo RPM `noarch`; solo cambia la instalación porque Bazzite usa una imagen de sistema inmutable.

```bash
# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic — instala el mismo RPM y reinicia en el nuevo despliegue
sudo rpm-ostree install ./bc250-control-center-*.rpm # Bazzite / Fedora Atomic
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

## Primer inicio

1. Abre `bc250-control-center`.
2. En Dashboard, selecciona **Prepare dependencies**.
3. Revisa el estado del módulo antes de aplicar un cambio.

## Qué hace

- Métricas en vivo de CPU, GPU, memoria, almacenamiento, red, temperaturas y ventiladores.
- Rangos seguros del governor de GPU para Cyan y Oberon.
- Ajuste temporal y persistente de CPU, además de desbloqueo experimental de núcleos ocultos.
- Controles de 24–40 Compute Units con estado vivo y de arranque por separado.
- Control PWM manual y curvas de ventilador por temperatura de GPU cuando el controlador compatible está listo.
- Comprobaciones del sistema, diagnósticos, historial y exportación de métricas a CSV.
- Localización de escritorio, escala de interfaz y navegación opcional por mando.

## Decky Quick Access opcional

El panel opcional de Decky es para SteamOS/Game Mode y se instala desde BC250 Control Center. Ofrece controles acotados de GPU, CU, CPU y ventiladores, mientras que la aplicación de escritorio conserva la configuración avanzada.

Después de instalar la aplicación, abre **Dashboard**, desplázate a la sección inferior **Decky** y selecciona la acción ofrecida. La aplicación instala Decky Loader si falta, o instala/repara solo BC250 Quick Access si Decky ya está disponible. La preparación normal de dependencias nunca instala Decky automáticamente.

Consulta el [README de Decky](../../integrations/decky/bc250-quick-access/README.md) para la ruta corta dentro de la aplicación, acciones compatibles y límites.

## Seguridad

El overclock, los cambios de Compute Units y el control de ventiladores pueden provocar congelamientos, apagados, pérdida de datos o daño de hardware. Aplica un cambio por vez, conserva un método de recuperación y no tomes las comprobaciones de software como validación del hardware.

## Idiomas

La interfaz de escritorio admite 30 idiomas y puede seguir el idioma del sistema o cambiarse en Settings. Incluye inglés, español, portugués, ruso, ucraniano, alemán, francés, polaco, chino, japonés, coreano y más.

## Herramientas externas y créditos

BC250 Control Center se basa en trabajo comunitario y no reclama propiedad sobre estos proyectos. Las herramientas se usan únicamente mediante flujos explícitos y revisados.

- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu) — governor de GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor) — alternativa compatible de governor de GPU.
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc) — detección y ajuste de CPU SMU.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager) y [su backend SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) — fuentes de investigación e integración de Compute Units.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) — flujo experimental de desbloqueo de núcleos CPU.
- [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos) y [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) — flujos explícitos de compatibilidad; en Fedora se actualiza `main` y se invoca el instalador oficial de DryhoppedIPA.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) — flujo oficial `v3` aislado por usuario para Arch/CachyOS; Manjaro es experimental y debe superar las pruebas ABI y Vulkan de upstream.
- [nct6687d](https://github.com/Fred78290/nct6687d) — soporte de controlador de sensores NCT y PWM.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250) — paquetes externos emparejados de kernel y Mesa/RADV para Arch/CachyOS, incluidas las correcciones de cómputo asíncrono GFX1013.

Consulta los [avisos de terceros](../THIRD_PARTY_NOTICES.md) para licencias, estado de revisión y el límite exacto de integración de cada proyecto.

## Estructura del proyecto

```text
src/bc250cc/   lógica de aplicación y sistema
frontends/     adaptadores Desktop Qt, CLI y Quick Access
privileged/    helpers protegidos y política Polkit
packaging/     metadatos de paquetes y scripts de configuración por distribución
scripts/       lanzadores e instalador local
```

Licencia [MIT](../../LICENSE).
