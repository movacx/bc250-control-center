# BC250 Control Center — contexto del proyecto

Documento de traspaso. Si abrís una sesión nueva, empezá por aquí: dice qué es
el proyecto, cómo está organizado, qué reglas no se pueden romper y qué queda
por hacer.

> Estado en el momento de escribirlo: versión `1.19.0`, rama
> `fix/cyan-fan-upstream-audit`, último commit `1dd7f37`.
> **3080 tests pasan, `ruff` limpio.** Nada subido a GitHub: todo el trabajo
> está en el árbol de trabajo, sin commitear.

---

## 1. Qué es

Una aplicación de escritorio en **PyQt6** para controlar el hardware de la
**AMD BC-250** — la placa de minería con APU derivada de la PS5 que la gente
reutiliza como equipo de juego. El BC-250 no tiene firmware ni herramientas de
fábrica pensadas para eso, así que todo lo que hace la aplicación son escrituras
directas a `sysfs`, D-Bus y archivos de configuración, a través de *helpers*
privilegiados.

**Qué controla:**

| Área | Qué hace |
|---|---|
| GPU | Rango de frecuencia y voltaje vía el gobernador Cyan Skillfish (D-Bus) o el gobernador Oberon (YAML) |
| CPU | Overclock/undervolt SMU: frecuencia, escala de voltaje, límite térmico |
| Compute Units | Habilita pares de WGP más allá de los 24 CU de fábrica (hasta 40) |
| Ventiladores | PWM directo sobre el chip NCT, presets y curva por temperatura |
| Sistema | Swap/zram/TTM, ACPI, mitigaciones de CPU, drivers, procesos |

**Dos frentes de interfaz:**

1. **Escritorio** (PyQt6) — siete pantallas, 30 idiomas, navegación por mando
2. **Decky Loader** ("BC250 Quick Access") — panel para el Modo Juego de
   SteamOS/Bazzite, en TypeScript + un backend Python

---

## 2. Arquitectura

```
src/bc250cc/           el núcleo, sin Qt
  domain/              reglas puras (límites, perfiles, comparación de versiones)
  application/         casos de uso; NO puede importar infrastructure
  infrastructure/      sysfs, D-Bus, subprocesos, archivos
  platform/            detección de distribución y de sistema de init
  shared/              contrato, catálogo de errores, versión

frontends/desktop/     la aplicación Qt
  pages/               las siete pantallas
  components/          widgets reutilizables
  console/             terminal integrada (PTY real, intérprete VT propio)
  core/                estado, preferencias, mando, enlaces externos
  i18n/locales/        30 catálogos JSON
  theme/               paleta y hojas de estilo

privileged/
  helpers/             12 helpers root, invocados por polkit/pkexec
  lib/                 módulos que los helpers cargan por ruta absoluta
  policies/            la política de polkit

integrations/decky/bc250-quick-access/   el plugin de Modo Juego
packaging/             constructores rpm/deb/pacman + scripts por distribución
scripts/               install-local.sh, uninstall-local.sh, entrypoints
tests/                 227 archivos de test
```

**Tamaño:** ~250 archivos Python, ~92 000 líneas.

### Las tres fronteras de proceso

Esto explica la mayoría de las decisiones raras del proyecto:

1. **El escritorio** — puede importar `bc250cc` normalmente.
2. **Los helpers privilegiados** — corren con `python3 -I` (modo aislado), que
   borra su propio directorio de `sys.path` e ignora `PYTHONPATH`. **No pueden
   importar `bc250cc`.** Cargan módulos por ruta absoluta, verificando que
   sean de root antes.
3. **El backend de Decky** — corre dentro de Decky Loader con solo los archivos
   que su instalador coloca (una lista blanca de 8).

Por eso existe `src/bc250cc/shared/contract.py`: un solo lugar con los números
que los tres procesos deben compartir, del que se **genera** una copia para los
procesos root.

---

## 3. Reglas que no se pueden romper

Si tocás el código, estas son las que muerden:

**Los 12 helpers son root.** Todos empiezan con `#!/usr/bin/python3 -I`, todos
comprueban `geteuid`, todos rechazan a un usuario normal. Hay un test
parametrizado que lo verifica **ejecutándolos**, no leyéndolos.

**`HELPER_PROTOCOL` debe ser un literal entero.** El escritorio lo lee del
archivo *instalado* con un análisis AST, sin importarlo, para detectar que el
helper y el plugin vienen de instalaciones distintas. Si lo convertís en una
expresión, ese mecanismo se rompe en silencio.

**El contrato se carga dentro de `main()`, nunca a nivel de módulo.** Decky
Loader importa `main.py`; una excepción ahí significa que el panel **no aparece
y nada explica por qué**. Un test lo verifica por AST.

**Marcador antes que número.** Los fallos de los helpers se diagnostican por su
marcador `PREFIX:`, y el número de salida es solo respaldo. 31 números están
compartidos entre helpers; el marcador es lo que desambigua.

**Una cadena visible = 30 traducciones.** Hay un test que recorre el árbol de
widgets y exige que todo literal visible esté en `en.json`, y otro que exige
que los 30 catálogos tengan exactamente el mismo juego de claves.

**`page.layout` es un atributo, no el método de Qt.** Varias páginas lo
sombrean. `page.layout()` explota.

**`qtbot.addWidget` guarda una referencia débil.** Si un test crea una página y
arranca sus refrescos, hay que apagarlos en el desmontaje o un callback
diferido alcanza widgets ya destruidos — y falla un test *distinto*.

**`isHidden()` ≠ `not isVisible()`.** Un hijo de un padre no mostrado no es
visible aunque esté configurado para estarlo. En tests usá `isHidden()`.

---

## 4. Qué se trabajó en esta sesión

### Terminal integrada
La barra de input se muestra **solo con mando**. Con teclado se escribe directo
en la rejilla, como una terminal normal.

El hallazgo que cambió el diseño: `TerminalView` **ya era** una ruta de entrada
completa (flechas, Ctrl+C, teclas de función, DECCKM, pegado con corchetes). La
barra nunca hizo falta para escribir; se había agregado porque un prompt de
contraseña no muestra nada y parecía una terminal colgada. Así que no había que
construir nada: había que dejar de tapar lo que ya funcionaba.

Soporta enchufar/desenchufar el mando a mitad de un workflow. Sin mando, el
estado "Contraseña de administrador" aparece en la cabecera.

### Rendimiento
Varias pantallas destruían y recreaban su contenido en cada refresco.

| Sitio | Antes | Cada |
|---|---|---|
| `pages/processes.py` `_render_table` | ~600-1000 widgets | 5 s **y cada tecla del buscador** |
| `gpu_governor_view.py` `SafePointTable` | 17 filas, ~100 restyles | 3 s |
| `pages/drivers.py` `_apply_snapshot` | reconstruía las filas | 2 s |

**Medido tras el cambio: 0 widgets construidos y 0 `setStyleSheet` en diez ticks
en estado estable.**

También: con mando conectado, cada `QEvent.ChildAdded` disparaba un recorrido de
**toda** la aplicación (`findChildren(QWidget)` sobre cada ventana). Ahora se
acota al subárbol que cambió.

### Seguridad
**Root sin autenticar en Modo Juego, alcanzable desde el escritorio.** El helper
`bc250-steamos-game-helper` corre con `allow_active=yes` (sin contraseña, a
propósito: gamescope suele no poder mostrar el diálogo de polkit). Su única
defensa era una heurística donde `SteamClientLaunch` contaba como prueba de Modo
Juego — y Steam pone esa variable en **cualquier** juego lanzado desde Modo
Escritorio. Resultado: lanzar un juego, apuntar `--origin-pid` a él, y tener root
sin contraseña sobre ventiladores, voltaje GPU, configuración del gobernador y
OC de CPU.

Cerrado en dos niveles: solo señales exclusivas de gamescope anulan el veto, y
las acciones que **persisten** exigen gamescope probado, no un puntaje.

Además: `bc250-fan-pwm-helper` no comprobaba identidad BC-250 (aceptaba
cualquier hwmon `nct*`), y `governor_toml.py` reescribía `/etc` sin verificar
dueño root.

### Diagnóstico de errores
60 → 38 fallos mal clasificados. `CPU_BACKEND_UNTRUSTED` ("el helper de CPU
instalado no es seguro") se mostraba como "falta un programa requerido", que
manda al usuario a preparar dependencias en vez de a reparar la instalación.

Se arregló **registrando marcadores que ya estaban en los mensajes** — coste de
traducción cero.

### Distribuciones e init
- OpenRC nunca ejecutaba el preflight de Cyan (systemd sí). Agregado `start_pre`.
- `install-fan-persistence.sh` escribía una unidad de systemd **a ciegas** en
  runit/s6/dinit. Ahora hay tercera rama.
- La detección de init estaba duplicada cinco veces en bash embebido, en un
  archivo que ya importaba `detect_init_manager`.
- Borrado `platform/distro/identity.py`: un segundo clasificador muerto que
  devolvía `family == "openrc"`, valor que ninguna tabla del proyecto conoce.

### Contrato único Decky ↔ escritorio
**El bug grande:** el helper publicaba el estado de CU con protocolo `13` y el
escritorio exigía `9`, descartando cada instantánea **sin una línea de log** y
cayendo a una caché vieja. La sincronización que el README promete llevaba rota
desde el protocolo 10.

Se creó `src/bc250cc/shared/contract.py` + un generador
(`scripts/development/generate_contract.py`) que produce dos artefactos
comiteados:
- `privileged/lib/bc250_contract.py` — para los dos procesos root
- `integrations/decky/.../src/generated/error_catalog.json` — para el panel

Otros arreglos de la misma familia:
- Piso de CPU en Modo Juego: 3500 → **3100**. Un perfil guardado a 3200 en el
  escritorio se redondeaba **hacia arriba** y se reaplicaba a 3500.
- Perfil Benchmark de Oberon unificado en `(1000, 2000)`, con `(2000, 2000)`
  tolerado en lectura para no dejar varado a nadie.
- Causa raíz de "dos botones idénticos": el generador de perfiles **recortaba**
  el perfil al rango permitido en vez de excluirlo.
- `diagnoseError` del panel ya no adivina por subcadenas: usa el catálogo
  generado. Cerradas 8 discrepancias de 32 marcadores.
- Versión del plugin: `0.1.0` → `1.19.0`.

### Icono y aviso de actualización
- Icono nuevo (isométrico) en nueve tallas, 16 a 1024.
- **Módulo de actualización**: `release_check.py` lee el `VERSION` publicado en
  GitHub. Es la **única** conexión de red que la aplicación hace por sí misma;
  todo lo demás vive en scripts que el usuario lanza. Por eso: HTTPS fijo,
  4 s de tiempo límite, cuerpo acotado a 64 bytes, nada identificatorio, sin
  errores visibles, con caché y con interruptor (`settings/update_check`).
- Valida **en cada entrada al dashboard**.
- `install_source.py` detecta cómo se instaló la copia: AUR → sugiere el
  comando del ayudante (`paru -Syu ...`); paquetería o script → al último
  release de GitHub. Solo consultas de lectura: `pacman -Qoq`, `rpm -qf`,
  `dpkg-query -S`.
- Burbuja con flecha apuntando a la insignia, que se voltea arriba si no hay
  sitio abajo.

### Iconos que no se actualizaban
**El instalador nunca refrescaba la caché de iconos; el desinstalador sí.** Eso
hacía que reinstalar fuera el único caso que fallaba: desinstalar reconstruía la
caché *después* de borrar los iconos, instalar escribía los nuevos sin avisar a
nadie, y el lanzador seguía leyendo una caché más vieja que los archivos.

### `run.sh`
Hacía `exec` directo a Python, así que un equipo sin PyQt6 recibía un
`ImportError` con nombre de *módulo*, no de paquete. Ahora nombra el comando
correcto por distribución (`rpm-ostree`, `dnf`, `apt-get`, `pacman`, `apk`,
`emerge`).

---

## 5. Tests ratchet añadidos

Todos con **descubrimiento mecánico**: un cuarto consumidor hereda las
comprobaciones en vez de depender de que alguien se acuerde.

| Archivo | Qué fija |
|---|---|
| `tests/packaging/test_one_contract_for_every_process.py` | Los artefactos generados coinciden con su fuente; el contrato no importa nada fuera de la stdlib; cada consumidor estampa su revisión y no carga a nivel de módulo |
| `tests/packaging/test_game_mode_root_is_not_reachable_from_the_desktop.py` | El bypass de `SteamClientLaunch`; las acciones persistentes exigen gamescope probado |
| `tests/services/test_exit_status_means_one_thing.py` | Un número ambiguo nunca decide; todo marcador impreso está registrado |
| `tests/desktop/architecture/test_refreshes_update_instead_of_rebuild.py` | Los widgets sobreviven a un refresco (identidad de objeto) |
| `tests/desktop/architecture/test_nothing_unreachable_ships.py` | Clases y métodos sin llamador; métodos definidos dos veces |
| `tests/quick_access/test_the_panel_has_no_bounds_of_its_own.py` | El panel no declara ningún límite propio; el bundle no está obsoleto |
| `tests/services/test_install_source.py` | Las consultas son de solo lectura (por AST, no por texto) |
| `tests/packaging/test_installation_paths_agree.py` | Instalador y desinstalador cubren lo mismo; las cachés se refrescan |

---

## 6. Pendiente

### Alta prioridad
- [ ] **Error de OC de CPU en Bazzite.** Lo reportaste pero no quedó el código
      de error. Hay que reproducirlo y capturarlo.
- [ ] **Probar en hardware lo que solo se verificó en test**: mando de verdad,
      Modo Juego real con gamescope, prompts de polkit en las acciones
      partidas, CU desde Modo Juego → escritorio.
- [ ] **Probar en otras distribuciones.** Fase 3 está hecha y validada
      sintácticamente, pero ninguna corrió en vivo salvo CachyOS.

### Media
- [ ] **Tres marcadores mal diagnosticados**: `GAME_MODE_CONTEXT`,
      `CU_CONTEXT`, `DAEMON_CONTEXT` salen como "Linux rechazó el acceso a un
      archivo". Cada uno se usa para dos cosas distintas (plataforma incorrecta
      *y* autorización), así que separarlos necesita una entrada de catálogo
      nueva: **3 frases × 30 idiomas**. Está en una lista permitida explícita
      con la razón escrita, y un test avisa si queda obsoleta.
- [ ] **11 funciones completas sin botón** (`UNWIRED_FEATURES` en
      `tests/desktop/architecture/test_nothing_unreachable_ships.py`):
      import/export de perfiles, página "BC250 System Health", preview de
      política de memoria, `test_scale_live` de CPU. Cada una es cablear o
      borrar. Recomendación: **cablear `_build_health_page`** — valida
      herramientas, helpers, servicios y configuración por distribución, que es
      justo lo que sirve para probar en otras distros.

### Baja
- [ ] **Migración completa de la lista de archivos del plugin Decky.** El plan
      original proponía borrar la copia vendida de `profiles.py` y bajar de 8
      archivos a 4. Se tomó otro camino: sincronizarla byte a byte con el canon
      y fijarla con un test. Cierra la misma divergencia con mucho menos riesgo
      — la ruta descartada tenía una trampa donde
      `quick_access_inventory.plugin_safe` habría reportado "no listo" en toda
      máquina correctamente actualizada.
- [ ] **`/ultrareview` no se puede lanzar** sobre este diff (208 archivos,
      25 777 líneas; el límite son 8 000). Hay que acotarlo con una base más
      cercana o partir el cambio.
- [ ] **Nada está commiteado.** Todo el trabajo vive en el árbol de trabajo.

### Notas sobre el aviso de actualización
La ventana de caché es de **15 minutos** (`release_check.CACHE_SECONDS`). Empezó
siendo de 6 horas y eso hacía que el aviso fuera indistinguible de estar
clavado: publicabas una versión, abrías el dashboard y no pasaba nada en toda
la tarde. Para probarlo a mano, borrá la caché:

```bash
rm -f ~/.cache/bc250-control-center/release-check.json
```

---

## 7. Cómo verificar

```bash
# suite completa + lint
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/ frontends/ tests/ privileged/

# los artefactos generados están al día
.venv/bin/python scripts/development/generate_contract.py --check

# los 12 helpers rechazan a un usuario normal
for h in privileged/helpers/*; do [ -f "$h" ] && /usr/bin/python3 -I "$h" </dev/null; done

# reinstalar (necesario tras cambiar iconos o el contrato)
./scripts/install-local.sh
```

El intérprete es `.venv/bin/python`; **no hay `pytest` ni `ruff` en el PATH**.

---

## 8. Detalles que cuestan tiempo si no se saben

- El **gestor de paquetes** responde por *archivo*, no por directorio:
  `pacman -Qoq /usr/bin` devuelve cientos de nombres.
- `QPolygonF` exige `QPointF`. Pasarle `QPoint` lanza dentro de `paintEvent`,
  y PyQt6 convierte una excepción en un virtual reimplementado en `qFatal()` —
  **aborta el proceso entero**, sin traza útil.
- `gtk-update-icon-cache` necesita `-t` en un `hicolor` de usuario, porque no
  hay `index.theme`. Sin eso se niega y la caché vieja sobrevive en silencio.
- El paquete de AUR es `bc250-control-center-git`; el de pacman local es
  `bc250-control-center`. Ambos son foráneos, así que el **nombre** es lo que
  los distingue.
- `runpy.run_path` devuelve una **copia** del espacio de nombres; las funciones
  conservan sus propios globals. Parchear el diccionario devuelto no cambia
  nada de lo que el helper realmente llama — hay que parchear `__globals__`.
