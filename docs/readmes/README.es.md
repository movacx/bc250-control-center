# BC250 Control Center

[English](../../README.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Centro de control para la AMD BC-250 en Linux. Reúne en una sola aplicación de escritorio la monitorización, el control de la GPU, el ajuste de la CPU, las Unidades de Cómputo, los ventiladores y la actualización del BIOS, con límites claros y validaciones antes de cada cambio en el hardware.

## Capturas

[<img src="../../assets/screenshots/dashboard-overview.png" alt="Panel de BC250 Control Center" width="100%">](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

[Ver todas las capturas →](https://movacx.github.io/bc250-control-center/gallery/#dashboard)

## Instalación

### Arch, CachyOS y SteamOS (AUR)

```bash
yay -S bc250-control-center-git
```

### Paquetes de cada versión

Descarga el paquete de tu sistema desde la [última versión](https://github.com/movacx/bc250-control-center/releases/latest):

| Sistema | Archivo |
|---|---|
| Arch / CachyOS / Manjaro | `bc250-control-center-<versión>-any.pkg.tar.zst` |
| Fedora / Nobara / Bazzite | `bc250-control-center-<versión>.noarch.rpm` |
| Ubuntu / Debian | `bc250-control-center_<versión>_all.deb` |

```bash
# Arch / CachyOS / Manjaro
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst

# Fedora / Nobara
sudo dnf install ./bc250-control-center-*.rpm

# Bazzite / Fedora Atomic: el mismo RPM, y después reinicia en el nuevo despliegue
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot

# Ubuntu / Debian
sudo apt install ./bc250-control-center_*.deb
```

En Debian y Ubuntu usa `apt install` y no `dpkg -i`: así APT descarga también las dependencias. Si ya usaste `dpkg -i` y el paquete quedó a medias, se arregla con `sudo apt --fix-broken install`.

### Actualizaciones

No hace falta volver a esta página. Cuando sale una versión nueva, el panel lo avisa, muestra qué cambió y la instala con el gestor de paquetes de tu sistema, verificando antes su SHA-256.

En SteamOS la actualización desactiva la protección de solo lectura, instala y la vuelve a activar. Una actualización de SteamOS elimina todo lo instalado en el sistema, también esta aplicación: abre **Reinstall BC250 Control Center** desde el menú del Modo Escritorio y vuelve a preparar las dependencias. SteamOS pide la contraseña de `deck`; si nunca la creaste, ejecuta `passwd` en Konsole primero.

**¿Vienes de la 1.19?** Su actualizador integrado no puede instalar paquetes. Actualiza una vez a mano con el paquete de la [última versión](https://github.com/movacx/bc250-control-center/releases/latest); a partir de ahí la aplicación se actualiza sola. En Bazzite reemplaza la 1.19 en un solo paso y reinicia; si la instalaste con install-local.sh, quita primero esa copia:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Primer inicio

1. Abre **BC250 Control Center**.
2. La pantalla de bienvenida te pregunta el idioma, la apariencia y cómo quieres la barra lateral, y te ofrece instalar las herramientas que necesita la placa. Todo se puede cambiar después en **Configuración**.
3. Si quieres, sigue el tour guiado: recorre cada módulo y explica qué cambia en la placa.

Antes de aplicar cualquier cambio, revisa el estado del módulo: te dice qué está listo, qué falta y por qué.

## Qué hace

**Panel y monitorización**
- Panel con procesador, gráficos y refrigeración, núcleos en vivo, temperatura de cada chip GDDR6, rieles de alimentación (con el mod I2C) y el BIOS instalado.
- Módulo de Rendimiento con gráficas de CPU, GPU, VRAM, RAM, disco y red, y una vista de Sensores con mínimos, medias y máximos.

**Hardware**
- **GPU:** rangos seguros del governor para Cyan y Oberon, laboratorio de voltaje y puntos por encima de 2000 MHz.
- **CPU / SMU:** ajuste temporal y persistente, prueba de estabilidad y desbloqueo experimental de núcleos ocultos.
- **Unidades de Cómputo:** de 24 a 40 CU, con el estado en vivo y el de arranque por separado.
- **Ventiladores:** control PWM manual, curvas por temperatura, perfiles que se mantienen al reiniciar y exportación a archivo o a Decky.
- **Memoria:** tamaño de la VRAM, ZRAM, ZSWAP y archivo de intercambio.
- **Firmware (BIOS):** prepara un USB de actualización con P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 o P2.00, con cada archivo verificado.

**Sistema**
- Preparación de dependencias adaptada a cada distribución, con una terminal integrada donde se ve cada comando.
- Correcciones de compatibilidad: GFX1013 y async compute, FSR4 por juego, telemetría y ACPI.
- Controladores de Wi-Fi, Bluetooth e impresoras desde los repositorios oficiales de tu distribución.
- Diagnósticos, historial y exportación de métricas a CSV.

**Interfaz**
- Temas Claro, Oscuro y Azul noche, estilos Estándar y Formal, 10 colores de acento y escala de 70 % a 150 %.
- 30 idiomas y navegación con mando.

## Decky Quick Access (opcional)

Un panel para el menú de acceso rápido de SteamOS y el modo Juego de Steam. Trae los controles del día a día (GPU, CU, CPU, ventiladores y VRAM) sin salir del juego; la configuración avanzada sigue en la aplicación de escritorio.

- **Perfiles por juego:** asigna a cada juego un perfil de GPU y de ventiladores. Se aplica al abrirlo y todo vuelve a como estaba al cerrarlo.
- **Async compute en vivo:** muestra si el juego está usando el cómputo asíncrono y cuánto.
- **Presets de ventiladores:** con los nombres y velocidades que exportes desde el escritorio.

Para instalarlo, abre el **Panel**, baja hasta la sección **Decky** y elige la acción que te ofrece. Si falta Decky Loader, la aplicación lo instala; si ya está, instala o repara solo BC250 Quick Access. La preparación normal de dependencias nunca instala Decky por su cuenta.

Más detalles en el [README de Decky](../../integrations/decky/bc250-quick-access/README.md).

## Seguridad

El overclock, los cambios de Unidades de Cómputo, el control de ventiladores y la actualización del BIOS pueden congelar o apagar el equipo, hacer perder datos o dañar el hardware. Aplica un cambio cada vez, ten siempre una forma de volver atrás y no tomes las comprobaciones de la aplicación como una garantía del hardware.

## Herramientas externas y créditos

BC250 Control Center se apoya en el trabajo de la comunidad y no reclama como propio ninguno de estos proyectos. Cada herramienta se usa solo a través de flujos explícitos y revisados.

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): governor de la GPU.
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): governor alternativo compatible.
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) y [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): kernel y Mesa/RADV para GFX1013.
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): kernel y Mesa/RADV emparejados para Arch/CachyOS.
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute en Bazzite 44.
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) y [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) (OptiScaler Client): FSR4 por juego.
- [HelixSR](https://github.com/lonewolf0622/HelixSR): reconstrucción con DLSS Model E para juegos con FSR 3.1, por juego.

**CPU y Unidades de Cómputo**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): detección y ajuste de la CPU por SMU.
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) y [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): desbloqueo de núcleos.
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [su versión para SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) y [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Unidades de Cómputo.
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): estados de rendimiento de la CPU por ACPI.

**Sensores, memoria y ventiladores**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): telemetría de los reguladores (VRM).
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): temperatura de la memoria GDDR6.
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): tamaño de la VRAM por CMOS.
- [nct6687d](https://github.com/Fred78290/nct6687d): sensores NCT y PWM de los ventiladores.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): BIOS P3.00 original y Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell y MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): copia del kit de actualización de ASRock (P2.00 y P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): logotipo de arranque personalizado.

Las licencias, el estado de revisión y el alcance exacto de cada integración están en los [avisos de terceros](../THIRD_PARTY_NOTICES.md).

## Estructura del proyecto

```text
bc250-control-center/
├── src/bc250cc/              El núcleo, sin interfaz gráfica
│   ├── domain/               Reglas y límites de cada módulo (GPU, CPU, CU, ventiladores, firmware…)
│   ├── application/          Casos de uso que combinan esas reglas
│   ├── infrastructure/       Acceso al sistema: sensores, servicios, paquetes, GitHub
│   ├── platform/             Diferencias entre distribuciones y sistemas de arranque
│   └── shared/               Versión, rutas y contratos compartidos por todos los procesos
├── frontends/
│   ├── desktop/              Aplicación de escritorio en Qt
│   │   ├── pages/            Un archivo por módulo (panel, GPU, CPU, ventiladores, firmware…)
│   │   ├── components/       Piezas reutilizables de la interfaz
│   │   ├── onboarding/       Pantalla de bienvenida y tour guiado
│   │   ├── console/          Terminal integrada
│   │   ├── theme/            Temas, estilos, colores e iconos
│   │   └── i18n/             Traducciones a 30 idiomas
│   └── cli.py                Modo de línea de comandos
├── integrations/decky/       Plugin Decky Quick Access para el modo Juego
├── privileged/               Lo que se ejecuta como root, aislado y revisado
│   ├── helpers/              Un ayudante por tarea privilegiada
│   ├── lib/                  Código compartido por esos ayudantes
│   └── policies/             Permisos de Polkit
├── packaging/                Paquetes .pkg.tar.zst, .rpm y .deb, y el PKGBUILD del AUR
├── scripts/                  Lanzadores, instalador local y utilidades de sistema
├── assets/                   Iconos, capturas y galería web
├── docs/                     Documentación, avisos de terceros y traducciones de este README
└── tests/                    Más de 4000 pruebas automáticas
```

Licencia [MIT](../../LICENSE).
