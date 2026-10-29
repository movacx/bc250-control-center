# Auditoría de la TUI (modo terminal)

Rama `feature/bc250-tui`. Probada en una BC-250 real (Bazzite) a 158x43 (≈1920x1080), 120x35 y 80x24, con `TERM=xterm-256color` y `TERM=linux`.

## Diseño visual

| Hallazgo | Cambio |
| --- | --- |
| Encabezados de dos filas, barras de bloques que se juntaban en filas seguidas, etiquetas cortadas | Encabezado de una fila; barra = línea gruesa `━` del color de la lectura sobre una fina `─` (`=` sobre `-` en TTY); columnas de etiqueta y valor comunes |
| Barras sin criterio: unas lecturas con barra y otras no | Regla única: barra solo si la magnitud tiene máximo conocido (temperatura, porcentaje, memoria usada/total); relojes, potencia, voltaje y nombres son valores |
| Panel: Refrigeración debajo de Procesador a 1920 px; filas más anchas que su tarjeta | Rejilla adaptativa: 3 tarjetas a ≥155 columnas, 2 a ~120, 1 a 80; columnas compartidas entre tarjetas y cada fila recortada a su ancho |
| Tarjetas planas | Grupos como en escritorio (TEMPERATURA, ACTIVIDAD, CONSUMO, RELOJES, MEMORIA, ESTADO, VENTILADOR, UNIDAD M.2, BIOS) con aire uniforme |
| Acciones indistinguibles del texto («Actualizar · Temperatura…») | Botón `[ Acción ]` en color de acento; opciones `( )`/`[x]`; submenús con `›`; estado en una fila «Estado» |
| Flechas ▲▼ sueltas | Barra de desplazamiento con indicador proporcional |
| Sidebar sin grupos y en otro orden | Grupos y orden de escritorio; telemetría GPU/CPU en la barra de título |

## Uso

| Hallazgo | Cambio |
| --- | --- |
| «Preparar dependencias» y otros flujos abrían una terminal externa o suspendían la TUI | Consola integrada: progreso en vivo, contraseña en el panel, Ctrl+C, estado final, duración, ruta del log; Enter/Esc cierra, `r` reporta si falló |
| Polkit abría la ventana de KDE (y en TTY no había agente) | `pkttyagent` registrado solo para el proceso de la TUI durante cada trabajo: Polkit pregunta en el panel |
| El cursor saltaba fuera de pantalla en páginas largas | Las flechas desplazan; Enter nunca actúa sobre algo no visible |
| Atajos fijos, sin búsqueda ni ratón | Pie de atajos según el foco; `/` busca; 1-9, 0 y `,` desde cualquier panel; ratón opcional |
| Faltaban actualizaciones y reporte de problemas | Configuración › Acerca de: buscar e instalar versión (plan de escritorio), reportar problema o idea |
| Textos del flujo en inglés | `terminal_plan.set_translator(tr)`, como escritorio |

## Ingeniería

| Hallazgo | Cambio |
| --- | --- |
| Causa de la terminal externa: solo se sustituía el lanzador de un repositorio | Se registra `set_embedded_terminal_launcher` (el mismo enganche que la consola de escritorio); se borró `inline_terminal.py` y la suspensión de curses |
| Parser ANSI propio duplicado | `TerminalScreen` y `TranscriptLog` de escritorio (sin Qt; el paquete de consola carga Qt de forma diferida) |
| E/S en el hilo de dibujo; repintado de 5000 líneas cada 200 ms | Lecturas en el poller; la consola convierte solo las filas visibles |
| CPU en reposo 3,07 % (≈6 procesos/s: busctl, systemctl, pacman, git) | Cadencias por dato (ventiladores 3 s, daemon/CU 15 s, herramientas 60 s; `r` lo fuerza): **2,75 %** de un núcleo en el panel, 2,33 % en Ventiladores |
| Código muerto (`field_or_dash`, `_policy`, `Choice.key/columns`, `Grid.tones`, constantes sin uso) | Eliminado |

## Garantías verificadas

- Ninguna acción sale de la consola: `tests/tui/test_no_action_leaves_the_console.py` pulsa todas las acciones de todas las páginas y pestañas y falla si el servicio se llama fuera de `ui.run`, si se crea un proceso o si la TUI importa `subprocess` fuera de `console.py`.
- Prueba real: el flujo de dependencias en modo plan (`bc250-install-system-deps.sh --mode plan`, sin cambios) lanzado por `TerminalRepository._abrir_terminal` desde la pantalla curses: corre en el panel, en español, con log, y 0 intentos de terminal externa.
- Navegación completa por teclado en las 11 secciones (↓, AvPág, Inicio, ←/→, `[`/`]`, Esc) y redimensionado en vivo 158→120→80→158 sin errores en `tui.log`.

## Tamaño (`frontends/tui/`, líneas)

No existe en `desarrollo/bc250-control-center`. Desde el primer diseño auditado (`442b413`): 3780 → 4088. El aumento es funcionalidad nueva: `support.py` (+123, actualizaciones y reporte), `console.py` (+82, emulador, log y agente Polkit) y `screen.py` (+102, ratón, búsqueda, desplazamiento y panel de consola). Las páginas bajaron (`fans` −19, `extras` −15, `dashboard` −8).

## Distribuciones

La TUI no añade dependencias: `curses` es de la biblioteca estándar y `psutil` ya lo necesitaba la app. `scripts/install-tui.sh` instala solo lo que falte con dnf, rpm-ostree (Bazzite), apt (Debian/Ubuntu/Mint, más pkexec/jq), pacman (Arch/CachyOS; en SteamOS desbloquea y vuelve a bloquear la raíz), zypper (con `python3-curses`) o apk. Probado en un contenedor limpio de Fedora 44 con instalación real de dependencias. Sin imágenes locales de Debian, Ubuntu, Arch ni Alpine: esas ramas se revisaron a mano, no se ejecutaron.

## Ronda: CPU, GPU, Compute Units y Ajustes adicionales como en escritorio

| Hallazgo | Cambio |
| --- | --- |
| CPU, GPU y CU eran listas largas de filas, sin parecido con escritorio | Motor común en `content.py`/`layout.py`: `Panel` (tarjeta con título, insignia, botón de cabecera y zona de riesgo roja), `Tiles` (mosaicos; perfil seleccionable con «Editar»), `Buttons` (fila repartida, primario relleno, peligro en rojo; uno por fila en móvil), `Split` (columna izquierda/derecha, apilado bajo 110 columnas), `Slider` (carril de rango con paradas, rojo pasado 2000 MHz) y `Legend` |
| Una fila solo podía tener un elemento seleccionable | `Row.owners`: cada tramo sabe de qué botón es; toques y flechas ←→ llegan a botones lado a lado; las celdas de CU se tocan una a una (`Row.cells`, `Pad.place`) |
| Ajustes adicionales tenía pestaña Decky y listas de acciones sueltas | Pestañas de escritorio (Compatibilidad · Escalado · Memoria y swap · Controladores); grupos Sistema / Governor / Kernel y gráficos / Vídeo con estado de color, tarjetas «Reinicio requerido», y Controladores con Red, Impresión y externos. Decky ya estaba en el Panel; la telemetría pasó a Configuración, como en escritorio |
| Pantallas y diálogos cargados de texto | Sin subtítulos ni textos de ayuda en mosaicos; CU sin telemetría duplicada; los diálogos llevan la acción como título y dos botones (Sí en rojo si es peligroso), sin pie de teclas |
