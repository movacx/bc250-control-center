# Validación física de SteamOS · Real Toolkit

Estado: pendiente. Este protocolo complementa las pruebas con fixtures; no
certifica que los componentes se hayan probado en una consola. El equipo de
desarrollo inspeccionado el 2026-11-16 usa Arch Linux con kernel
7.3.4-1.425-cachyos-bc250, por lo que no sirve como evidencia de arranque SteamOS.

El proveedor ya no está fijado: cada acción resuelve el último commit de `main`
(el 2026-11-18 seguía siendo `88abd200170c8855f45cc6883e72d243151ceb7a`, 1.12.0) y
lo anota en `.bc250cc-provider.json`; anotar en cada sesión el hash que muestra la
terminal («Preparing SteamOS Real Toolkit (main xxxxxxx)»). La alternativa
keyboardspecialist sí está fijada: kernel/Mesa en `6aee553` (v0.40.0, 2026-11-17;
antes `e1563f2`, v0.30.0) y Proton siguiendo `master`. El inventario completo de funciones y opciones anidadas está en
[steamos-real-toolkit-inventory.json](steamos-real-toolkit-inventory.json).
La ruta de integración y las adaptaciones se documentan en
[STEAMOS_REAL_TOOLKIT_MIGRATION.md](STEAMOS_REAL_TOOLKIT_MIGRATION.md).

## Registro de cada sesión

Antes de una sesión física, validar también el archivo de fuentes fijado desde
el checkout de Control Center (no ejecuta instaladores ni descarga archivos):

```bash
python3 scripts/qa/validate-steamos-toolkit-source.py /ruta/al/archivo-revisado.tar.gz --report /ruta/al/informe.json
```

Conservar el informe junto al registro de la sesión y comprobar que sus hashes
del adaptador coinciden con el checkout probado. Un resultado correcto de este
comando demuestra preparación y sintaxis, no instalación ni funcionamiento del
hardware.

Anotar revisión de Control Center, revisión del Toolkit, versión/canal de
SteamOS, kernel, modelo BC-250, topología CPU/CU inicial, periféricos presentes,
proveedores ya instalados y modo de protección de la raíz. Conservar el comando
exacto, decisiones en los menús, salida, código de retorno, cambios observados,
reinicio requerido y resultado posterior al reinicio. Un periférico ausente o
una operación cancelada se registra como **no probada**, nunca como aprobada.

Consultas de referencia antes y después (sin modificar la configuración):

```bash
cat /etc/os-release
uname -r
steamos-readonly status
findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS --target /
findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS --target /home
lscpu
swapon --show
systemctl --failed --no-pager
systemctl status bc250-smu-oc cyan-skillfish-governor-smu --no-pager
```

Un servicio inexistente puede producir un retorno distinto de cero: registrar
ese resultado como estado inicial, no convertirlo automáticamente en fallo de
la integración. Guardar localmente la configuración propia relevante antes de
cambiar cada componente para comparar contenido, permisos y persistencia.

## Matriz de instalaciones y convivencia

Ejecutar por separado en instalaciones de prueba recuperables:

1. SteamOS sin proveedores anteriores: paquete de Control Center y, en otra
   sesión, instalación desde código con prefijo de usuario. Comprobar que las
   mismas acciones abren terminal interactiva y usan los helpers protegidos.
2. SteamOS con funciones nativas de Control Center configuradas: CPU OC y su
   persistencia, Cyan/GPU, CU, ventiladores, ACPI, audio, vídeo VA-API y CEC. Las operaciones
   externas que los reemplazarían deben detenerse antes de modificar sus
   archivos/servicios. Las acciones independientes siguen disponibles.
3. SteamOS con keyboardspecialist instalado: su estado, reparación, retirada
   y rollback siguen disponibles en la alternativa explícita. Real Toolkit
   debe detectar conflictos, sin sustituir el proveedor automáticamente.
   Incluir una instalación con solo parche de kernel y otra con rollback
   interrumpido antes de regenerar initramfs; Mesa no debe ser requisito para
   detectar sus marcadores. Los marcadores compartidos de versiones antiguas
   requieren revisión/rollback explícito antes de cambiar de instalador.
4. SteamOS con Real Toolkit instalado: estado real coherente con drivers,
   servicios y configuraciones. La alternativa debe rechazar una toma de
   control de gráficos mientras sigan sus artefactos, incluso incompletos.

En todas las sesiones verificar también GPU nativa, fans y perfiles, BIOS,
Blackbox, acceso remoto, plugin Decky propio, monitoreo, CU y CPU OC persistente.
Comparar con el estado inicial y reiniciar donde corresponda. La presencia de
una opción del Toolkit no autoriza a sustituir silenciosamente esos módulos.
No usar «Instalar todo» para preparar una sesión que necesita funciones nativas
superpuestas: probar ese flujo completo en una instalación separada.

## Acciones que requieren evidencia

Cada fila requiere instalación/configuración, estado efectivo y retirada o
restauración cuando el proveedor la ofrece. Las claves corresponden al registro
cerrado del adaptador; abrir un menú no valida sus opciones internas. Para los
menús, recorrer y registrar cada opción pertinente del inventario, incluyendo
cancelar/volver. No ejecutar todo el registro como un script automático.

Solo se exponen las filas que la aplicación no ofrece de forma nativa; CPU/GPU,
CU, perfiles, memoria/swap, ventiladores, CoolerControl, mitigaciones y extras se
prueban con los controles propios de Control Center.

| Componente (origen `SteamOS · rpf16rj`) | Acciones Real Toolkit | Evidencia física |
| --- | --- | --- |
| Administración del toolkit | `verify` | Pendiente |
| Gestión de energía · ACPI | `acpi-install`, `acpi-revert` | Pendiente |
| Recuperación de arranque · GRUB | `recovery` | Pendiente |
| Claves de firma de paquetes | `keyring` | Pendiente |
| Kernel y Mesa · GFX1013 | `combined-install`, `combined-revert` | Pendiente |
| Proton · FSR4 | `proton-install`, `proton-revert` | Pendiente |
| Vídeo por hardware · VA-API | `video-install`, `video-revert` | Pendiente |
| Dolby Digital · AC-3 | `ac3-install`, `ac3-revert` | Pendiente |
| Salida de audio doble | `dual-install`, `dual-revert` | Pendiente |
| Control del televisor · HDMI-CEC | `cec-setup`, `cec-status`, `cec`, `cec-wake-install`, `cec-wake-remove`, `cec-poweroff-install`, `cec-poweroff-remove`, `cec-clear-overrides` | Pendiente |
| AIC8800 · Wi-Fi / Bluetooth | `aic8800` | Pendiente |
| Intel BE200 | `be200` | Pendiente |
| DualSense | `dualsense` | Pendiente |
| Adaptador inalámbrico Xbox | `xbox-adapter` | Pendiente |
| OpenLinkHub | `openlinkhub-install`, `openlinkhub-revert` | Pendiente |

### Alternativa conservada

| Componente | Acciones keyboardspecialist | Evidencia física |
| --- | --- | --- |
| Compatibilidad del kernel | `kernel-install`, `kernel-status`, `kernel-rollback` | Pendiente |
| Mesa / RADV · GFX1013 | `graphics-install`, `graphics-status`, `graphics-uninstall-fsr4`, `graphics-uninstall` | Pendiente |
| BC-250 GE-Proton | `proton-install`, `proton-status`, `proton-uninstall` | Pendiente |

## Criterios funcionales por familia

- CPU/GPU/CU: valores observados y persistentes tras reinicio, límites y
  topología correctos; ningún servicio compite por los mismos controles.
- Memoria: reparto RAM/VRAM, swap y ZRAM/ZSWAP realmente activos después del
  reinicio; restauración consistente con el estado documentado por upstream.
- Kernel/Mesa: compilar para el kernel de la sesión; comprobar arranque,
  módulo cargado, Vulkan de 64/32 bits y una carga gráfica representativa.
  Comparar selección de ICD antes/después. No inferir soporte de otra versión
  de kernel por una compilación exitosa o por superar el mínimo de upstream.
- Pantalla/audio: HDMI, modos utilizados, sonido y suspensión/reanudación;
  probar por separado AC-3, salida doble y CEC con hardware compatible.
- Vídeo/Proton: verificar funcionamiento en una aplicación real; que el
  instalador termine o que aparezca un archivo no demuestra aceleración o FSR4.
- Fans/sensores: lecturas razonables y control efectivo; comprobar arbitraje
  entre motor nativo y servicio externo, también al cambiar de estado en vivo.
- Wi-Fi/BT/mandos/accesorios: dispositivo reconocido y uso real después de
  reiniciar; probar los menús de instalación, estado y retirada disponibles.
- Decky/extras: carga en modo juego y bajo el usuario correcto; plugin propio
  y externo diferenciados. Comprobar perfiles y PWM sin saltarse las guardas.
- Emuladores/juegos: inicio real, accesos directos y retirada con los datos del
  usuario conservados según el contrato del componente.

## Fallos, retirada y recuperación

1. Cancelar cada clase de diálogo: no confirmar una instalación ni declarar
   éxito de una operación que no se realizó.
2. Probar fallos controlados de descarga y espacio en un entorno de prueba:
   error legible, sin ejecución de bytes no verificados y sin abrir la raíz
   durante la preparación de fuentes.
3. Probar una acción correcta y una fallida con la raíz inicialmente protegida
   y, por separado, escribible: restaurar y verificar el modo inicial. Registrar
   interrupciones por separado; las pruebas Python no certifican cortes de
   energía, señales no manejadas o pérdida de la terminal.
4. Probar instalación, reparación, retirada y reinstalación de gráficos por
   proveedor. El rollback de kernel de la alternativa no debe quitar Mesa,
   Proton ni módulos de otros kernels.
   La recuperación masiva debe detectar también parches del otro proveedor
   en kernels distintos del actual; las acciones individuales conservan su
   ámbito del kernel en ejecución.
5. Crear las entradas de recuperación; arrancarlas de verdad en el equipo de
   prueba. Un rechazo de guarda, fallo de desbloqueo o de un componente debe
   impedir la limpieza final y el reinicio de éxito. Conservar el código de
   error y la evidencia para reparar/reintentar.
6. Probar recuperación con el árbol de trabajo presente y su ruta de emergencia
   sin él. Revisar los cambios frente al estado inicial, no solo el mensaje
   final. Ninguna guarda debe desaparecer por retirar el paquete de la app.
7. Verificar el checker persistente de Decky/recuperación tras retirar la app
   en la instalación de prueba y luego reinstalarla. Las pruebas de importación
   aislada existentes no sustituyen esa prueba completa del ciclo de vida.

## Lista de entrega (2026-11-18)

Orden pensado para una BC-250 con SteamOS 3.9.5 (kernel 7.2.7) como la de
desarrollo. Cada paso dice qué debería verse y cómo volver atrás. Antes de nada,
guardar `uname -r`, `steamos-readonly status`, `df -h / /var /home` y
`pacman -Q bc250-control-center`.

1. **Una sola instalación.** Si `pacman -Q bc250-control-center` responde, hay un
   paquete: actualizarlo en lugar de mezclar (`BC250_PKG_RELEASE=4
   packaging/scripts/build-local-pkg.sh`, `sudo steamos-readonly disable`,
   `sudo pacman -U dist/bc250-control-center-*-any.pkg.tar.zst`, `sudo
   steamos-readonly enable`). Con `scripts/install-local.sh` encima del paquete el
   instalador avisa con `[WARN] … also installed as the system package`.
   Comprobar después: `cmp privileged/lib/bc250_steamos_toolkit_runtime.zip
   /usr/libexec/bc250-control-center/lib/bc250_steamos_toolkit_runtime.zip` sin
   salida y `stat -c '%U:%a' …zip` = `root:644`. Volver atrás: reinstalar el
   paquete anterior con `pacman -U`.
2. **Solo-lectura.** En Preparación, el panel de solo-lectura muestra el estado
   real (`Protegido`/`Escribible`). Si la raíz quedó escribible de una sesión
   anterior y se quiere protegida: «Volver a activar solo lectura». Esperado: el
   panel pasa a `Protegido` sin errores. En la interfaz de terminal, «SteamOS
   read-only mode → Status» termina bien en ambos estados (antes salía con el
   código 1 de `steamos-readonly status` y se mostraba como fallo).
3. **Toolkit · Administración → Verificar.** La terminal muestra el commit de
   `main`, el estado de `/` y `/var` (avisos `[WARN]` si quedan <300 MB en `/` o
   <250 MB en `/var`), ejecuta `run_status` y al terminar la raíz vuelve a su
   estado inicial. Comprobar `steamos-readonly status` antes y después.
4. **Una acción que la guarda debe rechazar.** Con el kernel/RADV de
   keyboardspecialist instalados, «Kernel y Mesa · GFX1013 → Instalar» debe parar
   con `Existing keyboardspecialist / Control Center graphics artifacts were
   found…` y `The toolkit cache was kept` (no se vuelve a descargar el archivo).
5. **ACPI del toolkit** (si se quiere): instalar, reiniciar, comprobar
   `/var/lib/bc250-acpi-fix/acpi_override.cpio` y el estado en la fila; revertir
   con «Quitar corrección ACPI».
6. **Alternativa keyboardspecialist.** «Compatibilidad del kernel → Verificar»
   debe decir `READY FOR MESA / RADV` o `READY` si el módulo está activo; ya no
   ofrece «Install per-game FSR4» (upstream lo retiró). Tras una instalación de
   kernel nueva, la política `amdgpu.sched_policy=2` ya no se escribe junto con
   el módulo: la activa «Mesa / RADV → Instalar», como hace upstream. Volver
   atrás: «Restaurar módulo original del kernel actual» y reiniciar.
   Con la fijación v0.40.0 (`6aee553`): una copia protegida preparada por
   Control Center 1.22.x (v0.30) sigue sirviendo para «Verificar» y «Restaurar
   módulo original» (la terminal avisa de que es v0.30.0); «Preparar» vuelve
   a copiar la v0.40 (ahora con `fetch-build-deps.sh` y
   `bc250-mesa-patches/libdrm-2.4.134-wrap.patch`, nunca `scripts/`) y, si el
   módulo de v0.30 sigue verificado, no recompila (mismos parches y marcas
   `smu-8core-metrics-r1`). Si hay que compilar, la terminal muestra
   `Build dependency repositories: extra-3.9 core-3.9` antes de bajar el kernel;
   ya no aparece el adaptador `*-bc250cc.sh`. «Mesa / RADV → Instalar» compila
   Mesa 26.3.0 con DirectMesh 1.4 para todos los juegos (`RADV_DIRECTMESH=0
   %command%` lo apaga en uno); «Verificar Mesa / RADV» debe mostrar
   `DirectMesh directmesh-v1.4`. Un Mesa / RADV instalado con 1.22.x
   (mesa-26.2.2, `production-fsr4-v4`) aparece «Instalado» y, ya con la copia
   v0.40, «Installed (earlier release)» en «Verificar»; «Instalar / actualizar»
   lo sustituye y «Quitar» lo retira. «BC-250 GE-Proton → Instalar» espera a
   que Mesa / RADV sea el de v0.40.
7. **Coexistencia nativa.** Con el AC-3 de rpf16rj instalado, el AC-3 propio
   debe mostrarse «gestionado por otra herramienta»; con el OpenLinkHub propio
   instalado, «OpenLinkHub → Instalar» del toolkit queda deshabilitado y marcado
   `BC250 Control Center`.
8. **Desinstalación local en SteamOS** (solo si se instaló con
   `install-local.sh`): `uninstall-local.sh` abre la raíz, retira los helpers de
   `/usr/libexec/bc250-control-center` y vuelve a protegerla; si no puede, lo dice
   en vez de culpar a un paquete.
9. **Tras una actualización de SteamOS**: `/usr` (helpers, paquetes, módulos de
   kernel parcheados) se pierde; `/etc` conserva solo lo listado en
   `/etc/atomic-update.conf.d`. Reinstalar Control Center, después repetir el
   kernel fix del proveedor elegido. El Mesa de rpf16rj vive en `/opt` (en
   `/home`) y su `VK_DRIVER_FILES` en `/etc/environment` (conservado), así que
   puede seguir activo sin el módulo parcheado: ejecutar «Verificar la
   instalación» y repetir «Kernel y Mesa · GFX1013» antes de jugar.

## Cierre

Una fila se aprueba únicamente con su registro físico y sus resultados de
retirada/restauración. Anotar versión/canal exactos para cada resultado y fallos
pendientes con su reporte. No declarar soporte completo con filas pendientes,
menús sin recorrer o únicamente resultados de mocks y empaquetado.
