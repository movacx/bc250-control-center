# Auditoría: SteamOS, VA-API, CEC y repositorios (14 de octubre de 2026)

Estado del repositorio al escribir esto: `main` en `789a4be`, con los cambios de esta auditoría sin commit.
Todo lo que dice «verificado» se probó en la BC-250 de desarrollo (Manjaro). Lo que dice «sin verificar»
no se pudo probar sin el hardware o la distribución en cuestión (SteamOS, un adaptador CEC, una TV).

## 1. Qué se hizo en esta pasada

| Cambio | Dónde | Estado |
|---|---|---|
| Las apps Flatpak (GPU Screen Recorder, OBS, Steam) ya pueden usar el driver VA-API | `scripts/system/bc250-vaapi-flatpak.py`, `vaapi_video.py`, tarjeta «Vídeo por hardware» | Verificado en un sandbox real de Flatpak |
| Ventana de control de la TV y del receptor: se abre en un control remoto dibujado y, tras un engranaje, la configuración con las dos automatizaciones | `accessories/hdmi_cec_control.py`, `accessories/hdmi_cec.py`, `pages/tv_control.py` | Pruebas con un busctl simulado; sin verificar con una TV |
| Buscador en la ventana de repositorios y ventana más compacta | `pages/settings.py`, `components/dialogs.py` | Verificado en captura |
| 49 textos nuevos traducidos a los 30 idiomas | `i18n/locales/*.json` | Traducciones mías, sin revisión nativa |

### 1.1 El caso de GPU Screen Recorder («H.264 no disponible»)

Reproducido y resuelto. La consulta que hace GPU Screen Recorder es `vaGetDisplayDRM` → `vaInitialize` →
`vaQueryConfigProfiles` → entrypoint `EncSlice`/`EncSliceLP` (fuente: `src/codec_query/vaapi.c` del proyecto).
Hice un programa de C con esa misma consulta:

- En el sistema, con `LIBVA_DRIVER_NAME=bc250`: H.264 y HEVC disponibles.
- Dentro de un sandbox de Flatpak (runtime 26.08) sin cambios: `radeonsi_drv_video.so init failed` → H.264 no disponible.
  Es exactamente lo que ve el usuario del Discord.
- Dentro del mismo sandbox con la anulación de usuario de Flatpak (acceso de solo lectura a
  `/var/lib/bc250-control-center/vaapi` más `LIBVA_DRIVER_NAME` y `LIBVA_DRIVERS_PATH`): H.264 y HEVC disponibles.
  Todas las librerías del driver (`libva`, `libvulkan`, `libdrm`, `libgomp`) resuelven dentro del runtime y los símbolos de glibc (máximo 2.38) también.

Lo que NO se verificó: que GPU Screen Recorder llegue a codificar de verdad con el driver (no está instalado aquí).
La consulta de capacidades sí pasa; si luego falla al grabar, sería otro problema (importación DMA-BUF, ver 2.3).

Cómo se aplica: se instala solo con el driver (sin root), o con el botón «Permitir apps Flatpak» para quien ya lo tenía instalado.
Se quita al desinstalar el driver. Solo toca sus propias líneas del archivo `~/.local/share/flatpak/overrides/global`.

Respuesta sugerida para el usuario de Discord:

> Eso pasa si GPU Screen Recorder es el Flatpak: va en un sandbox y no ve el driver, solo el radeonsi del runtime, que en la BC-250 no arranca.
> Con la versión nueva del Control Center, en Compatibilidad → Vídeo por hardware sale el botón «Permitir apps Flatpak»
> (o se aplica solo al reinstalar el driver). Reinicia GPU Screen Recorder después y H.264 debería aparecer como disponible.
> Si usas la versión nativa, avísame, porque entonces sería que la sesión no tiene `LIBVA_DRIVER_NAME=bc250` (hace falta cerrar sesión tras instalar).

## 2. simpmix/bc250-encoding-decoding-fix

- Versión integrada: `v0.5.2`, commit `b8de980`, que es idéntico a `main` hoy (último push 3 de octubre). No hay nada nuevo que integrar.
- Última versión publicada: `v0.5.2` (30 de septiembre). Un único issue abierto (#1, «Need contributors»); los 18 anteriores están cerrados.
- Lo que ya hace bien el Control Center: construye en un contenedor Fedora, sin libx264, verifica que arranque por libva y ofrezca H.264 y HEVC
  antes de activarlo, no toca `radeonsi_drv_video.so` ni usa la unidad de arranque de upstream (que se colgó en una placa).
- Huecos, por prioridad:
  1. **Driver de 32 bits** (Steam Link / Remote Play). Es un cliente de 32 bits y cae a software sin él (issue #8 de upstream).
     `keyboardspecialist/bc250-steamos` v0.28.14 lo ofrece como compañero opcional. Aquí no existe. Requiere en SteamOS instalar
     `lib32-libva`, `lib32-libdrm`, `lib32-vulkan-icd-loader`, `lib32-vulkan-radeon`, `lib32-glibc` y `lib32-gcc-libs`, y la construcción
     i386 en el contenedor. No se hizo a ciegas: es un cambio con privilegios sobre SteamOS que no se puede probar aquí.
  2. **Presets de Sunshine/Moonlight y WiVRn** (`tools/sunshine_preset`, `tools/wivrn_preset`): el Control Center no los aplica.
  3. **Variables de afinación** (`BC250_H264_BACKEND`, `BC250_X264_CRF`, `BC250_FAST_MODE`, `BC250_HEVC_SLICES`, `BC250_QUEUE_PRIORITY`):
     no hay interfaz. `BC250_H264_BACKEND` (x264 en la CPU o cómputo en la GPU) es la que más cambia el comportamiento.
  4. `tools/bc250_diagnose.sh` (diagnóstico completo, incluye permisos de `renderD128`): se podría enlazar desde el botón «Probar».

## 3. HDMI-CEC: ¿lo gestiona el Control Center?

Respuesta corta: **sí, la instalación y la configuración; no el uso del día a día**, hasta ahora.

| Función | Antes | Ahora |
|---|---|---|
| Instalar/configurar cecd (nombre «BC-250» en la TV; construirlo donde no viene) | Sí | Sí |
| Detectar adaptador y kernel sin CEC | Sí | Sí |
| Probar: despertar la TV | Sí (terminal, que al fallar daba un diagnóstico genérico) | Sí (ventana, con respuesta clara) |
| Apagar la TV, cambiar la entrada a este equipo | No | Sí |
| Despertar y poner en espera el receptor, volumen, silencio | No | Sí |
| Estado de la TV y el receptor, dirección física | No | Sí |
| Encender la TV al iniciar sesión (cecd solo lo hace al reanudar de suspensión) | No | Sí, opcional |
| Poner la TV en espera al apagar el equipo (cecd solo lo hace al suspender) | No | Sí, opcional |

Las dos automatizaciones son «educadas»: si hay otro dispositivo activo en una TV encendida, no le quitan la entrada. Se ejecutan:

- Encendido: servicio de usuario `bc250-control-center-cec-wake.service`.
- Apagado: unidad de sistema con `ExecStop` (solo en `poweroff`/`halt`, nunca en reinicio ni suspensión), 10 s de tiempo máximo, necesita `cec-ctl`.

Ambas se niegan a pisar las unidades equivalentes de `bc250-steamos` y solo borran lo que lleva su marca.

Código portado de `keyboardspecialist/bc250-steamos` (dominio público), cuyo autor comprobó las llamadas contra una TV y un receptor reales.

Sin verificar: todo el envío real (no hay adaptador CEC en esta máquina). Lo que sí se verificó es la sintaxis de todos los flujos con `bash -n`
y la lógica con un busctl simulado (direcciones lógicas, bytes de `System Audio Mode Request`, retroceso a la tecla de encendido, etc.).

Pendiente en CEC (visto en `bc250-cec.sh` y en `rpf16rj/bc250-steamos-real-toolkit`):

- **Receptor que sigue al equipo** (encender/apagar al arrancar, apagar, suspender y reanudar; hoy solo hay botones manuales).
- **Entregar la entrada a otro dispositivo** (`handoff`) y soltarla (`release`), y una vista de `scan` del árbol CEC.
- **Reparar el registro CEC** (`repair`) cuando el adaptador se queda sin dirección tras apagar la TV.
- **Mapa de teclas del mando de la TV** (OK→Enter, Atrás→Esc) para que funcione en la interfaz de gamepad de Steam (regla udev `71-bc250-cec-keys.rules`).
- **Arreglo DSC/HDMI 2.1 PCON** para 4K120 (kernel; es de `MastaG/linux-cachyos-bc250`, no de CEC pero afecta a quien use TV con adaptador CH7218).

## 4. Flujo de SteamOS: qué hay y qué falta

Frente a `keyboardspecialist/bc250-steamos` v0.32.0 (último push 9 de octubre):

| Componente del toolkit | En el Control Center |
|---|---|
| UMA (VRAM mínima) y límite TTM | Sí (`system_setup_vram.py`, `system_setup_ttm.py`) |
| Swap: zram, zswap + disco (swapfile en `/home`) | Sí (`system_setup_memory.py`), con lista de conservación |
| ACPI, mitigaciones, `nosmt` | Sí; `nosmt` solo como argumento de arranque, no el interruptor en caliente de SMT |
| Gobernador de GPU, voltaje, rango | Sí |
| Overclock de CPU (smu_oc) | Sí, con reintento si el SMU no responde a tiempo |
| 40 CU / gestor de CU en vivo; desbloqueo de núcleos | Sí |
| Módulo AMDGPU del kernel, Mesa/RADV con cómputo asíncrono | Sí (`steamos_amdgpu.py`, `steamos_graphics_runtime.py`) |
| Fan: NCT6687 | Sí |
| FSR4, OptiScaler, HelixSR 1.8.1 | Sí |
| VA-API 64 bits | Sí; ahora con acceso Flatpak |
| HDMI AC-3 y CEC | Sí; CEC ampliado |
| AIC8800 Wi-Fi/BT, temperatura de memoria GDDR6 | Sí |
| Plugin de Decky | Sí (`decky_quick_access.py`) |
| Reinstalación tras actualizar SteamOS | Sí (`steamos_rescue.py`) |
| **VA-API 32 bits** | **No** |
| **Perfil BC250 RADV R2 + Proton privado + vkd3d parcheado** | **No** |
| **BC-250 GE-Proton** (`MastaG`) | **No** |
| **CoolerControl** | No (el Control Center ya tiene su propio control de ventiladores) |
| **Interruptor de SMT en caliente y persistente** | Parcial |
| **Actualización automática del toolkit** | No aplica (el Control Center tiene la suya) |
| **Comprobación tras actualizar SteamOS** (qué componentes siguen en pie) | No: solo existe el reinstalador del propio programa |

Notas de SteamOS que conviene tener presentes:

- `/var` es una partición pequeña (unos 230 MB) que respalda el overlay de `/etc`. `rpf16rj` v1.10.2 añadió una comprobación temprana de
  espacio libre en `/var` (falla por debajo de 100 MB) porque pacman moría a medias. El Control Center pone el driver VA-API (unos pocos MB)
  en `/var/lib` y los swapfiles en `/home`, bien; pero ninguno de los flujos comprueba el espacio libre de `/var` antes de instalar.
- La lista de conservación por defecto de SteamOS (`/usr/lib/rauc/atomic-update-keep.conf`) ya conserva `/etc/systemd/system/*.service`;
  los archivos de `/etc/environment.d` y `/etc/profile.d` sí necesitan entrada propia (el driver VA-API y AC-3 ya la tienen).
- `rpf16rj` 1.10.2: unidades antiguas en `/etc/systemd/system/cyan-skillfish-governor-smu.service*` que tapaban la del paquete y
  entraban en bucle (203/EXEC). Conviene comprobar que el instalador del gobernador del Control Center limpia ese caso en SteamOS.

Lo que NO se pudo verificar: todo el flujo de SteamOS. Esta máquina es Manjaro.

## 5. Estado de los 39 repositorios de la ventana «Repositorios oficiales»

(La ventana dice 30 en algunos mensajes; son 39.)

### 5.1 Integrados con revisión fijada: qué ha cambiado desde la revisión

| Herramienta | Repositorio | Cambios desde la revisión fijada |
|---|---|---|
| Gobernador Cyan | `filippor/cyan-skillfish-governor` | +1 commit («add descriptive errors»); versión 0.4.14 publicada el 3 de octubre |
| bc250_smu_oc | `bc250-collective/bc250_smu_oc` | Ninguno |
| core unlock | `rw-r-r-0644/bc250-core-unlock` | +2, solo documentación (enlaces) |
| CU manager (estándar y SteamOS) | `WinnieLV`, `F5GO` | Ninguno (sin cambios desde julio) |
| AMDGPU de SteamOS | `keyboardspecialist/bc250-steamos` | +3 (HelixSR, zram y SMU); v0.32.0 |
| FSR4 (runtime) | `dmorazasanchez/bc250-fsr4` | +2, licencia MIT |
| FSR4 (cliente OptiScaler) | `daniel-h-0/bc250-fsr4-fork` | +2: **arreglo del cliente en Bazzite y Fedora Atomic** (1.0.7-bc250.4) y nombres de carpetas de juego (1.0.7-bc250.5) |
| HelixSR | `lonewolf0622/HelixSR` | +8; **1.9.0 experimental** subida a `main` el 13 de octubre sin publicarse como versión |
| VA-API | `simpmix/bc250-encoding-decoding-fix` | Ninguno |
| NCT6687 | `Fred78290/nct6687d` | +40, más voltajes específicos por placa; 70 issues abiertos |
| Oberon | `mothenjoyer69/oberon-governor` (GitLab) | No comprobado (sin API en esta sesión) |
| GFX1013 directo | `DryhoppedIPA/bc250-gfx1013-fix` | Ninguno |
| Temperatura GDDR6 | `pan-Rijovich/bc250-memory-temperature` | +3: **validación de entrada y tiempos de espera en el sondeo UMC**, volcado de registros al agotarse |
| Telemetría APU | `onlinermm/BC250-Telemetry` | Ninguno |

Candidatas a actualizar (previa revisión del diff, porque cada una lleva un SHA fijado y un archivo de confianza):
`fsr4_opticlient` (arregla Bazzite), `gddr6_memory_temp` (más robusto) y `cyan_smu` (mensajes de error).
No las toqué: cambiar un pin sin leer el diff y re-verificar el hash rompe la garantía del catálogo.

### 5.2 Referencias y no integrados

| Repositorio | Último push | Nota |
|---|---|---|
| `duggasco/bc250-40cu-unlock` | 24 de junio | **Archivado** y con 12 issues abiertos: el catálogo lo cita como proyecto vivo |
| `kenavru/BC-250` | 28 de noviembre de 2025 | Sin actividad en casi un año |
| `tmghd272/bc250-custom-bios-logo` | 25 de marzo | Sin actividad |
| `tmghd272/bc250-batocera-tools` | 24 de agosto | Referencia |
| `mendesrr/bc250-acpi-fix-updated-8c` | 3 de agosto | Referencia |
| `e-tho/bc250-acpi-fix` | 5 de octubre | **v1.1.1**: comprobar si hay algo nuevo respecto al ACPI integrado |
| `rpf16rj/bc250-steamos-real-toolkit` | 12 de octubre | **v1.10.3**: seguimiento de SteamOS beta (kernel 7.2.4); fuente de varias ideas de la sección 3 y 4 |
| `redbeard1083/bc250-toolkit` | 12 de octubre | Referencia activa |
| `62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images` | 13 de octubre | Imágenes diarias |
| `MastaG/linux-cachyos-bc250` | 13 de octubre | Activo; origen del DirectMesh 1.3.1 y de varios arreglos de pantalla |
| `Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script` | 4 de octubre | v0.5.0 |
| `fanoush/bc250_memcfg` | 11 de septiembre | v0.1 |
| `Hexxeh/bc250-efi-core-unlock` | 22 de septiembre | Referencia |
| `lonewolf0622/BC250-Native-Mesh-Shaders-` | 12 de septiembre | Referencia |
| `tri3gubki-ops/bc250-async-compute-bazzite` | 5 de septiembre | v0.2.4 |
| Impresión, Bluetooth, USB-WiFi (CUPS 2.4.20, PAPPL 1.4.12, BlueZ 5.87, etc.) | Activos | Solo referencias |

## 6. Issues y discusiones del proyecto

- **#23 (abierto) «Core Unlock Clarity»**: pide dejar claro en la interfaz que el desbloqueo de núcleos no es permanente
  (un apagado completo restaura los 6 núcleos). El texto del botón ya dice «A full power-off clears the change», pero no hay un aviso
  persistente ni la explicación de qué hacer si hay inestabilidad. El autor del issue se ofreció a abrir un PR; está sin hacer.
- **Discusión #9 (sin resolver)**: «Aborting because throttling was detected» al escalar la CPU automáticamente. Sin respuesta desde el 3 de octubre
  (se le preguntó la versión y la distribución). Hay un segundo usuario con el mismo síntoma en el log. Falta pedir temperatura y refrigeración.
- Issue #22 (cerrado): swap y mitigaciones en SteamOS. Resuelto con la sección de memoria.
- Issue #21 (cerrado): VA-API. Resuelto con esta integración; este caso de Flatpak es su continuación natural.
- Ningún PR abierto. Los dos del 25 y 26 se integraron y cerraron.

## 7. Segunda pasada (SteamOS): hecho y no hecho

Estudié el toolkit de `keyboardspecialist` en su versión v0.34.0 (14 de octubre) y lo comparé pieza a pieza.

### Hecho (con pruebas; nada de esto se ejecutó en SteamOS real)

| Qué | Dónde | Cómo se comprobó |
|---|---|---|
| **Driver VA-API de 32 bits** para Steam Remote Play y Steam Link (SteamOS, Arch, CachyOS, Manjaro). Botón «Añadir driver de 32 bits»; tras una actualización de SteamOS que quita las librerías, «Reparar driver de 32 bits» las trae sin recompilar | `vaapi_video.py`, `scripts/system/bc250-vaapi-probe.c`, tarjeta de vídeo | Compilado de verdad en el contenedor Fedora (ELF32, sin TEXTREL, glibc ≤ 2.38) y **arrancado como programa de 32 bits sobre esta BC-250**: H.264 y HEVC, codificación y decodificación |
| Comprobación de espacio en `/var` antes de cualquier instalación que toque el sistema en SteamOS (100 MB; avisa por debajo de 250) | `steamos-root.sh` (lo usan todos los flujos con `pacman`), `steamos_readonly.py` | Pruebas del guard con el bash real |
| **SMT en caliente** (apagar/encender ahora, sin guardar) donde el kernel lo permite | helper privilegiado, panel de opciones de arranque | Pruebas del helper en sandbox y de la interfaz |
| zswap de SteamOS pasa a **lz4** (como el toolkit desde v0.34; zstd y lzo-rle siguen de reserva) | `system_setup_memory.py` | Prueba actualizada |
| Aviso de que el desbloqueo de núcleos **no es permanente** y qué hacer si hay inestabilidad (issue #23) | guía de persistencia de firmware | — |
| `duggasco/bc250-40cu-unlock` marcado **Archivado** en la ventana de repositorios (se puede buscar «archived») | `settings.py` | Prueba |
| Revisión fijada de `fsr4_opticlient` corregida a `528f13b` (el código ya instalaba la 1.0.7-bc250.5; el catálogo seguía en la anterior) | `catalog.py` | Pruebas del catálogo |
| Fila del VA-API que faltaba en `THIRD_PARTY_NOTICES.md` | docs | — |

### Memoria y swap: revisión

El diseño del Control Center (helper en Python con estado y restauración) es más robusto que el de los scripts del toolkit. El fallo que corrigió el toolkit en v0.34.0, un ciclo de dependencias de arranque entre la unidad de zswap y `tmp.mount`, **no se da aquí**: no hay unidad que espere a `systemd-tmpfiles-setup`; la configuración de zswap en SteamOS va en un archivo de `tmpfiles.d` y el servicio de arranque corre después de `swap.target`. Lo que no existe aquí es el **selector de compresor** de zram/zswap (lz4/zstd) del toolkit: no lo añadí porque la interfaz de memoria está duplicada en dos pantallas y ligada a las reglas de Bazzite, y el cambio de valor por defecto de zswap cubre lo que más importa.

### No hecho, y por qué

- **Perfil RADV R2** y **BC-250 GE-Proton**: son dos instalaciones de más de 1 GB cada una, ligadas al runtime RADV de FSR4 de MastaG y, el R2, a un Proton privado con vkd3d parcheado y compilación de Mesa como alternativa (el script del toolkit tiene unas 4000 líneas). Sin SteamOS real para probar, prefiero no entregar algo que pueda fallar a medias.
- **Pins de `gddr6_memory_temp` y `cyan_smu`**: el primero cambia un binario que se escribe en la memoria del SMU (`SMUPayload.bin`) y su `main.c`; el segundo cambia solo mensajes de error, pero el parche propio del Control Center sobre ese código (`patch-cyan-bc250cc-runtime.py`) toca los mismos archivos. Ninguno se cambia sin probar en hardware.
- **CEC**: receptor que sigue al equipo, entrega de entrada, reparación del registro y mapa de teclas del mando de la TV. Sin adaptador ni TV, todo sería a ciegas.
- **Sunshine/WiVRn y variables de afinación del driver de vídeo**.
- **Comprobación general tras una actualización de SteamOS**: el panel ya muestra el estado de cada componente y existe el reinstalador del programa; lo único que faltaba eran las librerías de 32 bits, que ya tienen su botón de reparación.
- **AIC8800 (Wi-Fi/Bluetooth OEM)**: el Control Center solo lo trata como referencia; el módulo con el arreglo del toolkit no está integrado.
- **HelixSR 1.9.0**: aún no es una versión publicada.

### Pruebas

Suite completa: 5318 pasadas. Fallan 3 por no haber `dpkg` en esta Manjaro y, a veces, una que depende del orden de ejecución. Vi un fallo de segmentación de Qt (`UsageBar` pintándose ya borrada) en una de las ejecuciones completas y **no se repitió** en la siguiente: es otro problema de ciclo de vida de objetos de PyQt, sin causa localizada.

### Resuelto en la primera pasada: el fallo de segmentación de `test_combo_wheel_guard.py`

La causa era un filtro de eventos de Python instalado en toda la aplicación (`install_combo_wheel_guard`): Qt envía eventos a los widgets mientras se destruyen y PyQt entrega un objeto Python que ya se está liberando; se reproducía incluso con un filtro vacío. Ahora cada lista desplegable es un `GuardedComboBox` y una prueba de arquitectura impide volver a crear un `QComboBox` sin proteger. El filtro de `core/gamepad.py` (navegación con mando) se quita en `aboutToQuit`, así que no queda instalado al destruir las ventanas al salir.

## 8. Contenedores rootless y el overlay `gpu_metrics` del gobernador (14 de octubre, tercera pasada)

Tras reiniciar, `podman run` fallaba en esta BC-250 con `error mounting "sysfs" ... operation not permitted`
(`VFS: Mount too revealing` con `unshare -Urmn mount -t sysfs`). Causa: el `fix-metrics` del gobernador Cyan monta
un fichero parcheado (tmpfs `/patched_gpu_metrics`) **sobre** `gpu_metrics` en `/sys`, y el kernel no deja a un
contenedor sin privilegios montar un sysfs nuevo mientras haya algo montado encima del `/sys` del anfitrión.
Con `--network=none` falla igual; con `--network=host` funciona, porque entonces Podman enlaza el `/sys` del
anfitrión en vez de montar uno.

Afectaba a todo lo que compila en un contenedor: driver VA-API (64 y 32 bits), `cecd`, daemon de telemetría APU,
compilación FSR4 y, en Bazzite, la del propio gobernador (Cyan y Oberon).

Arreglo (`container_network.py` y `install-cyan-upstream-release.sh`): antes de lanzar el contenedor se pregunta
al kernel si dejaría montar el sysfs y, solo si no, se añade `--network=host`. Sin el overlay nada cambia (red
aislada por defecto); `sudo podman` no se ve afectado; la compilación de telemetría conserva `--network=none`
salvo que el overlay no deje otra salida. Comprobado en esta máquina: el ayudante detecta el overlay y el
contenedor arranca.
