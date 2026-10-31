# Revisión del TUI y distribuciones — 2026-10-31

## Resultado

El TUI utiliza navegación por teclado en TTY y SSH. Se retiraron `--touch`,
la selección automática del modo táctil, los controles táctiles de ajustes,
las teclas en pantalla y la captura del ratón. Los archivos de dashboard y
sensores/rendimiento no se modificaron; comparten la navegación corregida.

CPU separa perfiles, monitorización, persistencia y desbloqueo de núcleos.
GPU separa perfiles/rango, servicio/compatibilidad, voltaje y monitorización.
CU separa enrutamiento, registros y persistencia. Estas secciones y Ajustes
adicionales utilizan formularios verticales en vez de columnas de tarjetas.

`F2` ofrece todas las secciones y `F3` todas las pestañas, aunque no quepan
en la pantalla. Tab/Shift+Tab recorre acciones habilitadas y revela su fila;
F6 cambia de panel, Esc vuelve a navegación y Ctrl+L redibuja. Las flechas de
un campo o una tabla no cambian accidentalmente a otra tarea. La barra lateral
acompaña la selección en terminales bajos. Se utiliza entrada Unicode de curses.

La consola se muestra inmediatamente y confirma sus actualizaciones con
`noutrefresh`/`doupdate`, incluyendo stdout, stderr y resultados de texto.
Los procesos tienen su propia PTY sin `preexec_fn` desde el proceso con hilos.
Se conserva la cancelación, el desplazamiento, el registro y el redimensionado.

La autorización Polkit del TUI necesita su agente de terminal registrado.
Un ContextVar impide que las lecturas de fondo hereden la autorización del
trabajo o recurran al agente gráfico del escritorio. Los procesos de consola
no heredan DISPLAY, WAYLAND_DISPLAY ni programas askpass gráficos.

Acceso remoto se agregó exclusivamente al menú del TUI: información inicialmente
oculta, vencimiento de visibilidad a cinco minutos, bloqueo manual, direcciones,
clave, inicio/parada web, configuración de red, dispositivos, permisos y duración
de sesiones. SSH tiene controles separados para iniciar/detener y habilitar/
deshabilitar al arrancar, usando systemd u OpenRC. No se reintrodujo SSH en el
dashboard. Un init o servidor no disponible deshabilita las acciones.

Las operaciones CPU/GPU/CU rechazadas conservan la selección pendiente y no se
registran como aplicadas. También se agregó recuperación de dependencias de
fuente mediante Portage en el instalador local.

## Pruebas realizadas

- 155 pruebas dedicadas a TUI, autorización y su instalación: aprobadas.
- 4.133 rutas de acciones y menús, en 18 escenarios de familia/backend/estado,
  con los cambios del sistema sustituidos por dobles de prueba.
- 571 pruebas adicionales de empaquetado, web, calidad y acceso remoto:
  aprobadas; dos omitidas según sus requisitos de entorno.
- 144 pruebas TUI en cada uno de los 14 perfiles de contenedor siguientes.
  Cada perfil instala desde fuente, comprueba el rechazo de ejecución sin TTY,
  ejecuta la batería y desinstala. Hay recorridos reales de curses en PTY con
  TERM=linux y xterm-256color, entrada por teclado, redimensionado y salida normal.
- Disco y red tienen pruebas de muestras/gráficas con valores conocidos, junto
  a CPU, GPU, VRAM y RAM. F3 permite llegar a esas pestañas aunque estén fuera
  de la parte visible de la barra. No se rediseñó el apartado de sensores.

| Perfil | Python observado | Resultado | Alcance concreto |
| --- | --- | --- | --- |
| CachyOS | 3.14.8 | 144 aprobadas | Imagen CachyOS y paquetes de sus repositorios |
| Bazzite 44 | 3.14.8 | 144 aprobadas | Imagen oficial 44.20261026; prefijo escribible de contenedor |
| Arch Linux | 3.14.8 | 144 aprobadas | Imagen base y paquetes Arch |
| Manjaro | 3.14.7 | 144 aprobadas | Imagen Manjaro y paquetes de sus repositorios |
| Kubuntu 24.04 | 3.12.3 | 144 aprobadas | Base oficial Ubuntu y metapaquete kubuntu-desktop real |
| Xubuntu 24.04 | 3.12.3 | 144 aprobadas | Base oficial Ubuntu y metapaquete xubuntu-desktop real |
| Lubuntu 24.04 | 3.12.3 | 144 aprobadas | Base oficial Ubuntu y metapaquete lubuntu-desktop real |
| Artix/OpenRC | 3.14.8 | 144 aprobadas | Imagen base-openrc |
| Alpine/OpenRC | 3.14.10 | 144 aprobadas | Imagen Alpine; OpenRC instalado por apk |
| Gentoo/OpenRC | 3.14.7 | 144 aprobadas | Stage3/OpenRC; psutil y herramientas de prueba en venv |
| Debian | 3.13.5 | 144 aprobadas | Imagen estable y paquetes Debian |
| Kali | 3.14.8 | 144 aprobadas | Imagen kali-rolling y repositorios Kali |
| Parrot | 3.13.5 | 144 aprobadas | Imagen parrotsec/core y repositorios Parrot |
| Devuan | 3.13.5 | 144 aprobadas | Imagen estable y repositorios Devuan |

Los IDs y digests de las imágenes, versiones y resultados están en
[`evidence-2026-10-31.json`](../scripts/qa/tui/evidence-2026-10-31.json).
Los diez ángulos de revisión están enumerados en
[`scripts/qa/tui/REVIEW.md`](../scripts/qa/tui/REVIEW.md).

También se reconstruyeron DEB, RPM, Arch y tarball. El DEB y el RPM se
reinstalaron con apt/dnf y sus lanzadores TUI abrieron y cerraron una PTY como
usuario normal. Los archivos siguen usando la versión de desarrollo 1.21.4.

## Límites de la evidencia

Los contenedores comparten el kernel del anfitrión. No certifican un arranque
completo de las variantes Ubuntu, OpenRC, systemd ni el despliegue inmutable de
Bazzite. La imagen OCI de Bazzite no tiene `/var` preparado como un sistema
arrancado; su prueba utiliza un prefijo en `/tmp`. Gentoo utiliza un venv de
prueba y omite instalar dependencias del sistema durante su instalación de
fuente: esta ejecución no certifica una transacción real de Portage.

Las escrituras de voltajes, CU, firmware, reinicios, montaje de dispositivos,
activación efectiva de SSH y autenticación con credenciales reales no se
realizan sobre la placa anfitriona. Sus decisiones, argumentos, confirmaciones,
resultados y fallos se comprueban con dobles de prueba. Los protocolos de
systemd/OpenRC se comprueban por separado; una sesión PAM/Polkit real necesita
validación en el sistema arrancado. Esto es una batería de software, no una
certificación de estabilidad de overclock o compatibilidad de cada kernel.

No se afirma que la suite completa del proyecto esté libre de incidencias
anteriores ajenas a esta revisión. Los resultados anteriores corresponden a
los grupos ejecutados y a los registros de esta revisión.

## Reproducción

```bash
python3 scripts/qa/tui/run-matrix.py --list
python3 scripts/qa/tui/run-matrix.py --allow-network --pull --profile alpine
python3 scripts/qa/tui/run-matrix.py --allow-network --pull
```

El ejecutor requiere Podman sin root, monta el repositorio en solo lectura y
no publica puertos ni monta dispositivos del anfitrión. `--prepared` permite
reutilizar las imágenes locales de prueba. Los registros y results.json se
guardan en `~/.cache/bc250-tui-matrix`, o en el destino de `--output`.

Fuentes de imágenes: [CachyOS](https://github.com/CachyOS/docker),
[Bazzite](https://github.com/ublue-os/bazzite),
[Manjaro](https://github.com/manjaro/manjaro-docker),
[Gentoo](https://github.com/gentoo/gentoo-docker-images),
[Artix](https://hub.docker.com/r/artixlinux/artixlinux),
[Parrot](https://www.parrotsec.org/docs/containers/parrot-on-docker/),
[Devuan](https://hub.docker.com/r/devuan/devuan).
