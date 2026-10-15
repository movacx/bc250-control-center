# BC250 Control Center

[English](../../README.md) · [Português](README.pt-BR.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Polski](README.pl.md) · [中文](README.zh-CN.md) · [日本語](README.ja.md)

Una aplicación de escritorio para sacarle partido a la AMD BC-250 en Linux. Me cansé de andar entre una docena de scripts y mensajes de foro, así que la monitorización, el gobernador de la GPU, el ajuste de la CPU, las Unidades de Cómputo, los ventiladores y el BIOS están en un solo sitio. Cada cambio en el hardware tiene límites y una comprobación antes de aplicarse, porque esta placa no perdona los tanteos.

Está hecha para la comunidad de la BC-250 y con su ayuda: casi todas las funciones empezaron como el reporte de un fallo o un «¿puede hacer X?» en el Discord.

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

No hace falta que vuelvas aquí. Cuando hay una versión nueva el panel te avisa, te enseña los cambios y la instala con tu gestor de paquetes, tras comprobar su SHA-256.

En SteamOS la actualización desactiva la protección de solo lectura, instala y la vuelve a activar. Ojo: una actualización del sistema de SteamOS borra todo lo instalado en el sistema, esta aplicación incluida: abre **Reinstall BC250 Control Center** desde el menú del Modo Escritorio y vuelve a preparar las dependencias. SteamOS pide la contraseña de `deck`; si nunca la creaste, ejecuta `passwd` en Konsole primero.

**¿Vienes de la 1.19?** Su actualizador no sabe instalar paquetes, perdona. Actualiza una vez a mano con el paquete de la [última versión](https://github.com/movacx/bc250-control-center/releases/latest); a partir de ahí la aplicación se actualiza sola. En Bazzite reemplaza la 1.19 en un solo paso y reinicia; si la instalaste con install-local.sh, quita primero esa copia:

```bash
# Bazzite / Fedora Atomic
sudo rpm-ostree uninstall bc250-control-center --install ./bc250-control-center-*.noarch.rpm
systemctl reboot

# install-local.sh
bash scripts/uninstall-local.sh
```

## Primer inicio

1. Abre **BC250 Control Center**.
2. La bienvenida pregunta idioma, apariencia y barra lateral, y ofrece instalar lo que necesita la placa. Todo se cambia después en **Configuración**.
3. El tour guiado merece un minuto: pasa por cada módulo y dice qué toca en la placa.

Antes de aplicar nada, mira la línea de estado del módulo. Dice qué está listo, qué falta y por qué.

## Qué hace

**Panel y monitorización**
- Un panel con procesador, gráficos y refrigeración, núcleos en vivo, la temperatura de cada chip GDDR6, los rieles de alimentación (si hiciste el mod I2C) y el BIOS que tienes instalado.
- Módulo de Rendimiento con gráficas de CPU, GPU, VRAM, RAM, disco y red, y una vista de Sensores con mínimos, medias y máximos.

**Hardware**
- **GPU:** rangos seguros del governor para Cyan y Oberon, laboratorio de voltaje y puntos por encima de 2000 MHz.
- **CPU / SMU:** ajuste temporal y persistente, prueba de estabilidad y desbloqueo experimental de núcleos ocultos.
- **Unidades de Cómputo:** de 24 a 40 CU, con el estado en vivo y el de arranque por separado.
- **Ventiladores:** control PWM manual, curvas por temperatura, perfiles que se mantienen al reiniciar y exportación a archivo o a Decky.
- **Memoria:** tamaño de la VRAM, ZRAM, ZSWAP y archivo de intercambio.
- **Firmware (BIOS):** prepara un USB de actualización con P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 o P2.00, con cada archivo verificado.

**Sistema**
- Preparación de dependencias que se adapta a tu distribución. Corre en una terminal integrada para que veas cada comando.
- Correcciones de compatibilidad: GFX1013 y async compute, FSR4 por juego, telemetría y ACPI. En Ubuntu y Fedora también avisa si el escritorio se dibuja con la CPU (llvmpipe) porque Mesa es demasiado viejo, y en Ubuntu puede arreglarlo desde el PPA de kisak.
- Dolby Digital 5.1 por HDMI para receptores y barras de sonido, y control de la TV por HDMI-CEC con el cecd de Valve.
- Controladores de Wi-Fi, Bluetooth e impresoras desde los repositorios oficiales de tu distribución.
- Diagnósticos, historial y exportación de métricas a CSV.

**Interfaz**
- Temas Claro, Oscuro y Azul noche, estilos Estándar y Formal, 10 colores de acento y escala de 70 % a 150 %.
- 30 idiomas y navegación con mando.

## Decky Quick Access (opcional)

Un panel para el menú de acceso rápido del modo Juego, para cambiar lo de siempre (GPU, CU, CPU, ventiladores, VRAM) sin salir del juego. La configuración avanzada se queda en la aplicación de escritorio.

- **Perfiles por juego:** asigna a cada juego un perfil de GPU y de ventiladores. Se aplica al abrirlo y todo vuelve a como estaba al cerrarlo.
- **Async compute en vivo:** muestra si el juego está usando el cómputo asíncrono y cuánto.
- **Presets de ventiladores:** con los nombres y velocidades que exportes desde el escritorio.

Para instalarlo, abre el **Panel**, baja a **Decky** y elige la acción que ofrece. Si falta Decky Loader, lo instala también; si ya está, solo instala o repara BC250 Quick Access. Preparar dependencias nunca instala Decky por su cuenta.

Más detalles en el [README de Decky](../../integrations/decky/bc250-quick-access/README.md).

## Seguridad

El overclock, desbloquear Unidades de Cómputo, el control de ventiladores y flashear un BIOS pueden congelar el equipo, perder datos o matar la placa. Cambia una cosa cada vez, ten siempre un camino de vuelta y no leas las comprobaciones de la app como una garantía: atrapan los errores evidentes, no todos.

## Herramientas externas y créditos

Nada de esto existiría sin quienes hicieron la ingeniería inversa de la placa. Los proyectos de abajo son suyos, no míos, y la aplicación solo los toca mediante flujos que he leído y fijado a una revisión.

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
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, el demonio HDMI-CEC de Valve.

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): BIOS P3.00 original y Chipset Menu.
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell y MeiMeiDXE v3.
- [BC-250](https://github.com/kenavru/BC-250): copia del kit de actualización de ASRock (P2.00 y P5.00).
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): logotipo de arranque personalizado.

**Proyectos relacionados que sigo** (la aplicación todavía no los usa; licencias según las muestra GitHub)
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) y [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0): temperaturas del VRM y de la memoria como módulos de kernel.
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0): otra forma de configurar Bazzite.
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) y [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm): investigación de VCN y un driver abierto de Windows. Ninguno declara licencia, así que solo los enlazo.

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
└── tests/                    Más de 5000 pruebas automáticas, con os-release de 37 distribuciones reales
```

## Contribuir

Lo más útil que puedes mandar es un reporte de fallo, sobre todo con tu distribución, tu kernel y lo que imprimió la terminal. Si usas una distribución que no aparece arriba, cuéntame cómo te fue, bien o mal.

Licencia [MIT](../../LICENSE).
