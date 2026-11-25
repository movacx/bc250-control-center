# BC250 Control Center

Configura, ajusta y supervisa la AMD BC-250 en Linux desde el escritorio, la terminal, el navegador o el teléfono.

<p align="center">
  <a href="https://movacx.github.io/bc250-control-center/gallery/#dashboard"><img src="../../assets/screenshots/demo.gif" alt="Panel de BC250 Control Center" width="100%"></a>
</p>

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/English-238636?style=for-the-badge" alt="Read in English"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/Espa%C3%B1ol-1f6feb?style=for-the-badge" alt="Leer en español"></a>
  <a href="README.pt-BR.md"><img src="https://img.shields.io/badge/Portugu%C3%AAs-8250df?style=for-the-badge" alt="Ler em português"></a>
  <a href="README.ru.md"><img src="https://img.shields.io/badge/%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-bb2f7b?style=for-the-badge" alt="Читать на русском"></a>
  <a href="README.uk.md"><img src="https://img.shields.io/badge/%D0%A3%D0%BA%D1%80%D0%B0%D1%97%D0%BD%D1%81%D1%8C%D0%BA%D0%B0-0969da?style=for-the-badge" alt="Читати українською"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/Deutsch-57606a?style=for-the-badge" alt="Auf Deutsch lesen"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/Fran%C3%A7ais-c9510c?style=for-the-badge" alt="Lire en français"></a>
  <a href="README.pl.md"><img src="https://img.shields.io/badge/Polski-0a7d6c?style=for-the-badge" alt="Czytaj po polsku"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-9a6700?style=for-the-badge" alt="阅读中文说明"></a>
  <a href="README.ja.md"><img src="https://img.shields.io/badge/%E6%97%A5%E6%9C%AC%E8%AA%9E-0550ae?style=for-the-badge" alt="日本語で読む"></a>
</p>

<p align="center">
  <a href="https://ko-fi.com/movacx"><img src="https://img.shields.io/badge/Ko--fi-Donate-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Donate on Ko-fi"></a>
</p>

Reúne en un solo programa lo que la placa necesita: gobernador de la GPU, ajuste de la CPU, unidades de cómputo, ventiladores, memoria, BIOS, escalado en juegos y preparación del sistema según tu distribución. Todas las interfaces usan los mismos límites y los mismos controles; ninguna puede hacer algo que las demás consideren inseguro.

Hay más capturas en la [galería](https://movacx.github.io/bc250-control-center/gallery/).

## Contenido

- [Elige tu interfaz](#elige-tu-interfaz)
- [Requisitos y distribuciones](#requisitos-y-distribuciones)
- [Instalación](#instalación)
  - [Paquetes](#paquetes) · [Escritorio](#escritorio) · [Terminal](#terminal) · [Web](#web) · [Aplicación para Android](#aplicación-para-android) · [SteamOS](#steamos)
- [Primeros pasos](#primeros-pasos)
- [Qué puedes hacer](#qué-puedes-hacer)
- [Usar cada interfaz](#usar-cada-interfaz)
- [Contraseña y permisos](#contraseña-y-permisos)
- [Actualizar y desinstalar](#actualizar-y-desinstalar)
- [Solución de problemas](#solución-de-problemas)
- [Seguridad del hardware](#seguridad-del-hardware)
- [Para desarrolladores](#para-desarrolladores)
- [Créditos](#créditos)

## Elige tu interfaz

| Interfaz | Para qué sirve mejor | Qué necesita la placa |
| --- | --- | --- |
| **Escritorio** | Instalación, ajuste y diagnóstico completos | Un entorno gráfico |
| **Terminal (TUI)** | Una consola local o una sesión SSH, con teclado o ratón | Solo una terminal |
| **Web** | Controlar la placa desde otro equipo o un teléfono de tu red | Nada más; no hace falta pantalla |
| **Aplicación para Android** | Lo mismo que la web, instalado en el teléfono | El acceso web encendido |
| **Decky** (opcional) | Los controles de cada día en el Modo Juego de Steam | Decky Loader |

La instalación de escritorio ya incluye la terminal y la web. Si solo quieres una de ellas, cada una tiene su propio instalador y no instala lo que no necesita.

## Requisitos y distribuciones

- Una placa AMD BC-250.
- Python 3.11 o posterior.
- Una cuenta con permiso de administrador (`sudo`).

| Distribución | Cómo se instala |
| --- | --- |
| Arch Linux, CachyOS, Manjaro | AUR o paquete `.pkg.tar.zst` |
| Fedora, Nobara | Paquete `.rpm` |
| Bazzite y otras Fedora Atomic | Paquete `.rpm` con `rpm-ostree` |
| Ubuntu, Linux Mint, Debian 13 | Paquete `.deb` |
| SteamOS (beta) | Paquete `.pkg.tar.zst` o AUR |

Otras distribuciones, también las que usan OpenRC, se detectan y se atienden en lo posible, pero no se prueban en cada versión.

## Instalación

Hay dos caminos. Los **paquetes** son los recomendados: se actualizan con el sistema. Los **instaladores desde el repositorio** sirven si prefieres clonar el proyecto o instalar una sola interfaz.

### Paquetes

Descarga el de tu distribución desde la [última versión](https://github.com/movacx/bc250-control-center/releases/latest).

**Arch Linux, CachyOS y Manjaro**

```bash
yay -S bc250-control-center-git
```

o, con el paquete descargado:

```bash
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
```

**Fedora y Nobara**

```bash
sudo dnf install ./bc250-control-center-*.rpm
```

**Bazzite y Fedora Atomic** (hay que reiniciar)

```bash
sudo rpm-ostree install ./bc250-control-center-*.rpm
systemctl reboot
```

**Ubuntu, Linux Mint y Debian**

```bash
sudo apt install ./bc250-control-center_*.deb
```

Usa `apt install` y no `dpkg -i`, para que también se instalen las dependencias. Si una instalación quedó a medias, ejecuta `sudo apt --fix-broken install`.

### Desde el repositorio

Clona el proyecto una sola vez, con tu usuario de siempre y sin `sudo`:

```bash
git clone https://github.com/movacx/bc250-control-center.git
cd bc250-control-center
```

Desde esa carpeta instala la interfaz que quieras. Los tres instaladores colocan el programa en `~/.local`, comprueban lo que falta, te piden permiso de administrador solo para instalar dependencias y los controles protegidos del hardware, y se pueden ejecutar otra vez para actualizar.

| Quiero… | Comando | Se abre con |
| --- | --- | --- |
| Todo: escritorio, terminal y web | `bash scripts/install-local.sh` | `bc250-control-center` |
| Solo la terminal | `bash scripts/install-tui.sh` | `bc250-control-center-tui` |
| Solo la web | `bash scripts/install-web.sh` | El navegador o la aplicación de Android |

Si la terminal no encuentra el comando, `~/.local/bin` no está en tu `PATH`; ábrelo con la ruta completa, por ejemplo `~/.local/bin/bc250-control-center-tui`.

> En Bazzite y Fedora Atomic los controles protegidos no se pueden instalar así. Instala el paquete `.rpm` con `rpm-ostree` y reinicia.

### Escritorio

```bash
bash scripts/install-local.sh
```

Instala la aplicación gráfica con su acceso en el menú, y con ella la terminal y la web. Para abrirla:

```bash
bc250-control-center
```

### Terminal

```bash
bash scripts/install-tui.sh
```

No instala PyQt6, polkit ni nada gráfico. Para ver qué falta sin cambiar nada:

```bash
bash scripts/install-tui.sh --check
```

Para abrirla, aquí o por SSH:

```bash
bc250-control-center-tui
```

```bash
ssh -t usuario@ip-de-la-placa bc250-control-center-tui
```

### Web

```bash
bash scripts/install-web.sh
```

Instala la interfaz web, la enciende para tu red de casa y muestra la dirección, la clave y un código QR. La placa no necesita pantalla. Con `--no-start` la instala sin encenderla.

| Comando | Qué hace |
| --- | --- |
| `bc250-control-center web setup` | Enciende el acceso y muestra dirección, clave y QR |
| `bc250-control-center web status` | Los vuelve a mostrar |
| `bc250-control-center web stop` | Apaga el acceso |

No hace falta Node.js ni ningún otro servidor. Con el escritorio instalado puedes hacer lo mismo desde **Acceso remoto**.

### Aplicación para Android

1. Descarga el archivo `.apk` desde la [última versión](https://github.com/movacx/bc250-control-center/releases/latest) e instálalo. Android te pedirá permiso para instalar aplicaciones fuera de la tienda.
2. En la placa, abre **Acceso remoto**, enciende el acceso web y activa **Accesible desde la red local** (o ejecuta `bc250-control-center web setup`).
3. Con el teléfono en la misma red Wi-Fi, abre la aplicación y escribe la dirección que muestra la placa, o pega el enlace de su código QR.

Necesita Android 7.0 o posterior. La aplicación recuerda la sesión y comprueba que siempre se conecta a tu placa. Solo funciona en tu red de casa: no usa ningún servidor de internet.

<p align="center">
  <img src="../../assets/screenshots/mobile-interface.png" alt="La interfaz en un teléfono: panel, CPU, unidades de cómputo, GPU y voltaje" width="100%">
</p>

¿iPhone? Abre la dirección de la web en el navegador; tiene la misma interfaz y se puede añadir a la pantalla de inicio.

### SteamOS

SteamOS protege su partición de sistema contra escritura, así que el paquete solo se puede instalar mientras esa protección está apagada. En el Modo Escritorio, abre Konsole:

```bash
sudo steamos-readonly disable
sudo pacman-key --init
sudo pacman-key --populate archlinux holo
sudo pacman -Syy
sudo pacman -U ./bc250-control-center-*-any.pkg.tar.zst
sudo steamos-readonly enable
```

Si el usuario `deck` no tiene contraseña, créala antes con `passwd`. Después de una actualización de SteamOS, usa **Reinstall BC250 Control Center** en el menú del Modo Escritorio y vuelve a preparar el sistema.

## Primeros pasos

1. Abre BC250 Control Center. La bienvenida te pide idioma, unidad de temperatura y apariencia.
2. En el **Panel**, usa **Preparar el sistema BC250**. Te enseña lo que va a instalar en tu distribución antes de hacerlo.
3. Reinicia si te lo pide.
4. Antes de cambiar algo, lee la línea de estado de esa página: dice qué está listo y qué falta.
5. Cambia una cosa a la vez y comprueba temperaturas y estabilidad antes de guardarla para el arranque.

El recorrido guiado explica qué cambia cada página en la placa. Puedes repetirlo en **Configuración › General**.

## Qué puedes hacer

| Página | Para qué sirve |
| --- | --- |
| **Panel** | CPU, gráficos, refrigeración, carga por núcleo, temperatura de la GDDR6 por chip, BIOS instalada y alimentación. Desde aquí se prepara el sistema. |
| **CPU / SMU** | Perfiles de frecuencia, voltaje y límite de temperatura, prueba de estabilidad, aplicarlos al encender y desbloqueo de núcleos ocultos, temporal o permanente. |
| **Unidades de cómputo** | Activar y desactivar pares de unidades en vivo, ver los registros, guardar la selección y recuperarla al arrancar. Las disponibles dependen de cada placa. |
| **Gobernador de GPU** | Perfiles de frecuencia, control del gobernador (Cyan u Oberon), compatibilidad con cada kernel y laboratorio de voltaje. |
| **Ventiladores** | Velocidad fija, curvas por temperatura, mezcla de varias fuentes, perfiles, calibración y control desde el arranque. |
| **Rendimiento** | Gráficas de CPU, GPU, VRAM, RAM, disco y red, todos los sensores y exportación a CSV. |
| **Procesos** | Qué usa la memoria y la GPU; pausar o cerrar, y gestionar la memoria mientras juegas. |
| **Ajustes adicionales** | Compatibilidad (kernel, Mesa, async compute, ACPI), escalado por juego (FSR4 con OptiScaler y HelixSR), VRAM, ZRAM, ZSWAP y swap, Dolby Digital 5.1 y control de la TV por HDMI-CEC. |
| **Firmware (BIOS)** | Prepara un USB con P3.00 Chipset Menu, MeiMeiDXE v3, P5.00, P3.00 o P2.00, y logotipo de arranque propio. Cada archivo se verifica; la aplicación nunca escribe la BIOS por sí misma. |
| **Caja negra** | Graba lo que hace la placa para que un reporte enseñe los segundos previos a un cuelgue. |
| **Acceso remoto** | Enciende la web, muestra el QR y administra los dispositivos y los permisos. |

Además: 30 idiomas, temas claro y oscuro, tamaño de la interfaz, °C o °F y manejo con mando.

> Las lecturas de los rieles de alimentación necesitan la modificación I2C de la placa; la aplicación incluye una guía con fotos.

## Usar cada interfaz

### Terminal

| Tecla | Acción |
| --- | --- |
| `↑` `↓` o `j` `k` | Elegir |
| `Enter` | Abrir una sección o ejecutar |
| `Esc` o `Tab` | Volver al menú |
| `[` `]` | Cambiar de pestaña |
| `/` | Buscar |
| `RePág` `AvPág` | Desplazar |
| Ratón | Elegir y desplazar |
| `?` | Ayuda |
| `q` | Salir |

Las operaciones se ven en la consola integrada. Ahí se escribe la contraseña si hace falta, y `Ctrl+C` detiene lo que esté en marcha. Para abrir una página concreta o sin color:

```bash
bc250-control-center-tui --page gpu --theme mono
```

### Web y teléfono

- **Emparejar un teléfono:** escanea el QR de **Acceso remoto**. Sirve una vez y se renueva solo.
- **Entrar desde un ordenador:** abre la dirección y escribe la **clave de acceso remoto**.
- **Un dispositivo emparejado puede controlar el hardware.** En **Dispositivos emparejados** puedes dejarlo solo para mirar, ponerle una duración o desconectarlo.
- **Nueva clave de acceso** desconecta a todos. Úsala si alguien más conoce la clave.
- **Aviso del navegador:** la conexión va cifrada con un certificado creado en tu placa. El navegador avisará hasta que confíes en él; puedes descargarlo en **Acceso remoto** y comparar su huella.

La web solo acepta conexiones de tu red de casa. El programa no abre puertos en el router ni crea túneles. Con **Accesible desde la red local** apagado, solo se puede usar desde la propia placa.

### Decky

BC250 Quick Access añade un panel al menú rápido del Modo Juego: GPU, unidades de cómputo, CPU, ventiladores y VRAM, con perfiles por juego. Se instala desde la sección **Decky** del Panel. Más detalles en el [README del complemento](../../integrations/decky/bc250-quick-access/README.md).

### Línea de comandos

```bash
bc250-control-center-cli --help
```

Incluye consultas del sistema y los sensores, la caja negra, perfiles, copias de recuperación y el diagnóstico completo (`diagnose --full`).

## Contraseña y permisos

El programa nunca se ejecuta como administrador. Los cambios en el hardware los hacen controles protegidos, cada uno con una lista cerrada de operaciones y límites.

**Acciones sin contraseña.** En CPU, unidades de cómputo, GPU y ventiladores no se pide la contraseña de Linux a cada cambio.

- Viene **activado** para la cuenta que instala el programa con `sudo`. Si tu instalación no pudo hacerlo, actívalo una vez en **Acceso remoto › Permisos**.
- Se apaga ahí mismo, y una actualización no lo vuelve a encender.
- **Sigue pidiendo contraseña** todo lo demás: desbloqueo de núcleos, temperatura de la GDDR6, instalar componentes, memoria, kernel y BIOS.
- **Ten en cuenta:** mientras está activo, quien use tu sesión o un dispositivo emparejado con control puede hacer esos cambios. Apágalo si compartes el equipo.

Las confirmaciones de las acciones con riesgo aparecen siempre, esté activado o no.

## Actualizar y desinstalar

**Paquetes.** La aplicación avisa de las versiones nuevas, muestra los cambios, verifica el paquete y lo instala. También puedes usar tu gestor de paquetes.

**Repositorio.** Desde la misma carpeta, y repitiendo el instalador que usaste:

```bash
git pull --ff-only
bash scripts/install-local.sh
```

**Aplicación para Android.** Instala el `.apk` nuevo encima; conserva la sesión.

**Desinstalar lo instalado desde el repositorio:**

```bash
bash scripts/uninstall-local.sh
```

Con `--dry-run` enseña lo que quitaría y con `--purge-user-data` borra también tu configuración. `install-tui.sh` e `install-web.sh` aceptan `--uninstall`.

**Desinstalar un paquete:** `sudo pacman -R`, `sudo dnf remove`, `sudo rpm-ostree uninstall` o `sudo apt remove`, seguido de `bc250-control-center`. Si quedan ajustes que necesitan deshacerse antes (memoria, arranque, ACPI), la desinstalación se detiene y te dice cuáles.

## Solución de problemas

| Qué pasa | Qué hacer |
| --- | --- |
| El teléfono no encuentra la placa | Comprueba que están en la misma red y que **Accesible desde la red local** está activado. Prueba con la dirección numérica en vez del nombre. |
| La web dice que el firewall bloquea | **Acceso remoto › Configurar firewall de la red local**. |
| El navegador avisa del certificado | Es normal la primera vez. Compara la huella con la de **Acceso remoto**. |
| Sigue pidiendo contraseña | **Acceso remoto › Permisos**. Si estaba activado, apágalo y enciéndelo para renovarlo. |
| Ventiladores en solo lectura | **Ventiladores › Preparar controlador PWM**. |
| El gobernador no arranca | Abre **Ver estado** en la página de GPU; dice la causa y cómo arreglarla. |

**Configuración › Soporte** incluye un manual sin conexión con los errores conocidos, adaptado a tu distribución.

### Enviar un reporte

Los errores muestran un código, por ejemplo `BC250-GPU-001`. Pulsa **Reportar este problema** y se abre un formulario con el código, el error y los datos del sistema ya puestos. **Puedes leer todo antes de enviarlo**, y las rutas de tu carpeta personal se sustituyen por `~`. También puedes abrir un [issue en GitHub](https://github.com/movacx/bc250-control-center/issues) con tu distribución, la versión del kernel y la salida de la terminal.

## Seguridad del hardware

Subir frecuencias, desbloquear unidades o núcleos, cambiar los ventiladores y grabar una BIOS puede volver inestable el sistema, hacer perder datos o dañar la placa. Cambia una cosa a la vez y ten siempre cómo volver atrás. Las comprobaciones del programa evitan los errores comunes, pero no son una garantía.

## Para desarrolladores

```text
src/bc250cc/        El núcleo, sin interfaz: reglas, operaciones y acceso al sistema
frontends/desktop/  Aplicación de escritorio (PyQt6)
frontends/tui/      Interfaz de terminal (curses)
frontends/web/      Servidor web y sus operaciones
frontends/web/app/  Web y aplicación de Android (Kotlin Multiplatform, Compose)
integrations/       Complemento de Decky y recepción de reportes
privileged/         Lo que se ejecuta como administrador, aislado y revisado
packaging/          Paquetes .pkg.tar.zst, .rpm, .deb y AUR
scripts/            Instaladores, herramientas de desarrollo y pruebas
tests/              Pruebas
```

Ejecutar el escritorio sin instalar:

```bash
./run.sh
```

Compilar la web y la aplicación de Android (hace falta un JDK y, para Android, su SDK):

```bash
scripts/development/build-web.sh
```

```bash
cd frontends/web/app && ./gradlew :androidApp:assembleDebug
```

Los límites entre capas están en [Arquitectura](../ARQUITECTURA_MVC.md), y los puntos de entrada en [Frontends](../../frontends/README.md). Los avisos de seguridad se envían como explica [SECURITY.md](../../SECURITY.md).

## Créditos

Este proyecto se apoya en el trabajo de la comunidad de la BC-250. Los proyectos de abajo pertenecen a sus autores; la aplicación los integra mediante flujos revisados y fijados a una versión concreta. Las licencias y el alcance de cada integración están en los [avisos de terceros](../THIRD_PARTY_NOTICES.md).

**GPU**
- [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu): gobernador de la GPU
- [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor): gobernador alternativo
- [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) y [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos): kernel y Mesa/RADV para GFX1013
- [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250): kernel y Mesa/RADV para Arch y CachyOS
- [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite): async compute en Bazzite 44, con parches de RADV también compilados para Arch, CachyOS y Fedora con kernel 7.2 o posterior

**Escalado**
- [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) y [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork): OptiScaler Client, FSR4 por juego
- [HelixSR](https://github.com/lonewolf0622/HelixSR): reconstrucción DLSS Model E en juegos con FSR 3.1

**CPU y Unidades de Cómputo**
- [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc): detección y ajuste de la CPU mediante la SMU
- [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) y [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): desbloqueo de núcleos
- [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix): estados de rendimiento de la CPU mediante ACPI
- [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager), [bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) y [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): Unidades de Cómputo

**Sensores, memoria y ventiladores**
- [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry): telemetría de los reguladores de voltaje (VRM) y las fotos de la guía I2C
- [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature): temperatura de la GDDR6
- [bc250_memcfg](https://github.com/fanoush/bc250_memcfg): tamaño de la VRAM mediante CMOS
- [nct6687d](https://github.com/Fred78290/nct6687d): sensores NCT y PWM de los ventiladores
- [linux-cec](https://gitlab.steamos.cloud/holo/linux-cec): cecd, el demonio HDMI-CEC de Valve

**Firmware**
- [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios): BIOS P3.00 original y Chipset Menu
- [AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script): UEFI Shell y MeiMeiDXE v3
- [BC-250](https://github.com/kenavru/BC-250): copia del kit de actualización de ASRock (P2.00 y P5.00)
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): logotipo de arranque personalizado

**Proyectos relacionados** (la aplicación no los usa; licencias según GitHub)
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) y [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0): temperaturas del VRM y de la memoria como módulos del kernel
- [bc250-bazzite-suite](https://github.com/RobertoTorino/bc250-bazzite-suite) (GPL-3.0): suite de configuración para Bazzite
- [bc250-vcn-research](https://github.com/Shalasere/bc250-vcn-research) y [amdgpu-wddm](https://github.com/D-Ogi/amdgpu-wddm): investigación de la codificación de vídeo VCN y un driver abierto para Windows (sin licencia declarada; solo enlazados)
