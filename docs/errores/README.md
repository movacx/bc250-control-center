# Errores y códigos de BC250 Control Center

Aquí están los errores que la app conoce: qué significa cada código, por qué
pasa y cómo se arregla en tu distribución. Si te salió una ventana de error,
busca su código (Ctrl+F) y vas directo a la ficha que corresponde.

## Cómo leer un error

Cada error que muestra la app trae un código con la forma `BC250-ÁREA-NNN`,
por ejemplo `BC250-PKG-001`.

- El **código** dice en qué parte falló: paquetes, governor, ventiladores...
- La **ficha** (`INST-01`, `GOV-08`...) explica qué pasó realmente y qué hacer.

Un mismo código puede tener varias fichas. `BC250-GENERAL-001`, por ejemplo,
significa "la operación falló y la app no reconoció el motivo", y detrás hay
causas muy distintas. En ese caso, compara el mensaje que viste con el
apartado **Qué se ve** de cada ficha.

Las mismas fichas están dentro de la app, en Ajustes → Acerca de → Soporte →
Errores conocidos, y ahí se abren ya con los pasos para tu distribución.

## Si tu error no está aquí

Usa **Reportar un problema** en la app. El reporte lleva los registros que
hacen falta para encontrar la causa, así que no tienes que copiar nada a
mano. Si el error es nuevo, se agrega a esta lista en cuanto se entiende.

<!-- generado automáticamente -->

## Números

**240 reportes** recibidos entre 2026-10-27 y 2026-11-21 (230 problemas y 10 ideas). 217 ya tienen su ficha; 13 todavía se están investigando. Actualizado el 2026-11-21.

### Por distribución

| Distribución | Problemas |
|---|---|
| Bazzite | 78 |
| CachyOS | 70 |
| SteamOS | 33 |
| Linux Mint | 27 |
| Fedora Linux | 9 |
| Arch Linux | 6 |
| Ubuntu | 3 |
| (oculta por privacidad) | 3 |
| Winux | 1 |

### Por versión de la app

| Versión | Problemas |
|---|---|
| 1.22.9 | 46 |
| 1.22.8 | 9 |
| 1.22.6 | 2 |
| 1.22.5 | 10 |
| 1.22.4 | 2 |
| 1.22.3 | 48 |
| 1.22.2 | 10 |
| 1.22.0 | 33 |
| 1.21.4 | 11 |
| 1.21.3 | 59 |

### Las fichas que más se repiten

| Ficha | Qué pasa | Reportes | Último |
|---|---|---|---|
| [PKG-01](#pkg-01) | El gestor de paquetes está bloqueado (pacman o apt) | 13 | 2026-11-21 |
| [UPS-01](#ups-01) | El archivo de HelixSR publicado no es el que la app revisó | 11 | 2026-11-21 |
| [GOV-01](#gov-01) | La configuración de Cyan tiene una clave repetida (Cannot declare … twice) | 10 | 2026-11-08 |
| [AUTH-01](#auth-01) | La autorización de administrador no se completó | 9 | 2026-11-20 |
| [PKG-03](#pkg-03) | No se pueden sincronizar las bases de paquetes (red, espejo o repositorio de MastaG) | 8 | 2026-11-20 |
| [GOV-07](#gov-07) | La GPU BC-250 no aparece donde Cyan la busca (o no se detecta) | 7 | 2026-11-12 |
| [INST-09](#inst-09) | Falta un ayudante protegido o no pasa su comprobación de seguridad | 7 | 2026-11-18 |
| [STEAM-01](#steam-01) | La versión del kernel de SteamOS no está soportada por el backend revisado | 7 | 2026-11-17 |
| [UPS-03](#ups-03) | El compilador de shaders (DXC por Wine/Proton) falla | 7 | 2026-11-20 |
| [INST-08](#inst-08) | La interfaz y el ayudante protegido son de versiones distintas | 6 | 2026-11-16 |
| [INST-10](#inst-10) | Linux negó el acceso a un archivo o dispositivo necesario | 6 | 2026-11-10 |
| [PKG-06](#pkg-06) | La instalación del kernel + Mesa de MastaG se corta en la confirmación de pacman | 6 | 2026-11-07 |
| [CU-01](#cu-01) | UMR no está instalado | 5 | 2026-11-15 |
| [GOV-10](#gov-10) | Cambiar el rango o la curva de GPU se rechaza (telemetría no disponible / Cyan apagado) | 5 | 2026-11-12 |
| [INST-02](#inst-02) | Un paquete propio del usuario rompe la transacción de rpm-ostree (logitech-trueforce) | 5 | 2026-11-21 |

## Códigos

Cada error que muestra la app lleva un código `BC250-ÁREA-NNN`. El código dice *dónde* falló; la ficha dice *por qué* y cómo se arregla. Un mismo código puede tener varias fichas (por ejemplo, `BC250-GENERAL-001` es el cajón de lo que no se reconoció).

| Código | Significado | Fichas | Reportes |
|---|---|---|---|
| `BC250-AUTH-002` | La autorización del administrador no se completó. | [AUTH-01](#auth-01) | 2 |
| `BC250-BUILD-001` | Las herramientas de compilación de SteamOS son incompatibles con las bibliotecas del sistema instaladas. | [STEAM-03](#steam-03) |  |
| `BC250-BUILD-002` | No se pudo compilar el módulo SteamOS AMDGPU. | [STEAM-03](#steam-03) |  |
| `BC250-BUILD-003` | Un paso de compilación falló. | [AUTH-01](#auth-01) | 2 |
| `BC250-BUSY-001` | Otra operación todavía utiliza este componente. | [INST-04](#inst-04) [AUTH-01](#auth-01) | 4 |
| `BC250-CMD-001` | Falta un programa requerido o un comando generado. | [INST-06](#inst-06) [CU-01](#cu-01) [CPU-01](#cpu-01) [MESH-01](#mesh-01) | 5 |
| `BC250-CONFIG-001` | Un archivo de configuración no es válido o está incompleto. | [INST-09](#inst-09) [GOV-02](#gov-02) [GOV-03](#gov-03) [CPU-01](#cpu-01) | 5 |
| `BC250-CONTAINER-001` | Podman sin root no tiene ID de usuario subordinados para este usuario. | [VID-02](#vid-02) |  |
| `BC250-CPU-001` | El resultado del ajuste de CPU no se pudo aplicar ni verificar. | — |  |
| `BC250-CPUTOOL-001` | La carga de CPU auditada rechazó el valor solicitado. | — |  |
| `BC250-CU-001` | No se pudo verificar la operación de Compute Units. | [GOV-06](#gov-06) [CU-01](#cu-01) [CU-03](#cu-03) | 7 |
| `BC250-DATA-001` | El flujo de trabajo rechazó una configuración existente o incoherente. | [AUTH-01](#auth-01) | 1 |
| `BC250-DBUS-001` | El governor GPU no expuso sus controles D-Bus. | [GOV-01](#gov-01) [GOV-09](#gov-09) [GFX-03](#gfx-03) | 3 |
| `BC250-FAN-001` | La ruta de control del ventilador no está disponible o se rechazó la escritura. | [INST-10](#inst-10) [FAN-01](#fan-01) | 2 |
| `BC250-FAN-002` | El abanico se entrega a otro programa. | — |  |
| `BC250-GENERAL-001` | La operación no se pudo completar. | [INST-01](#inst-01) [INST-02](#inst-02) [INST-03](#inst-03) [INST-05](#inst-05) [INST-09](#inst-09) [AUTH-01](#auth-01) [PKG-02](#pkg-02) [PKG-03](#pkg-03) [PKG-04](#pkg-04) [PKG-06](#pkg-06) [PKG-10](#pkg-10) [PKG-11](#pkg-11) [GOV-01](#gov-01) [GOV-05](#gov-05) [GOV-06](#gov-06) [GOV-07](#gov-07) [CU-02](#cu-02) [STEAM-02](#steam-02) [STEAM-05](#steam-05) [UPS-02](#ups-02) [UPS-03](#ups-03) [UPS-05](#ups-05) [UPS-06](#ups-06) [VID-01](#vid-01) [VID-02](#vid-02) [MESH-02](#mesh-02) [GFX-04](#gfx-04) [FAN-01](#fan-01) [NET-01](#net-01) [UPS-08](#ups-08) [STOR-02](#stor-02) | 67 |
| `BC250-GFX-001` | Ya hay una versión del fix GFX1013 instalada. | — |  |
| `BC250-GPU-001` | La fuente de telemetría GPU seleccionada no está disponible. | [GOV-01](#gov-01) | 1 |
| `BC250-GPU-005` | El governor no pudo colocar sus archivos de sensor parcheados. | — |  |
| `BC250-GPU-007` | — | [GOV-06](#gov-06) |  |
| `BC250-GPU-008` | Cyan no está en marcha, así que la curva de voltaje no se cambió. | — |  |
| `BC250-GPU-900` | No se pudo completar la operación GPU. | [AUTH-01](#auth-01) [GOV-03](#gov-03) [GOV-06](#gov-06) [GOV-09](#gov-09) [GOV-10](#gov-10) [CU-03](#cu-03) [UPS-07](#ups-07) | 10 |
| `BC250-HELPER-001` | Falta un helper protegido de BC250 o no pasó la verificación de seguridad. | [INST-09](#inst-09) | 2 |
| `BC250-HW-001` | No se detectó hardware BC-250 compatible. | [GOV-07](#gov-07) [FAN-04](#fan-04) | 2 |
| `BC250-IMMUTABLE-001` | La implementación del sistema inmutable no está lista para este cambio. | [PKG-04](#pkg-04) | 1 |
| `BC250-IMMUTABLE-002` | La raíz de SteamOS seguía siendo de solo lectura al escribir los paquetes. | — |  |
| `BC250-KERNEL-001` | El kernel en ejecución y su controlador o encabezados no coinciden. | [FAN-02](#fan-02) | 1 |
| `BC250-NET-001` | No se pudo alcanzar ni verificar una descarga requerida. | [GFX-03](#gfx-03) | 1 |
| `BC250-PERM-001` | Linux rechazó el acceso a un archivo o dispositivo requerido. | [INST-08](#inst-08) [INST-10](#inst-10) [GOV-06](#gov-06) | 2 |
| `BC250-PERM-002` | Linux rechazó el acceso a un archivo o dispositivo requerido. | [INST-10](#inst-10) |  |
| `BC250-PKG-001` | El gestor de paquetes está ocupado. | [PKG-01](#pkg-01) [TV-01](#tv-01) | 10 |
| `BC250-PKG-002` | No se pudo verificar la firma del paquete o la clave del repositorio. | [INST-03](#inst-03) [PKG-05](#pkg-05) | 1 |
| `BC250-PKG-004` | Un paquete necesario no está disponible en los repositorios habilitados. | [INST-01](#inst-01) [PKG-09](#pkg-09) | 1 |
| `BC250-PKG-005` | La lista de paquetes de este sistema está desactualizada. | [PKG-03](#pkg-03) |  |
| `BC250-PKG-006` | Un paquete descargado llegó dañado. | [PKG-05](#pkg-05) |  |
| `BC250-PKG-007` | El mismo repositorio de paquetes está configurado dos veces. | [PKG-11](#pkg-11) |  |
| `BC250-PROTOCOL-001` | La interfaz y el helper protegido son versiones diferentes. | [INST-07](#inst-07) [INST-08](#inst-08) [AUTH-01](#auth-01) [GOV-07](#gov-07) [GOV-11](#gov-11) [STEAM-03](#steam-03) | 13 |
| `BC250-PROTON-001` | La operación de GE-Proton de SteamOS no se completó. | [STEAM-06](#steam-06) | 1 |
| `BC250-RANGE-001` | El valor solicitado está fuera del rango admitido. | [STEAM-04](#steam-04) | 1 |
| `BC250-RESOURCE-001` | El sistema no pudo iniciar otro proceso. | — |  |
| `BC250-RUNTIME-001` | Un programa necesita una biblioteca del sistema más nueva que la de este equipo. | — |  |
| `BC250-SERVICE-002` | — | [GOV-05](#gov-05) |  |
| `BC250-SERVICE-003` | El gestor de servicios no pudo completar el cambio solicitado. | [INST-09](#inst-09) | 2 |
| `BC250-STORAGE-001` | No hay suficiente almacenamiento de escritura. | [STOR-01](#stor-01) [MEM-02](#mem-02) [STOR-02](#stor-02) | 1 |
| `BC250-TERMINAL-001` | No se pudo iniciar el flujo de trabajo del terminal requerido. | — |  |
| `BC250-TIMEOUT-001` | La operación no terminó dentro de su límite de seguridad. | [INST-05](#inst-05) [VID-01](#vid-01) | 2 |
| `BC250-TTM-001` | No se pudo cambiar el límite de memoria de la GPU. | [MEM-02](#mem-02) |  |
| `BC250-UMR-001` | UMR no está funcionando. | [CU-01](#cu-01) [CU-02](#cu-02) | 2 |
| `BC250-UPSCALE-002` | HelixSR rechazó este juego por su anti-cheat. | — |  |
| `BC250-UPSTREAM-404` | El repositorio de paquetes externo no está disponible temporalmente en su dirección. | [AUTH-01](#auth-01) [PKG-01](#pkg-01) [PKG-03](#pkg-03) | 9 |
| `BC250-VRAM-001` | No se pudo cambiar el tamaño de la VRAM. | — |  |
| `BC250-WINE-001` | Wine no pudo iniciarse. | [UPS-03](#ups-03) |  |
| `BC250-WINE-002` | Wine o Proton no pueden ejecutarse en este entorno. | [UPS-03](#ups-03) |  |
| `BC250-WORKFLOW-001` | El flujo de trabajo informó el error en sí. | [INST-02](#inst-02) [INST-09](#inst-09) [PKG-01](#pkg-01) [PKG-03](#pkg-03) [PKG-07](#pkg-07) [PKG-08](#pkg-08) [PKG-10](#pkg-10) [STOR-01](#stor-01) [GOV-03](#gov-03) [GOV-04](#gov-04) [GOV-06](#gov-06) [GOV-07](#gov-07) [GOV-08](#gov-08) [GOV-11](#gov-11) [GOV-13](#gov-13) [CU-02](#cu-02) [CU-03](#cu-03) [MEM-01](#mem-01) [MEM-02](#mem-02) [MEM-03](#mem-03) [MEM-04](#mem-04) [STEAM-01](#steam-01) [UPS-01](#ups-01) [UPS-03](#ups-03) [UPS-04](#ups-04) [VID-03](#vid-03) [GFX-01](#gfx-01) [GFX-02](#gfx-02) [AUD-01](#aud-01) [AUD-02](#aud-02) [TV-01](#tv-01) [STEAM-07](#steam-07) | 56 |

## Fichas

### Instalación, actualización y ayudantes protegidos

<a id="inst-01"></a>
#### INST-01 · La actualización se bloquea por un paquete en capas que ya no existe

`BC250-GENERAL-001`, `BC250-PKG-004` · estado: corregido · visto en: Bazzite · 4 reportes, último el 2026-11-17

**Qué se ve.** Al pulsar "Actualizar aplicación" en Bazzite, rpm-ostree aborta con error: Packages not found: coolercontrol y no instala la nueva versión de Control Center.

**Por qué pasa.** rpm-ostree vuelve a resolver todos los paquetes en capas del sistema en cada cambio. Si uno ya no existe en ningún repositorio activo (aquí coolercontrol, porque su COPR se desactivó o Fedora lo retiró), la transacción entera falla aunque el paquete no tenga nada que ver con Control Center.

**Cómo se arregla.**

*Bazzite*

Comprueba si el error dice «Packages not found: coolercontrol». Busca ese paquete en la lista LayeredPackages; el bloqueo corresponde a ese paquete en capas.

```bash
rpm-ostree status
```

Si el error nombra coolercontrol y ya no necesitas ese programa, retíralo con el comando de este paso. Si lo necesitas, recupera primero su repositorio y vuelve a actualizar.

```bash
rpm-ostree uninstall coolercontrol
```

Cuando termine la transacción, guarda tu trabajo y reinicia. Abre Control Center y repite «Actualizar aplicación»; la descarga ya no debería detenerse por coolercontrol.

```bash
rpm-ostree status
```


<a id="inst-02"></a>
#### INST-02 · Un paquete propio del usuario rompe la transacción de rpm-ostree (logitech-trueforce)

`BC250-GENERAL-001`, `BC250-WORKFLOW-001` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite · 5 reportes, último el 2026-11-21

**Qué se ve.** Preparar dependencias o actualizar la app en Bazzite falla con package logitech-trueforce-… requires (dkms-logitech-trueforce = … if dkms), but none of the providers can be installed.

**Por qué pasa.** El usuario tiene en capas un paquete de terceros (driver de volantes Logitech) que no se puede resolver contra la nueva imagen del sistema. rpm-ostree se niega a cualquier cambio hasta que se resuelva. Nada de esto lo instaló Control Center.

**Cómo se arregla.**

*Bazzite*

Busca el paquete que aparece antes de «none of the providers can be installed». Esta guía cubre el caso de logitech-trueforce instalado en capas.

```bash
rpm-ostree status
```

Si el paquete bloqueante es logitech-trueforce y puedes dejar de usar ese controlador, retíralo. Si lo necesitas, espera una versión compatible de su repositorio.

```bash
rpm-ostree uninstall logitech-trueforce
```

En Bazzite, reinicia después de completar el nuevo despliegue y vuelve a preparar las dependencias. Si cambia el paquete mencionado, revisa ese nuevo conflicto.

```bash
rpm-ostree status
```

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

En Fedora Workstation, revisa el paquete y su repositorio con dnf. Actualiza el controlador compatible o retira solo el paquete que ya no necesites. No se aplica el reinicio de un despliegue Atomic.

En Bazzite, reinicia después de completar el nuevo despliegue y vuelve a preparar las dependencias. Si cambia el paquete mencionado, revisa ese nuevo conflicto.


<a id="inst-03"></a>
#### INST-03 · Un repositorio de terceros no pasa la verificación de firma (GPG)

`BC250-GENERAL-001`, `BC250-PKG-002` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite · 4 reportes, último el 2026-11-15

**Qué se ve.** rpm-ostree aborta importando un RPM (cyan-skillfish-governor-smu…rpm could not be verified, foomatic-db-ppds…rpm could not be verified).

**Por qué pasa.** La llave GPG del repositorio (COPR de filippor para Cyan, repos de impresión) falta, caducó o cambió; o la caché de metadatos quedó a medias.

**Cómo se arregla.**

*Arch / CachyOS*

Anota el repositorio, el paquete y la clave que nombra el error. Comprueba también que la fecha del equipo sea correcta.

```bash
date -Is
```

Actualiza el llavero que corresponda a tu distribución y completa la actualización del sistema. Si falla la firma de un único paquete, comprueba su descarga antes de cambiar las claves.

Repite la instalación. Debe verificar la firma antes de continuar; conserva el mensaje completo si todavía falta una clave.

*SteamOS*

Anota el repositorio, el paquete y la clave que nombra el error. Comprueba también que la fecha del equipo sea correcta.

```bash
date -Is
```

Ejecuta el reinstalador o la preparación SteamOS de la app para recuperar sus llaveros. No mezcles llaves de una derivada de Arch con las de SteamOS.

Repite la instalación. Debe verificar la firma antes de continuar; conserva el mensaje completo si todavía falta una clave.

*Bazzite*

Anota el repositorio, el paquete y la clave que nombra el error. Comprueba también que la fecha del equipo sea correcta.

```bash
date -Is
```

Actualiza los metadatos con el comando indicado. Si continúa el error de firma, recupera la clave desde la página oficial de ese repositorio o desactiva solo la fuente que ya no utilices.

```bash
rpm-ostree refresh-md --force
```

Repite la instalación. Debe verificar la firma antes de continuar; conserva el mensaje completo si todavía falta una clave.

*Fedora*

Anota el repositorio, el paquete y la clave que nombra el error. Comprueba también que la fecha del equipo sea correcta.

```bash
date -Is
```

Actualiza los metadatos con el comando indicado. Si continúa el error de firma, recupera la clave desde la página oficial de ese repositorio o desactiva solo la fuente que ya no utilices.

```bash
sudo dnf clean all && sudo dnf makecache
```

Repite la instalación. Debe verificar la firma antes de continuar; conserva el mensaje completo si todavía falta una clave.

*Ubuntu / Mint, Debian*

Anota el repositorio, el paquete y la clave que nombra el error. Comprueba también que la fecha del equipo sea correcta.

```bash
date -Is
```

Ejecuta apt update y busca la línea «GPG error» o «NO_PUBKEY»: nombra el repositorio que falla. Si es una fuente que ya no usas (por ejemplo el repositorio de un programa que desinstalaste), desactiva solo esa fuente en /etc/apt/sources.list.d. Si la necesitas, instala su clave nueva desde la página oficial de ese repositorio.

```bash
sudo apt update
```

```bash
ls /etc/apt/sources.list.d/
```

Repite la instalación. Debe verificar la firma antes de continuar; conserva el mensaje completo si todavía falta una clave.


<a id="inst-04"></a>
#### INST-04 · Hay otra transacción de rpm-ostree en curso

`BC250-BUSY-001` · estado: corregido · visto en: Bazzite · 4 reportes, último el 2026-11-06

**Qué se ve.** Actualizar o preparar dependencias falla al instante con error: Transaction in progress: upgrade --check o install --idempotent foomatic-db….

**Por qué pasa.** Bazzite lanza solo sus actualizaciones automáticas (rpm-ostreed-automatic, uupd), o el usuario tiene otra instalación abierta. rpm-ostree solo acepta una transacción a la vez.

**Cómo se arregla.**

*Arch / CachyOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Deja terminar pacman/yay/paru. Si no queda ninguno activo, usa la liberación protegida del bloqueo de pacman desde Compatibilidad.

Vuelve a iniciar una sola actualización desde Control Center. El mensaje «Transaction in progress» debe desaparecer al quedar libre el gestor.

*SteamOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Deja terminar la instalación activa y repite el flujo SteamOS. Si el bloqueo continúa sin una operación activa, usa la reparación de pacman de la app.

Vuelve a iniciar una sola actualización desde Control Center. El mensaje «Transaction in progress» debe desaparecer al quedar libre el gestor.

*Bazzite*

Consulta el estado y comprueba si hay una actualización automática o una instalación todavía trabajando.

```bash
rpm-ostree status
```

Espera a que termine esa operación y cierra la otra herramienta de paquetes. Si la transacción está realmente detenida, revísala antes de decidir cancelarla.

Vuelve a iniciar una sola actualización desde Control Center. El mensaje «Transaction in progress» debe desaparecer al quedar libre el gestor.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Espera a dnf o PackageKit y vuelve a iniciar una sola instalación. No retires archivos de bloqueo mientras el gestor trabaja.

Vuelve a iniciar una sola actualización desde Control Center. El mensaje «Transaction in progress» debe desaparecer al quedar libre el gestor.

*Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Espera a apt/dpkg o unattended-upgrades. Cuando termine, vuelve a iniciar una sola instalación.

Vuelve a iniciar una sola actualización desde Control Center. El mensaje «Transaction in progress» debe desaparecer al quedar libre el gestor.


<a id="inst-05"></a>
#### INST-05 · rpm-ostree supera el tiempo límite

`BC250-TIMEOUT-001`, `BC250-GENERAL-001` · estado: corregido · visto en: Bazzite · 2 reportes, último el 2026-11-07

**Qué se ve.** error: Updating deployment: Timeout was reached al actualizar la app.

**Por qué pasa.** El demonio de rpm-ostree tardó más que el límite de D-Bus (red lenta, disco ocupado o descarga grande de metadatos).

**Cómo se arregla.**

*Bazzite*

Comprueba si rpm-ostree sigue trabajando, aunque la ventana haya mostrado un tiempo de espera agotado.

```bash
rpm-ostree status
```

Si la transacción ya terminó en error, comprueba la red y vuelve a actualizar. Si el fallo se repite al obtener metadatos, limpia esa caché antes del nuevo intento.

```bash
rpm-ostree cleanup -m
```

Repite la acción una sola vez y espera a que termine. Si vuelve a agotarse el tiempo, guarda el estado y el registro de la transacción actual.


<a id="inst-06"></a>
#### INST-06 · rpm-ostree no puede limpiar un despliegue antiguo

`BC250-CMD-001` · estado: lo resuelve el usuario · visto en: Bazzite · 1 reporte, último el 2026-11-01

**Qué se ve.** Aplicar un perfil de CPU que necesita un despliegue nuevo falla con error: Staging deployment: Cleaning deployments: Removing ostree/deploy/…: opendir(syntax): E….

**Por qué pasa.** Un despliegue antiguo de ostree está dañado o a medio borrar; rpm-ostree no puede preparar uno nuevo. No es un fallo de la app.

**Cómo se arregla.**

*Bazzite*

Consulta los despliegues y el espacio disponible. Localiza el texto «Cleaning deployments» en el error actual.

```bash
rpm-ostree status
df -h / /boot
```

Reinicia y prueba de nuevo cuando no haya otra transacción activa. Si el despliegue antiguo sigue dañado, conserva el registro para revisar qué despliegue debe repararse.

Comprueba si se puede preparar un nuevo despliegue. Si persiste el fallo, adjunta el registro de rpm-ostreed; evita eliminar a ciegas el despliegue de respaldo.

```bash
journalctl -u rpm-ostreed -b -n 80 --no-pager
```


<a id="inst-07"></a>
#### INST-07 · En Fedora falta parte del entorno gráfico de Python (PyQt6 QtSvg, psutil, venv)

`BC250-PROTOCOL-001` · estado: corregido en desarrollo (falta publicar) · visto en: Fedora · 1 reporte, último el 2026-11-07

**Qué se ve.** La actualización termina con Error: the GUI runtime is still incomplete after dependency installation (PyQt6 QtSvg, SVG plugin, psutil, pip or venv).

**Por qué pasa.** Instalación con install-local.sh en Fedora: faltaban paquetes del sistema para el entorno gráfico.

**Cómo se arregla.**

*Arch / CachyOS*

Revisa qué dependencia falta: PyQt6, QtSvg, psutil o el entorno virtual. Esta guía se aplica principalmente a instalaciones desde código.

Instala las dependencias con el gestor de tu distribución o reinstala su paquete oficial de Control Center para que las prepare. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu python-pyqt6 qt6-svg python-psutil
```

Cierra y vuelve a abrir Control Center. La interfaz debe cargar sin indicar que el entorno gráfico de Python está incompleto.

*SteamOS*

Revisa qué dependencia falta: PyQt6, QtSvg, psutil o el entorno virtual. Esta guía se aplica principalmente a instalaciones desde código.

Usa el reinstalador SteamOS de la app para preparar el paquete y sus dependencias en el entorno correcto.

Cierra y vuelve a abrir Control Center. La interfaz debe cargar sin indicar que el entorno gráfico de Python está incompleto.

*Bazzite*

Revisa qué dependencia falta: PyQt6, QtSvg, psutil o el entorno virtual. Esta guía se aplica principalmente a instalaciones desde código.

Reinstala el RPM de la app mediante el flujo Bazzite y arranca en el despliegue que lo contiene. Las dependencias del host no se reparan con dnf dentro de Toolbx.

Cierra y vuelve a abrir Control Center. La interfaz debe cargar sin indicar que el entorno gráfico de Python está incompleto.

*Fedora*

Revisa qué dependencia falta: PyQt6, QtSvg, psutil o el entorno virtual. Esta guía se aplica principalmente a instalaciones desde código.

Instala las dependencias con el gestor de tu distribución o reinstala su paquete oficial de Control Center para que las prepare.

```bash
sudo dnf install python3-pyqt6 qt6-qtsvg python3-psutil python3-pip
```

Cierra y vuelve a abrir Control Center. La interfaz debe cargar sin indicar que el entorno gráfico de Python está incompleto.

*Ubuntu / Mint, Debian*

Revisa qué dependencia falta: PyQt6, QtSvg, psutil o el entorno virtual. Esta guía se aplica principalmente a instalaciones desde código.

Instala las dependencias con el gestor de tu distribución o reinstala su paquete oficial de Control Center para que las prepare.

```bash
sudo apt install python3-pyqt6 python3-pyqt6.qtsvg python3-psutil python3-venv
```

Cierra y vuelve a abrir Control Center. La interfaz debe cargar sin indicar que el entorno gráfico de Python está incompleto.


<a id="inst-08"></a>
#### INST-08 · La interfaz y el ayudante protegido son de versiones distintas

`BC250-PROTOCOL-001`, `BC250-PERM-001` · estado: lo resuelve el usuario · visto en: Linux Mint · 6 reportes, último el 2026-11-16

**Qué se ve.** Acciones como Memoria y swap u Opciones de arranque del kernel fallan con BC250-PROTOCOL-001 y la salida muestra «usage: bc250-system-setup-helper …»: el ayudante no reconoce la opción que le pidió la interfaz.

**Por qué pasa.** La interfaz se actualizó (o se ejecuta desde una carpeta de código) pero el ayudante privilegiado de /usr/libexec/bc250-control-center es de otra versión, o se instaló a mano y quedó a medias.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si estás ejecutando la app desde una carpeta de código mientras los ayudantes pertenecen a otro paquete instalado.

Reinstala el paquete de la misma versión que la interfaz. En Bazzite, arranca en el despliegue que contiene esa instalación; en SteamOS, usa el reinstalador después de una actualización del sistema.

Vuelve a abrir la app y repite la acción. Si persiste el aviso de versiones distintas, incluye las versiones instaladas en el nuevo reporte.


<a id="inst-09"></a>
#### INST-09 · Falta un ayudante protegido o no pasa su comprobación de seguridad

`BC250-HELPER-001`, `BC250-SERVICE-003`, `BC250-CONFIG-001`, `BC250-GENERAL-001`, `BC250-WORKFLOW-001` · estado: lo resuelve el usuario · visto en: Linux Mint, SteamOS, Winux 11.26.11, CachyOS, Bazzite · 7 reportes, último el 2026-11-18

**Qué se ve.** Unidades de cómputo, ACPI, perfiles de CPU o la curva de voltaje se niegan con uno de los mensajes de arriba.

**Por qué pasa.** El ayudante root (/usr/libexec/bc250-control-center/… o /var/lib/bc250-control-center/…) no existe, no es de root, tiene permisos de escritura de grupo u otros, o pertenece a un despliegue inmutable que aún no arrancó. Pasa con install-local.sh, con instalaciones a medias, o en Bazzite/SteamOS antes de reiniciar.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si el aviso dice que falta un ayudante o que su instalación no es de confianza. Revisa si hay un despliegue todavía pendiente.

Reinstala Control Center mediante el paquete correspondiente a tu distribución. Mantén los permisos que instala el paquete; no copies un ayudante suelto.

Aplica el reinicio que solicite la instalación, abre de nuevo la app y repite la acción que estaba bloqueada.


<a id="inst-10"></a>
#### INST-10 · Linux negó el acceso a un archivo o dispositivo necesario

`BC250-PERM-001`, `BC250-PERM-002`, `BC250-FAN-001` · estado: lo resuelve el usuario · visto en: Bazzite, CachyOS · 6 reportes, último el 2026-11-10

**Qué se ve.** HelixSR (red, generación de fotogramas), FSR4/OptiScaler, desbloqueo de 8 núcleos, PWM de ventiladores, unidades de cómputo o la actualización fallan con BC250-PERM-001.

**Por qué pasa.** Un ayudante de la app no tiene permiso sobre un archivo o dispositivo. Suele deberse a un ayudante de otra versión, a un despliegue de Bazzite o SteamOS que espera un reinicio, a una denegación de SELinux, a archivos de un juego creados por otro usuario o por Flatpak, o a que el usuario que llega a polkit no es el que lanzó la acción.

**Cómo se arregla.**

*Todas las distribuciones*

Abre el detalle del error y anota la ruta exacta y la operación que Linux rechazó. Comprueba si es un archivo del juego o un ayudante de la app.

Si es un ayudante, reinstala la misma versión de la app. Si es una carpeta de juego, revisa su propietario y los permisos de acceso de Steam o Flatpak a esa carpeta.

Repite la misma acción. Si se vuelve a denegar, guarda la ruta y la salida reciente; en Fedora/Bazzite comprueba también la denegación de SELinux.


### Autorización (polkit, sudo)

<a id="auth-01"></a>
#### AUTH-01 · La autorización de administrador no se completó

`BC250-AUTH-002`, `BC250-UPSTREAM-404`, `BC250-DATA-001`, `BC250-BUSY-001`, `BC250-GPU-900`, `BC250-BUILD-003`, `BC250-PROTOCOL-001`, `BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: CachyOS, Bazzite, SteamOS · 9 reportes, último el 2026-11-20

**Qué se ve.** La acción termina sin hacer nada tras Error executing command as another user: Not authorized o sudo: a password is required.

**Por qué pasa.** 1) El usuario cerró o canceló la ventana de contraseña. 2) No hay agente de polkit (Hyprland, Sway, sesiones mínimas), así que la ventana nunca aparece. 3) sudo se pidió sin terminal (reinicio de Cyan en segundo plano) o la contraseña tardó más del límite.

**Cómo se arregla.**

*Todas las distribuciones*

Repite la acción y comprueba si aparece una ventana de contraseña. El comando permite comprobar si pkexec está instalado.

```bash
command -v pkexec
```

Completa la contraseña sin cerrar el diálogo. En Hyprland/Sway/niri comprueba que se inicie un agente polkit de la sesión; en Gaming Mode cambia a Modo Escritorio.

La acción debe continuar tras autenticarte. Si nunca aparece el diálogo, indica qué escritorio utilizas y que pkexec existe al enviar el reporte.


### Gestores de paquetes y repositorios

<a id="pkg-01"></a>
#### PKG-01 · El gestor de paquetes está bloqueado (pacman o apt)

`BC250-PKG-001`, `BC250-UPSTREAM-404`, `BC250-WORKFLOW-001` · estado: corregido · desde la 1.22.7 · visto en: CachyOS, SteamOS · 13 reportes, último el 2026-11-21

**Qué se ve.** La instalación falla con «could not lock database» o «failed to synchronize all databases (unable to lock database)» en pacman, o con «Could not get lock /var/lib/dpkg/lock-frontend» en apt.

**Por qué pasa.** 1) Otro gestor de paquetes está corriendo (pacman, yay, paru, Discover, la actualización automática de CachyOS). 2) Una actualización anterior se cortó (corte de luz, ventana cerrada) y dejó /var/lib/pacman/db.lck.

**Cómo se arregla.**

*Arch / CachyOS, SteamOS*

Comprueba si pacman, yay, paru u otro gestor sigue trabajando. Espera a esa operación antes de intentar otra instalación.

```bash
ps -C pacman,yay,paru,pamac,apt,apt-get,dpkg,dnf -o pid,comm
```

En Arch/CachyOS/SteamOS usa «Liberar el bloqueo de pacman» desde Compatibilidad; la app comprueba si es un bloqueo huérfano. En otros gestores, deja terminar la actualización activa.

Cuando no quede otro gestor activo, repite la instalación. Si el bloqueo regresa, conserva el nombre y PID del proceso que lo mantiene.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

```bash
ps -C pacman,yay,paru,pamac,apt,apt-get,dpkg,dnf -o pid,comm
```

Espera a que termine la transacción rpm-ostree. Consulta su estado y vuelve a instalar cuando quede libre; este gestor no utiliza el db.lck de pacman.

Cuando no quede otro gestor activo, repite la instalación. Si el bloqueo regresa, conserva el nombre y PID del proceso que lo mantiene.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

```bash
ps -C pacman,yay,paru,pamac,apt,apt-get,dpkg,dnf -o pid,comm
```

Espera a dnf/PackageKit. Comprueba qué operación mantiene ocupada la base RPM antes de volver a instalar.

Cuando no quede otro gestor activo, repite la instalación. Si el bloqueo regresa, conserva el nombre y PID del proceso que lo mantiene.

*Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

```bash
ps -C pacman,yay,paru,pamac,apt,apt-get,dpkg,dnf -o pid,comm
```

Deja terminar apt/dpkg/unattended-upgrades. Si la configuración quedó interrumpida, usa dpkg --configure -a solo después de que el gestor esté libre.

Cuando no quede otro gestor activo, repite la instalación. Si el bloqueo regresa, conserva el nombre y PID del proceso que lo mantiene.


<a id="pkg-02"></a>
#### PKG-02 · SteamOS no puede quitar el bloqueo de su base de paquetes

`BC250-GENERAL-001` · estado: corregido · visto en: SteamOS · 1 reporte, último el 2026-11-08

**Qué se ve.** Instalar Mesa RADV en SteamOS termina con warning: could not remove lock file /usr/lib/holo/pacmandb/db.lck.

**Por qué pasa.** La protección de solo lectura de SteamOS volvió a activarse (o nunca se desactivó) mientras pacman trabajaba en /usr.

**Cómo se arregla.**

*SteamOS*

Confirma que la ruta del aviso sea /usr/lib/holo/pacmandb/db.lck y que no haya una instalación de pacman activa.

Repite la instalación desde el flujo SteamOS de Control Center para que gestione la protección de la raíz. Si la acción anterior se interrumpió, reinicia primero.

La operación debe crear y retirar su bloqueo al terminar. Si vuelve a fallar, conserva la salida de findmnt y del flujo SteamOS.


<a id="pkg-03"></a>
#### PKG-03 · No se pueden sincronizar las bases de paquetes (red, espejo o repositorio de MastaG)

`BC250-UPSTREAM-404`, `BC250-WORKFLOW-001`, `BC250-GENERAL-001`, `BC250-PKG-005` · estado: corregido · visto en: SteamOS, CachyOS · 8 reportes, último el 2026-11-20

**Qué se ve.** Instalar el kernel BC-250, Mesa o actualizar falla al sincronizar: error: failed to synchronize all databases (unexpected error).

**Por qué pasa.** Sin red o DNS, un espejo caído, la base local más vieja que los espejos (404), o el repositorio de MastaG (GitHub Releases) no disponible un momento.

**Cómo se arregla.**

*Arch / CachyOS*

Identifica la URL o el espejo que falla. Comprueba primero la resolución de nombres y el acceso a ese servidor.

```bash
getent hosts github.com
```

Actualiza los índices con el gestor correspondiente. En Arch, completa una actualización coherente del sistema; si falla un espejo, selecciona otro de la misma distribución. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu
```

Vuelve a instalar. Si el servidor sigue devolviendo 404 o un error de red, conserva su URL y prueba más tarde.

*SteamOS*

Identifica la URL o el espejo que falla. Comprueba primero la resolución de nombres y el acceso a ese servidor.

```bash
getent hosts github.com
```

Repite la preparación SteamOS con la red disponible. Si falla un servidor de Valve, espera a su recuperación en vez de reemplazar sus repositorios por los de Arch.

Vuelve a instalar. Si el servidor sigue devolviendo 404 o un error de red, conserva su URL y prueba más tarde.

*Bazzite*

Identifica la URL o el espejo que falla. Comprueba primero la resolución de nombres y el acceso a ese servidor.

```bash
getent hosts github.com
```

Actualiza los índices con el gestor correspondiente. En Arch, completa una actualización coherente del sistema; si falla un espejo, selecciona otro de la misma distribución.

```bash
rpm-ostree refresh-md --force
```

Vuelve a instalar. Si el servidor sigue devolviendo 404 o un error de red, conserva su URL y prueba más tarde.

*Fedora*

Identifica la URL o el espejo que falla. Comprueba primero la resolución de nombres y el acceso a ese servidor.

```bash
getent hosts github.com
```

Actualiza los índices con el gestor correspondiente. En Arch, completa una actualización coherente del sistema; si falla un espejo, selecciona otro de la misma distribución.

```bash
sudo dnf makecache --refresh
```

Vuelve a instalar. Si el servidor sigue devolviendo 404 o un error de red, conserva su URL y prueba más tarde.

*Ubuntu / Mint, Debian*

Identifica la URL o el espejo que falla. Comprueba primero la resolución de nombres y el acceso a ese servidor.

```bash
getent hosts github.com
```

Actualiza los índices con el gestor correspondiente. En Arch, completa una actualización coherente del sistema; si falla un espejo, selecciona otro de la misma distribución.

```bash
sudo apt update
```

Vuelve a instalar. Si el servidor sigue devolviendo 404 o un error de red, conserva su URL y prueba más tarde.


<a id="pkg-04"></a>
#### PKG-04 · El servidor de paquetes de SteamOS no responde (504 / timeout)

`BC250-GENERAL-001`, `BC250-IMMUTABLE-001` · estado: lo resuelve el usuario · visto en: SteamOS · 2 reportes, último el 2026-11-09

**Qué se ve.** Instalar Mesa RADV o stress en SteamOS falla descargando de steamdeck-packages.steamos.cloud.

**Por qué pasa.** Fallo temporal del servidor de Valve o de la red.

**Cómo se arregla.**

*Arch / CachyOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Una descarga puede tener 504, pero este host es de SteamOS; diagnosticar la URL real como red, no añadir los repos de Valve.

La descarga debe completar su verificación antes de instalar. Si el mismo servidor sigue sin responder, vuelve a intentarlo más tarde.

*SteamOS*

Confirma que el error 504 o timeout corresponde a steamdeck-packages.steamos.cloud, no a una firma inválida.

```bash
getent hosts steamdeck-packages.steamos.cloud
```

Espera unos minutos y repite el flujo SteamOS. Comprueba que puedes acceder al servidor antes de cambiar llaves o paquetes.

La descarga debe completar su verificación antes de instalar. Si el mismo servidor sigue sin responder, vuelve a intentarlo más tarde.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Un 504 de otro repositorio es equivalente de red (NET-01/GFX-03), no un problema de pacman de SteamOS.

La descarga debe completar su verificación antes de instalar. Si el mismo servidor sigue sin responder, vuelve a intentarlo más tarde.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Un 504 de otro repositorio es equivalente de red; reintentar el flujo correspondiente.

La descarga debe completar su verificación antes de instalar. Si el mismo servidor sigue sin responder, vuelve a intentarlo más tarde.

*Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Un 504 de otra fuente apt es equivalente de red; no usar comandos de pacman.

La descarga debe completar su verificación antes de instalar. Si el mismo servidor sigue sin responder, vuelve a intentarlo más tarde.


<a id="pkg-05"></a>
#### PKG-05 · Un paquete descargado llegó dañado (checksum)

`BC250-PKG-006`, `BC250-PKG-002` · estado: corregido en desarrollo (falta publicar) · visto en: CachyOS · 1 reporte, último el 2026-11-15

**Qué se ve.** Instalar el kernel BC-250: pacman dice que linux-cachyos-bc250-…pkg.tar.zst is corrupted y cada reintento falla igual.

**Por qué pasa.** Descarga cortada o el repositorio de MastaG volvió a publicar el archivo con la misma versión. Si al "Do you want to delete it?" se responde n, pacman reutiliza la copia dañada para siempre.

**Cómo se arregla.**

*Arch / CachyOS*

Busca el nombre del archivo y confirma que el aviso diga checksum o «invalid or corrupted package».

En pacman responde y cuando pregunte si debe borrar el archivo dañado. Repite la descarga; en apt/dnf el comando de limpieza retira archivos descargados, no programas instalados.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.

*SteamOS*

Busca el nombre del archivo y confirma que el aviso diga checksum o «invalid or corrupted package».

En el pacman de SteamOS acepta retirar la descarga dañada cuando lo pregunte y repite el flujo SteamOS. Solo se retira ese archivo descargado.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Vuelve a descargar mediante el flujo de Bazzite y conserva la verificación. Si el archivo del origen sigue siendo inconsistente, espera a que el repositorio lo corrija.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar la limpieza de paquetes descargados dnf y volver a descargar el paquete afectado.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.

*Ubuntu / Mint*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Limpiar la descarga apt afectada y repetir desde la fuente correcta; mantener verificación.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.

*Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Limpiar la descarga apt afectada y repetir desde su fuente Debian; mantener verificación.

Repite la instalación. Si una nueva descarga falla con la misma suma, espera a que el repositorio publique un archivo correcto.


<a id="pkg-06"></a>
#### PKG-06 · La instalación del kernel + Mesa de MastaG se corta en la confirmación de pacman

`BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: CachyOS · 6 reportes, último el 2026-11-07

**Qué se ve.** El log termina en looking for conflicting packages… o en :: Proceed with installation? [Y/n] yy sin instalar nada.

**Por qué pasa.** pacman no recibió una respuesta afirmativa válida en «Proceed with installation? [Y/n]» (por ejemplo, se escribió «yy», que pacman toma como «no»), o la terminal se cerró en esa pregunta. No es un conflicto de paquetes: no se instaló nada.

**Cómo se arregla.**

*Arch / CachyOS*

Busca la última pregunta «Proceed with installation? [Y/n]». Si la salida termina allí o se respondió yy, la instalación no recibió un Sí válido.

Repite la instalación y escribe una sola y. Pulsa Enter únicamente cuando la opción por defecto sea Sí; revisa antes la lista de reemplazos o retiradas.

Espera al resumen final del gestor. Si vuelve a detenerse sin instalar, conserva la pregunta y la respuesta exactas del nuevo intento.

*SteamOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Pacman también pregunta en SteamOS. Para el caso genérico de cancelación, responder correctamente dentro del flujo SteamOS; la instalación MastaG descrita es de Arch/CachyOS.

Espera al resumen final del gestor. Si vuelve a detenerse sin instalar, conserva la pregunta y la respuesta exactas del nuevo intento.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Repite el flujo Bazzite y acepta su confirmación solo después de revisar los paquetes. Una cancelación no exige reparar pacman.

Espera al resumen final del gestor. Si vuelve a detenerse sin instalar, conserva la pregunta y la respuesta exactas del nuevo intento.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

En dnf, una respuesta negativa también cancela la instalación. Repite únicamente si deseas instalar y revisa su propia pregunta de confirmación.

Espera al resumen final del gestor. Si vuelve a detenerse sin instalar, conserva la pregunta y la respuesta exactas del nuevo intento.

*Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Repite apt si deseas instalar y responde a su propia confirmación después de revisar los cambios.

Espera al resumen final del gestor. Si vuelve a detenerse sin instalar, conserva la pregunta y la respuesta exactas del nuevo intento.


<a id="pkg-07"></a>
#### PKG-07 · pacman se saltó las cabeceras del kernel BC-250

`BC250-WORKFLOW-001` · estado: corregido · visto en: Arch Linux · 1 reporte, último el 2026-11-09

**Qué se ve.** ERROR: linux-cachyos-bc250-headers was not verified as the installed bc250-cachyos build.

**Por qué pasa.** pacman ofreció saltar un paquete por una dependencia sin resolver y se respondió que sí.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si el aviso nombra linux-cachyos-bc250-headers. El kernel y sus cabeceras deben instalarse juntos.

Actualiza el sistema y resuelve la dependencia que falta. Repite la instalación sin aceptar que se salten las cabeceras. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu
```

Comprueba que el instalador verifica ambos paquetes. Conserva el kernel anterior como opción de arranque hasta probar el nuevo.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar FAN-02: deben corresponder al kernel del despliegue activo.

Comprueba que el instalador verifica ambos paquetes. Conserva el kernel anterior como opción de arranque hasta probar el nuevo.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar FAN-02 y kernel-devel exacto.

Comprueba que el instalador verifica ambos paquetes. Conserva el kernel anterior como opción de arranque hasta probar el nuevo.

*Ubuntu / Mint*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar FAN-02 y linux-headers del kernel activo.

Comprueba que el instalador verifica ambos paquetes. Conserva el kernel anterior como opción de arranque hasta probar el nuevo.

*Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar FAN-02 y linux-headers de la ABI/kernel activo.

Comprueba que el instalador verifica ambos paquetes. Conserva el kernel anterior como opción de arranque hasta probar el nuevo.


<a id="pkg-08"></a>
#### PKG-08 · No existe el repositorio [cachyos-v3] (Proton BC-250)

`BC250-WORKFLOW-001` · estado: lo resuelve el usuario · visto en: CachyOS · 1 reporte, último el 2026-10-31

**Qué se ve.** Instalar Proton BC-250 en CachyOS falla porque no encuentra [cachyos-v3] en pacman.conf.

**Por qué pasa.** El CachyOS del usuario usa otro nivel de repositorio (cachyos-v4, cachyos-znver4 o solo cachyos) o un pacman.conf modificado. La app se niega a adivinar dónde poner el repositorio de MastaG.

**Cómo se arregla.**

*Arch / CachyOS*

Lista los repositorios habilitados y comprueba si estás usando CachyOS o una distribución Arch distinta.

```bash
pacman-conf --repo-list
```

En CachyOS, recupera su configuración de repositorios compatible con la BC-250. En Arch, elige la opción Arch de la app. El nombre de un ancla no justifica instalar paquetes para otra CPU.

Repite Proton BC-250. Si la app sigue rechazando el ancla, incluye el listado de repositorios en un reporte.


<a id="pkg-09"></a>
#### PKG-09 · Falta el paquete stress (OC de CPU)

`BC250-PKG-004` · estado: lo resuelve el usuario · visto en: Bazzite

**Qué se ve.** Al usar el OC de CPU (o una acción que lo arrastra, como la pantalla Thermalright) sale stress is missing. Press Prepare dependencies….

**Por qué pasa.** stress no está instalado; en Bazzite queda "en capas" y solo existe tras reiniciar.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si el programa stress está disponible en este arranque.

```bash
command -v stress
```

Instálalo con el comando de tu distribución o con Preparar dependencias. Si Bazzite lo añade al próximo despliegue, reinicia antes de probar la CPU. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu stress
```

Vuelve a la sección CPU y comprueba que la prueba pueda iniciarse. Si el aviso apareció en Thermalright, indícalo en un reporte separado.

```bash
command -v stress
```

*SteamOS*

Comprueba si el programa stress está disponible en este arranque.

```bash
command -v stress
```

Instálalo con el comando de tu distribución o con Preparar dependencias. Si Bazzite lo añade al próximo despliegue, reinicia antes de probar la CPU.

Vuelve a la sección CPU y comprueba que la prueba pueda iniciarse. Si el aviso apareció en Thermalright, indícalo en un reporte separado.

```bash
command -v stress
```

*Bazzite*

Comprueba si el programa stress está disponible en este arranque.

```bash
command -v stress
```

Instálalo con el comando de tu distribución o con Preparar dependencias. Si Bazzite lo añade al próximo despliegue, reinicia antes de probar la CPU. Al terminar rpm-ostree, reinicia en el nuevo despliegue antes de verificar.

```bash
rpm-ostree install stress
```

Vuelve a la sección CPU y comprueba que la prueba pueda iniciarse. Si el aviso apareció en Thermalright, indícalo en un reporte separado.

```bash
command -v stress
```

*Fedora*

Comprueba si el programa stress está disponible en este arranque.

```bash
command -v stress
```

Instálalo con el comando de tu distribución o con Preparar dependencias. Si Bazzite lo añade al próximo despliegue, reinicia antes de probar la CPU.

```bash
sudo dnf install stress
```

Vuelve a la sección CPU y comprueba que la prueba pueda iniciarse. Si el aviso apareció en Thermalright, indícalo en un reporte separado.

```bash
command -v stress
```

*Ubuntu / Mint, Debian*

Comprueba si el programa stress está disponible en este arranque.

```bash
command -v stress
```

Instálalo con el comando de tu distribución o con Preparar dependencias. Si Bazzite lo añade al próximo despliegue, reinicia antes de probar la CPU.

```bash
sudo apt install stress
```

Vuelve a la sección CPU y comprueba que la prueba pueda iniciarse. Si el aviso apareció en Thermalright, indícalo en un reporte separado.

```bash
command -v stress
```


<a id="pkg-10"></a>
#### PKG-10 · La PPA kisak-mesa no ofrece un Mesa más nuevo para esta versión de Ubuntu/Mint

`BC250-WORKFLOW-001`, `BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: Ubuntu, Linux Mint · 1 reporte, último el 2026-10-28

**Qué se ve.** "Mesa · kisak-mesa PPA" falla: la Mesa más nueva disponible es vacía o más vieja que la que se necesita.

**Por qué pasa.** La PPA de kisak todavía no publica paquetes para esa versión de Ubuntu (26.04) o para la base de Linux Mint.

**Cómo se arregla.**

*Ubuntu / Mint*

Comprueba la base Ubuntu de tu instalación y qué versión de Mesa ofrece la PPA. En Mint, revisa su versión de Ubuntu base.

```bash
cat /etc/os-release
apt-cache policy mesa-vulkan-drivers
```

Si kisak no publica para esa base, mantén Mesa de la distribución y espera un build compatible. No añadas una PPA de otra versión para superar el aviso.

La acción solo debe ofrecerse cuando exista una versión compatible. Puedes seguir usando Mesa de la distribución mientras tanto.


<a id="pkg-11"></a>
#### PKG-11 · pacman: «database already registered» (repositorio duplicado)

`BC250-PKG-007`, `BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: arch · 3 reportes, último el 2026-11-20

**Qué se ve.** La actualización de Control Center (paru/yay) o una instalación con pacman se detiene con «error: database already registered».

**Por qué pasa.** El mismo repositorio está definido dos veces: en /etc/pacman.conf y otra vez en un archivo incluido, o en una sección añadida a mano. pacman se detiene antes de instalar nada.

**Cómo se arregla.**

*Arch / CachyOS, SteamOS*

Lista los repositorios repetidos.

```bash
pacman-conf --repo-list | sort | uniq -d
```

Busca dónde está definido cada uno: en /etc/pacman.conf y en los archivos de /etc/pacman.d.

```bash
grep -rn '^\[' /etc/pacman.conf /etc/pacman.d
```

Edita el archivo y deja solo una de las dos secciones (o la línea Include que la repite); luego vuelve a ejecutar la acción.

```bash
sudoedit /etc/pacman.conf
```


### Almacenamiento

<a id="stor-01"></a>
#### STOR-01 · SteamOS: /var sin espacio

`BC250-STORAGE-001`, `BC250-WORKFLOW-001` · estado: corregido · desde la 1.22.7 · visto en: SteamOS · 2 reportes, último el 2026-11-11

**Qué se ve.** Preparar dependencias o instalar el acceso rápido de Modo Juego en SteamOS se detiene pidiendo liberar espacio.

**Por qué pasa.** En SteamOS /var es una partición pequeña (unos 230 MB). Logs del sistema, caché de pacman y metadatos de firmware la llenan.

**Cómo se arregla.**

*Arch / CachyOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Revisa qué sistema de archivos está lleno con df. Usa la limpieza de caché de tu distribución y retira solo descargas o registros que ya no necesites.

Comprueba de nuevo el espacio libre y repite la preparación. Si /var se llena enseguida, identifica el archivo o servicio que vuelve a ocuparlo.

*SteamOS*

Comprueba cuánto espacio queda en /var y cuánto ocupan los registros del sistema.

```bash
df -h /var
journalctl --disk-usage
```

Abre Panel › Preparar sistema › Liberar espacio de /var. Revisa la limpieza propuesta; los registros y cachés que se retiren no son programas instalados.

Comprueba de nuevo el espacio libre y repite la preparación. Si /var se llena enseguida, identifica el archivo o servicio que vuelve a ocuparlo.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Revisa el uso real del volumen y las cachés de tu imagen. El tamaño reducido de /var descrito en SteamOS no es una característica de Bazzite.

Comprueba de nuevo el espacio libre y repite la preparación. Si /var se llena enseguida, identifica el archivo o servicio que vuelve a ocuparlo.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Localiza la partición llena con df y revisa sus registros y cachés dnf. No uses la limpieza de pacman de SteamOS.

Comprueba de nuevo el espacio libre y repite la preparación. Si /var se llena enseguida, identifica el archivo o servicio que vuelve a ocuparlo.

*Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Localiza la partición llena con df y revisa sus registros y descargas apt. No necesitas asumir una partición /var pequeña.

Comprueba de nuevo el espacio libre y repite la preparación. Si /var se llena enseguida, identifica el archivo o servicio que vuelve a ocuparlo.


<a id="stor-02"></a>
#### STOR-02 · Disco lleno al instalar un paquete grande (Write failed / No space left on device)

`BC250-STORAGE-001`, `BC250-GENERAL-001` · estado: corregido en desarrollo (falta publicar) · visto en: CachyOS

**Qué se ve.** Al instalar el Proton BC-250 (o cualquier paquete grande), pacman muestra decenas de «could not extract … (Write failed)» y la transacción se aborta.

**Por qué pasa.** El sistema de archivos donde se instala (normalmente / o /usr) se quedó sin espacio a mitad de la extracción. El paquete de Proton ocupa varios GB y la descarga ya había llenado la caché de pacman.

**Cómo se arregla.**

*Arch / CachyOS, SteamOS*

Mira qué partición está llena y cuánto espacio libre queda.

```bash
df -h / /var /usr /home
```

Libera espacio: vacía la caché de paquetes que ya no necesitas y recorta el registro del sistema.

```bash
sudo pacman -Sc
```

```bash
sudo journalctl --vacuum-size=200M
```

Repite la instalación del Proton BC-250 desde Ajustes adicionales. Necesita varios GB libres en /.

*Bazzite, Fedora, Ubuntu / Mint, Debian*

Mira qué partición está llena y cuánto espacio libre queda.

```bash
df -h / /var /usr /home
```

Libera espacio: vacía la caché de paquetes que ya no necesitas y recorta el registro del sistema.

```bash
sudo journalctl --vacuum-size=200M
```

Repite la instalación del Proton BC-250 desde Ajustes adicionales. Necesita varios GB libres en /.


### Gobernador de GPU (Cyan y Oberon)

<a id="gov-01"></a>
#### GOV-01 · La configuración de Cyan tiene una clave repetida (Cannot declare … twice)

`BC250-GENERAL-001`, `BC250-DBUS-001`, `BC250-GPU-001` · estado: corregido · visto en: Bazzite · 10 reportes, último el 2026-11-08

**Qué se ve.** Preparar dependencias o cambiar la compatibilidad de Cyan falla leyendo el TOML.

**Por qué pasa.** Una sección ([gpu-usage]) o una clave (fix-freq) aparece dos veces en el TOML, normalmente porque una versión anterior de la app o una edición a mano añadió el bloque otra vez.

**Cómo se arregla.**

*Todas las distribuciones*

El archivo está en /etc/cyan-skillfish-governor-smu/config.toml. Guarda una copia con fecha antes de editarlo; sudoedit abrirá una copia temporal en el editor de tu sesión.

```bash
sudo cp -a -- /etc/cyan-skillfish-governor-smu/config.toml \
  "/etc/cyan-skillfish-governor-smu/config.toml.bak-$(date +%Y%m%d-%H%M%S)" &&
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
```

Busca la tabla o clave que el error indica como duplicada. Conserva una sola definición con el valor que deseas utilizar; no cambies el resto de la curva de voltaje.

En un sistema con systemd, este comando valida el TOML y solo reinicia Cyan si aparece «TOML OK». Si falla la validación, corrige la línea indicada y vuelve a comprobarla. Cierra las cargas 3D antes de reiniciar el gobernador.

```bash
python3 -c 'import tomllib; tomllib.load(open("/etc/cyan-skillfish-governor-smu/config.toml", "rb")); print("TOML OK")' &&
sudo systemctl restart cyan-skillfish-governor-smu &&
systemctl status cyan-skillfish-governor-smu --no-pager
```

El servicio debe indicar active (running). Con otro gestor de servicios, ejecuta solo la primera línea para validar el archivo y reinicia el gobernador desde Control Center.


<a id="gov-02"></a>
#### GOV-02 · La configuración de Cyan reescribe un valor (Cannot overwrite a value)

`BC250-CONFIG-001` · estado: lo resuelve el usuario · visto en: CachyOS · 3 reportes, último el 2026-11-07

**Qué se ve.** Preparar dependencias se detiene porque el TOML de Cyan no es válido.

**Por qué pasa.** Una clave escalar y una tabla con el mismo nombre (por ejemplo gpu-usage = … y luego [gpu-usage]), casi siempre por edición manual o una guía externa.

**Cómo se arregla.**

*Todas las distribuciones*

El archivo está en /etc/cyan-skillfish-governor-smu/config.toml. Guarda una copia con fecha antes de editarlo; sudoedit abrirá una copia temporal en el editor de tu sesión.

```bash
sudo cp -a -- /etc/cyan-skillfish-governor-smu/config.toml \
  "/etc/cyan-skillfish-governor-smu/config.toml.bak-$(date +%Y%m%d-%H%M%S)" &&
sudoedit /etc/cyan-skillfish-governor-smu/config.toml
```

Corrige la definición señalada por «Cannot overwrite a value». Una clave y una tabla no pueden usar el mismo nombre; por ejemplo, gpu-usage = … y [gpu-usage]. Conserva la configuración de voltaje que ya utilizabas.

En un sistema con systemd, este comando valida el TOML y solo reinicia Cyan si aparece «TOML OK». Si falla la validación, corrige la línea indicada y vuelve a comprobarla. Cierra las cargas 3D antes de reiniciar el gobernador.

```bash
python3 -c 'import tomllib; tomllib.load(open("/etc/cyan-skillfish-governor-smu/config.toml", "rb")); print("TOML OK")' &&
sudo systemctl restart cyan-skillfish-governor-smu &&
systemctl status cyan-skillfish-governor-smu --no-pager
```

El servicio debe indicar active (running). Con otro gestor de servicios, ejecuta solo la primera línea para validar el archivo y reinicia el gobernador desde Control Center.


<a id="gov-03"></a>
#### GOV-03 · Faltan puntos seguros (safe-points) en el TOML de Cyan

`BC250-CONFIG-001`, `BC250-GPU-900`, `BC250-WORKFLOW-001` · estado: corregido · desde la 1.22.7 · visto en: Bazzite, CachyOS · 3 reportes, último el 2026-11-03

**Qué se ve.** Cambiar la curva de voltaje o el rango de GPU se niega: faltan frecuencias en el TOML.

**Por qué pasa.** El TOML venía de una versión vieja de Cyan o de otra guía, sin los puntos que la app espera.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba qué frecuencias indica el aviso y si estás intentando usar puntos avanzados.

Actualiza la app y aplica de nuevo el perfil de voltaje para completar los puntos empaquetados. Activa los avanzados desde Compatibilidad solo si deseas usar esas frecuencias.

Vuelve a leer el rango y comprueba que Cyan reconoce cada frecuencia solicitada antes de guardar el perfil.


<a id="gov-04"></a>
#### GOV-04 · Cyan se detiene con Remote I/O error (código 121)

`BC250-WORKFLOW-001` · estado: lo resuelve el usuario · visto en: Bazzite · 1 reporte, último el 2026-10-29

**Qué se ve.** Activar Cyan falla y el servicio se reinicia en bucle.

**Por qué pasa.** El SMU no respondió al gobernador: SMU en un estado raro tras un cuelgue, otra herramienta usando el buzón del SMU, o firmware no compatible.

**Cómo se arregla.**

*Todas las distribuciones*

Consulta el registro de Cyan y busca «Remote I/O error» o el código 121.

```bash
journalctl -u cyan-skillfish-governor-smu -b -n 60 --no-pager
```

Apaga completamente la placa, desconecta la alimentación unos segundos y vuelve a arrancar. Inicia Cyan sin otra herramienta de CPU o GDDR6 accediendo al SMU.

Comprueba que Cyan permanece activo. Si vuelve el error 121, guarda el registro de este arranque y los datos de BIOS.


<a id="gov-05"></a>
#### GOV-05 · Se intentó activar Cyan antes de instalarlo

`BC250-GENERAL-001`, `BC250-SERVICE-002` · estado: corregido · visto en: Bazzite

**Qué se ve.** Failed to enable unit: Unit cyan-skillfish-governor-smu.service does not exist.

**Por qué pasa.** Cyan no estaba instalado, o en Bazzite estaba en capas sin reiniciar.

**Cómo se arregla.**

*Todas las distribuciones*

Consulta si existe la unidad cyan-skillfish-governor-smu.service.

```bash
systemctl status cyan-skillfish-governor-smu --no-pager
```

Abre Preparar dependencias y prepara Gobernador. En Bazzite completa el despliegue y su reinicio antes de iniciar el servicio.

Vuelve a la tarjeta del gobernador e inicia Cyan. La unidad debe existir y cambiar a estado conectado.

```bash
systemctl status cyan-skillfish-governor-smu --no-pager
```


<a id="gov-06"></a>
#### GOV-06 · La configuración de Cyan falta o no pertenece a root

`BC250-WORKFLOW-001`, `BC250-CU-001`, `BC250-GENERAL-001`, `BC250-GPU-900`, `BC250-PERM-001`, `BC250-GPU-007` · estado: corregido · visto en: Linux Mint · 3 reportes, último el 2026-11-10

**Qué se ve.** Iniciar Cyan, aplicar un perfil de GPU u otras acciones del governor fallan con «Governor configuration is unavailable» o «Governor configuration is not protected by root».

**Por qué pasa.** Falta /etc/cyan-skillfish-governor-smu/config.toml, o existe pero no pertenece a root. Suele pasar cuando Cyan se instaló a mano o a medias, fuera de la app. La app no usa una configuración que cualquier usuario podría cambiar, porque de ella dependen el voltaje y las frecuencias de la GPU.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba que config.toml existe en /etc/cyan-skillfish-governor-smu y que pertenece a root.

```bash
ls -l /etc/cyan-skillfish-governor-smu/config.toml
```

Abre Preparar dependencias › Gobernador para restaurar Cyan y su configuración. Si el error provenía de otra acción, confirma que el diagnóstico actual sigue señalando Cyan.

Inicia el gobernador y aplica un perfil ofrecido por la app. Si falta aún el archivo, adjunta la ruta y el resultado de la comprobación.


<a id="gov-07"></a>
#### GOV-07 · La GPU BC-250 no aparece donde Cyan la busca (o no se detecta)

`BC250-GENERAL-001`, `BC250-PROTOCOL-001`, `BC250-WORKFLOW-001`, `BC250-HW-001` · estado: lo resuelve el usuario · visto en: Linux Mint · 7 reportes, último el 2026-11-12

**Qué se ve.** Cyan no arranca con «Cyan Skillfish GPU not found at expected PCI bus location», o el arreglo GFX1013 dice «AMD BC-250 (PCI 1002:13fe) was not found».

**Por qué pasa.** El sistema no ve la GPU en 1002:13fe: amdgpu no cargó, la GPU está en otra ruta (máquina virtual, passthrough), o el equipo no es una BC-250.

**Cómo se arregla.**

*Todas las distribuciones*

Busca el dispositivo AMD con identificador 1002:13fe y comprueba qué driver utiliza.

```bash
lspci -nnk -d 1002:13fe
```

Si no aparece, realiza un apagado completo. Si aparece sin amdgpu, revisa el kernel y parámetros como nomodeset; usa el kernel compatible que ofrece tu distribución.

Vuelve a detectar el hardware desde la app. Si continúa ausente, conserva la salida PCI y el registro de amdgpu para soporte.

```bash
lspci -nnk -d 1002:13fe
```


<a id="gov-08"></a>
#### GOV-08 · El driver amdgpu no arrancó en este arranque

`BC250-WORKFLOW-001` · estado: corregido · visto en: Fedora · 3 reportes, último el 2026-11-18

**Qué se ve.** Activar Cyan se niega: no hay nada que controlar.

**Por qué pasa.** El driver amdgpu no se cargó en este arranque. A veces pasa tras un reinicio en caliente de la BC-250, y pasa siempre que el arranque lleva nomodeset, amdgpu.modeset=0 o amdgpu en la lista negra. Fedora deja nomodeset si se instaló en «modo de gráficos básicos».

**Cómo se arregla.**

*Todas las distribuciones*

Consulta el registro de este arranque y localiza el primer fallo de amdgpu.

```bash
journalctl -k -b --no-pager | grep -i amdgpu
```

Revisa la línea de arranque. Si aparece nomodeset, amdgpu.modeset=0 o modprobe.blacklist=amdgpu, quítalo del gestor de arranque y reinicia. Si no aparece nada de eso, apaga la BC-250 por completo (no reiniciar) y vuelve a encenderla.

```bash
cat /proc/cmdline
```

Comprueba que amdgpu aparece como driver de la GPU antes de volver a activar Cyan.

```bash
lspci -nnk -d 1002:13fe
```


<a id="gov-09"></a>
#### GOV-09 · No se puede leer el rango de Cyan por D-Bus / Cyan no arranca en Bazzite

`BC250-GPU-900`, `BC250-DBUS-001` · estado: pendiente · visto en: Linux Mint, Bazzite · 2 reportes, último el 2026-11-11

**Qué se ve.** La curva de voltaje no se aplica; en Bazzite, instalar Cyan termina con el servicio en fallo.

**Por qué pasa.** Cyan no está corriendo o no publicó su interfaz D-Bus todavía. En Bazzite, el servicio puede arrancar antes que la GPU (Cyan v0.4.15 añade una regla udev y BindsTo para eso).

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba el estado del servicio y sus últimas líneas de este arranque.

```bash
systemctl status cyan-skillfish-governor-smu --no-pager
```

Inicia Cyan desde la tarjeta del gobernador y espera a «Conectado». Si el servicio se detiene, resuelve primero el primer error que aparezca en el registro.

Refresca el rango antes de aplicar la curva. Si solo falla tras reiniciar, conserva el registro de ese arranque.

```bash
journalctl -u cyan-skillfish-governor-smu -b -n 60 --no-pager
```


<a id="gov-10"></a>
#### GOV-10 · Cambiar el rango o la curva de GPU se rechaza (telemetría no disponible / Cyan apagado)

`BC250-GPU-900` · estado: corregido · visto en: Bazzite, CachyOS · 5 reportes, último el 2026-11-12

**Qué se ve.** "GPU range failed" con un traceback.

**Por qué pasa.** Con Oberon, la app exige ver la carga de GPU para cambiar el perfil sin riesgo; sin telemetría se niega. Con Cyan apagado, la curva de voltaje no se puede escribir.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba qué gobernador está activo y si la app puede leer la carga y el reloj de la GPU.

Cierra los juegos o cargas 3D, refresca la página e inicia Cyan si está apagado. Vuelve a aplicar un rango o perfil ofrecido por la app.

La curva debe aplicarse con telemetría disponible. Si la protección vuelve a rechazarla, conserva el estado y el mensaje actual.


<a id="gov-11"></a>
#### GOV-11 · Oberon: no se desinstala del todo, no compila o no arranca

`BC250-WORKFLOW-001`, `BC250-PROTOCOL-001` · estado: lo resuelve el usuario · visto en: CachyOS, SteamOS, Bazzite · 4 reportes, último el 2026-11-15

**Qué se ve.** Tres casos: la desinstalación deja el binario; en SteamOS la compilación de yaml-cpp falla; en Bazzite el servicio sale con error al instante.

**Por qué pasa.** Son tres casos distintos. Si al desinstalar queda el binario, es porque se instaló a mano fuera del paquete. En SteamOS la compilación falla con «features.h: No such file or directory» porque el sistema no trae las cabeceras de glibc que necesita yaml-cpp. En Bazzite el servicio puede salir al instante si no ve la GPU o si Cyan está activo a la vez.

**Cómo se arregla.**

*Todas las distribuciones*

Revisa la ruta del ejecutable y el primer error del registro. Distingue un fallo de compilación de un servicio que no arranca.

```bash
journalctl -u oberon-governor -b -n 60 --no-pager
```

Mantén activo un solo gobernador. Si queda un binario instalado a mano, comprueba primero a qué paquete pertenece; en el caso SteamOS descrito puedes usar Cyan.

Inicia el gobernador elegido desde la app y comprueba su estado. Si Oberon aún falla, conserva el primer error del journal o de la compilación.


<a id="gov-12"></a>
#### GOV-12 · Cyan no arranca solo al iniciar (Bazzite) y las frecuencias altas no se aplican

sin código · estado: pendiente · visto en: Bazzite · 1 reporte, último el 2026-11-15

**Qué se ve.** Aunque se marca "iniciar al arrancar", Cyan no arranca tras reiniciar; y para ver frecuencias altas hay que activar la compatibilidad.

**Por qué pasa.** Hay dos problemas distintos. Que Cyan no arranque solo suele deberse a que el servicio se inicia antes de que la GPU esté lista y se cierra (ver GOV-09). Que falten frecuencias altas es otra cosa: los puntos por encima de 2000 MHz no están activos en el TOML de Cyan (ver GOV-03).

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si la unidad está habilitada y si falló antes de que amdgpu estuviera disponible.

```bash
systemctl is-enabled cyan-skillfish-governor-smu
journalctl -u cyan-skillfish-governor-smu -b -n 60 --no-pager
```

Como alternativa temporal, inicia Cyan desde la app después de arrancar. Si faltan frecuencias, sigue también la guía de puntos seguros de Cyan.

En el próximo arranque comprueba de nuevo el estado. Si solo falla el inicio automático, conserva el journal de ese arranque para investigar el orden de servicios.


<a id="gov-13"></a>
#### GOV-13 · La verificación de Cyan rechazó un fix-freq válido (código 61)

`BC250-WORKFLOW-001` · estado: corregido en desarrollo (falta publicar) · visto en: arch · 1 reporte, último el 2026-11-17

**Qué se ve.** Preparar dependencias instala Cyan, dice que conservó el TOML y luego se detiene con «Cyan fix-freq is missing or invalid in config.toml» (código 61).

**Por qué pasa.** El instalador validaba el TOML con Python (tomllib), pero la verificación posterior de la app buscaba la línea con grep. Un TOML válido escrito de otra forma (clave entre comillas, clave con punto, tabla en línea) pasaba la primera y fallaba la segunda.

**Cómo se arregla.**

*Todas las distribuciones*

Mira qué valores tiene la sección [gpu-usage] del TOML de Cyan.

```bash
grep -n -A6 'gpu-usage' /etc/cyan-skillfish-governor-smu/config.toml
```

Comprueba que el archivo es TOML válido y que fix-freq es true o false; si no sale ningún error, el archivo está bien y basta con actualizar Control Center.

```bash
python3 -c "import tomllib; c=tomllib.load(open('/etc/cyan-skillfish-governor-smu/config.toml','rb')); print(c.get('gpu-usage'))"
```

Con la versión corregida, pulsa otra vez Preparar dependencias en el Panel.


### Unidades de cómputo (40 CU) y UMR

<a id="cu-01"></a>
#### CU-01 · UMR no está instalado

`BC250-CMD-001`, `BC250-CU-001`, `BC250-UMR-001` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite, Arch Linux · 5 reportes, último el 2026-11-15

**Qué se ve.** Unidades de cómputo dice que no encuentra UMR y no cambia nada.

**Por qué pasa.** UMR no se instaló o se desinstaló. En Bazzite queda en capas hasta reiniciar.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Instala UMR para tu distribución o prepáralo desde Panel › Preparar sistema › UMR. Mantén abierta la terminal hasta que termine. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu --needed umr || paru -S --needed umr
```

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```

*SteamOS*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Abre Panel › Preparar sistema, marca UMR y pulsa Preparar seleccionados. El flujo de la app gestiona el entorno de paquetes de SteamOS.

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```

*Bazzite*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Instala UMR con el comando. Al terminar, guarda tu trabajo y reinicia si rpm-ostree ha creado un despliegue nuevo; UMR estará disponible después de arrancar en él.

```bash
rpm-ostree install umr
```

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```

*Fedora*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Instala UMR para tu distribución o prepáralo desde Panel › Preparar sistema › UMR. Mantén abierta la terminal hasta que termine.

```bash
sudo dnf install umr
```

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```

*Ubuntu / Mint*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Prueba el paquete UMR de esta versión de Ubuntu. Si apt no lo encuentra, usa Panel › Preparar sistema › UMR › Preparar seleccionados para compilarlo.

```bash
sudo apt update && sudo apt install umr
```

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```

*Debian*

Comprueba si Linux encuentra el ejecutable umr. Si no aparece ninguna ruta, falta la herramienta que lee los registros de la GPU.

```bash
command -v umr
```

Prueba el paquete UMR de esta versión de Debian. Si apt no lo encuentra, usa la preparación de UMR de la app para compilarlo.

```bash
sudo apt update && sudo apt install umr
```

Comprueba que umr abre su ayuda y vuelve a sincronizar las unidades de cómputo desde la app antes de aplicar cambios.

```bash
umr --help
```


<a id="cu-02"></a>
#### CU-02 · UMR está instalado pero no funciona (LLVM)

`BC250-UMR-001`, `BC250-WORKFLOW-001`, `BC250-GENERAL-001` · estado: corregido · visto en: Arch Linux, CachyOS, Fedora · 2 reportes, último el 2026-11-20

**Qué se ve.** Unidades de cómputo no puede leer la máscara WGP y umr falla al abrir con «error while loading shared libraries: libLLVM…».

**Por qué pasa.** Una actualización del sistema cambió la versión de LLVM y UMR quedó enlazado a la vieja.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si umr existe pero al abrir su ayuda indica que falta libLLVM u otra biblioteca.

```bash
umr --help
```

Reinstala o recompila UMR contra las bibliotecas del sistema actual. Si lo instalaste desde código, usa Preparar seleccionados › UMR para reconstruirlo.

```bash
paru -S umr-git
```

La ayuda de umr debe abrir sin errores de bibliotecas. Después refresca y sincroniza las unidades de cómputo.

```bash
umr --help
```

*SteamOS*

Comprueba si umr existe pero al abrir su ayuda indica que falta libLLVM u otra biblioteca.

```bash
umr --help
```

Usa Preparar seleccionados › UMR para reconstruir la herramienta contra el entorno actual de SteamOS.

La ayuda de umr debe abrir sin errores de bibliotecas. Después refresca y sincroniza las unidades de cómputo.

```bash
umr --help
```

*Bazzite*

Comprueba si umr existe pero al abrir su ayuda indica que falta libLLVM u otra biblioteca.

```bash
umr --help
```

Actualiza la imagen y sus paquetes con rpm-ostree. Reinicia en el despliegue actualizado antes de comprobar UMR.

```bash
rpm-ostree upgrade
```

La ayuda de umr debe abrir sin errores de bibliotecas. Después refresca y sincroniza las unidades de cómputo.

```bash
umr --help
```

*Fedora*

Comprueba si umr existe pero al abrir su ayuda indica que falta libLLVM u otra biblioteca.

```bash
umr --help
```

Reinstala o recompila UMR contra las bibliotecas del sistema actual. Si lo instalaste desde código, usa Preparar seleccionados › UMR para reconstruirlo. El comando actualiza los paquetes del sistema antes de reinstalar UMR.

```bash
sudo dnf upgrade --refresh && sudo dnf reinstall umr
```

La ayuda de umr debe abrir sin errores de bibliotecas. Después refresca y sincroniza las unidades de cómputo.

```bash
umr --help
```

*Ubuntu / Mint, Debian*

Comprueba si umr existe pero al abrir su ayuda indica que falta libLLVM u otra biblioteca.

```bash
umr --help
```

Reinstala o recompila UMR contra las bibliotecas del sistema actual. Si lo instalaste desde código, usa Preparar seleccionados › UMR para reconstruirlo.

```bash
sudo apt update && sudo apt install --reinstall umr
```

La ayuda de umr debe abrir sin errores de bibliotecas. Después refresca y sincroniza las unidades de cómputo.

```bash
umr --help
```


<a id="cu-03"></a>
#### CU-03 · Máscara de núcleos distinta de 0x77: posibles núcleos defectuosos

`BC250-WORKFLOW-001`, `BC250-GPU-900`, `BC250-CU-001` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite, CachyOS · 1 reporte, último el 2026-11-14

**Qué se ve.** Desbloquear núcleos se detiene sin escribir nada y la salida dice «non-0x77 presence mask detected» o «unexpected core mask 0x…, expected 0x77».

**Por qué pasa.** De fábrica, la BC-250 tiene 6 de sus 8 núcleos activos, con la máscara 0x77: tres núcleos en cada grupo (CCX). La herramienta oficial solo desbloquea placas con esa máscara. Si la tuya lee otra, como 0xB7 o 0xE7, la fábrica apagó otros dos núcleos, y pudo hacerlo porque estaban defectuosos. Por eso la herramienta se niega a seguir.

**Cómo se arregla.**

*Todas las distribuciones*

Busca en el mensaje la máscara que leyó la herramienta («core presence mask: 0x…»). Este comando muestra cuántos núcleos e hilos tienes ahora.

```bash
lscpu
```

Ve a CPU › Zona de riesgo, elige esa misma máscara en «Máscara de núcleos de esta placa» y vuelve a desbloquear. La app solo continúa si la placa lee exactamente la máscara elegida; con cualquier otra se vuelve a negar.

Los dos núcleos que se activan no vienen probados de fábrica. Después de desbloquear, haz una prueba de estrés de unas horas y revisa el registro del kernel por errores de hardware (MCE). Si aparece alguno, vuelve a la configuración de fábrica.

```bash
sudo dmesg | grep -iE 'mce|machine check'
```

Si tu máscara no está en esa lista, deja la placa con sus núcleos de fábrica: la app no ofrece forzar otras máscaras.


### CPU (overclock, desbloqueo de núcleos, SMU)

<a id="cpu-01"></a>
#### CPU-01 · No hay un overclock.conf validado o falta el repositorio bc250_smu_oc

`BC250-CONFIG-001`, `BC250-CMD-001` · estado: lo resuelve el usuario · visto en: CachyOS · 2 reportes, último el 2026-11-19

**Qué se ve.** Instalar la persistencia del OC de CPU falla.

**Por qué pasa.** No se ejecutó antes la detección temporal de CPU (que genera y valida overclock.conf), o el repositorio de herramientas no se descargó.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si ya ejecutaste la detección temporal para esa frecuencia y si terminó correctamente.

Prepara las herramientas de CPU, ejecuta la detección temporal y verifica el resultado antes de pulsar Instalar persistencia.

Guarda la persistencia solo cuando exista un overclock.conf validado para ese resultado; después comprueba el estado del servicio.


### Memoria, swap, TTM y zswap

<a id="mem-01"></a>
#### MEM-01 · zswap solo se configura con /var en Btrfs (Bazzite)

`BC250-WORKFLOW-001` · estado: comportamiento esperado · visto en: Bazzite · 1 reporte, último el 2026-10-28

**Qué se ve.** Configurar memoria en Bazzite se detiene sin cambiar nada.

**Por qué pasa.** El /var del usuario no es Btrfs (instalación personalizada); el swapfile de la app necesita Btrfs con NOCOW.

**Cómo se arregla.**

*Arch / CachyOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

zswap en general no depende de ese flujo Bazzite; usar el backend de memoria de la distro y sus requisitos reales.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.

*SteamOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

```bash
findmnt -no FSTYPE /var
```

Usar el backend SteamOS; no trasladar la restricción Btrfs /var de Bazzite.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.

*Bazzite*

Comprueba el sistema de archivos de /var. El aviso corresponde al flujo de zswap que necesita Btrfs.

```bash
findmnt -no FSTYPE /var
```

Si /var no es Btrfs, selecciona zram en Memoria y swap o conserva un swap ya configurado para tu sistema de archivos.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.

*Fedora*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar el backend Fedora; verificar requisitos reales de swap/zswap, sin asumir la restricción Bazzite.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.

*Ubuntu / Mint*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar el backend Ubuntu y el swap disponible; no afirmar que zswap solo funciona en Btrfs.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.

*Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Usar el backend Debian; la limitación pertenece a esta implementación Bazzite, no a zswap en general.

Comprueba el estado de memoria después de aplicar la opción elegida. No necesitas reformatear /var para seguir usando zram.


<a id="mem-02"></a>
#### MEM-02 · El límite de memoria de GPU (TTM) es mayor que la RAM o no queda espacio para el swap

`BC250-WORKFLOW-001`, `BC250-TTM-001`, `BC250-STORAGE-001` · estado: comportamiento esperado · visto en: Bazzite · 2 reportes, último el 2026-11-17

**Qué se ve.** La configuración se niega por tamaño.

**Por qué pasa.** Con la VRAM reservada, el sistema tiene menos RAM de la que se pidió para TTM; o el disco no tiene espacio para el swapfile más el margen de seguridad.

**Cómo se arregla.**

*Todas las distribuciones*

Consulta la RAM que queda tras reservar VRAM y el espacio libre de la partición del swap.

```bash
free -h
df -h /var
```

Elige un TTM menor o reduce la VRAM reservada; para swap, libera espacio o selecciona un tamaño que deje el margen que indica la app.

Aplica los valores ofrecidos y refresca el estado. La operación debe superar la comprobación de capacidad antes de modificar memoria o disco.


<a id="mem-03"></a>
#### MEM-03 · Ya existe un swapfile de otro tamaño

`BC250-WORKFLOW-001` · estado: corregido · visto en: Bazzite · 1 reporte, último el 2026-11-05

**Qué se ve.** Configurar memoria se detenía al cambiar el tamaño del swap.

**Por qué pasa.** Versiones antiguas no redimensionaban su propio swapfile.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba qué swap está activo y confirma que el archivo que deseas cambiar pertenece a Control Center.

```bash
swapon --show
```

Actualiza la app y vuelve a elegir el tamaño en Memoria y swap. La app debe redimensionar únicamente su propio archivo.

Refresca el estado de swap y comprueba el tamaño resultante antes de seguir trabajando.

```bash
swapon --show
```


<a id="mem-04"></a>
#### MEM-04 · Otra preparación o cambio del sistema ya está en curso

`BC250-WORKFLOW-001` · estado: comportamiento esperado · visto en: SteamOS, CachyOS · 1 reporte, último el 2026-11-07

**Qué se ve.** Una acción de ACPI o de preparación se niega al empezar.

**Por qué pasa.** Hay otra acción de la app en marcha (otra ventana de terminal) o una anterior quedó colgada con su bloqueo.

**Cómo se arregla.**

*Todas las distribuciones*

Busca otra terminal de Control Center o una operación de preparación todavía activa.

Deja terminar esa acción. Si ya no queda ninguna y el bloqueo procede de una ejecución interrumpida, reinicia para limpiar su estado temporal.

Inicia una sola preparación y espera a que finalice; la segunda acción debe dejar de avisar de una preparación concurrente.


### Compatibilidad de SteamOS (módulo amdgpu, Mesa RADV, GE-Proton)

<a id="steam-01"></a>
#### STEAM-01 · La versión del kernel de SteamOS no está soportada por el backend revisado

`BC250-WORKFLOW-001` · estado: pendiente · visto en: SteamOS · 7 reportes, último el 2026-11-17

**Qué se ve.** Preparar la compatibilidad de SteamOS se detiene al principio con «the reviewed SteamOS kernel backend supports kernel bases …; running: …».

**Por qué pasa.** El backend de SteamOS que la app revisó cubre bases de kernel concretas (por ejemplo 6.16, 6.18 y 7.2). Los canales beta y preview de SteamOS pueden traer una base más nueva, como 7.3, que todavía no está revisada. La app se detiene antes de descargar o compilar nada, así que el sistema queda como estaba.

**Cómo se arregla.**

*SteamOS*

Consulta el kernel y la versión/canal de SteamOS. Compáralos con las opciones que ofrece la app instalada.

```bash
uname -r
cat /etc/os-release
```

Actualiza Control Center; si tu kernel aún no está cubierto, vuelve a un canal compatible o espera soporte para esa base.

Vuelve a abrir Compatibilidad › SteamOS. La preparación debe reconocer el kernel antes de descargar o compilar el backend.


<a id="steam-02"></a>
#### STEAM-02 · El clon local del kernel de Valve está dañado

`BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: SteamOS · 1 reporte, último el 2026-11-01

**Qué se ve.** La compatibilidad de SteamOS falla en git.

**Por qué pasa.** Una descarga anterior se cortó (sin espacio o apagado) y dejó el repositorio git a medias.

**Cómo se arregla.**

*Arch / CachyOS*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Reparar el clon concreto de la herramienta afectada; no borrar un checkout de desarrollo ni usar una ruta de SteamOS.

El nuevo clon debe pasar la comprobación de git y continuar la preparación. Si vuelve a dañarse, revisa espacio y la interrupción de la descarga.

*SteamOS*

Confirma que «index file smaller than expected» apunta al clon de Valve dentro de ResourceTools, no a un repositorio personal.

Comprueba que no contenga cambios propios. Aparta únicamente ese clon dañado y repite la preparación para que se descargue de nuevo.

El nuevo clon debe pasar la comprobación de git y continuar la preparación. Si vuelve a dañarse, revisa espacio y la interrupción de la descarga.

*Bazzite*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Un clon de HelixSR/DirectMesh puede dañarse; reparar la caché específica. La ruta del kernel de Valve no corresponde a este backend.

El nuevo clon debe pasar la comprobación de git y continuar la preparación. Si vuelve a dañarse, revisa espacio y la interrupción de la descarga.

*Fedora, Ubuntu / Mint, Debian*

En tu sistema este problema aparece con otro gestor de paquetes o componente, pero la causa y la solución son las mismas. Usa el equivalente de tu distribución en los comandos.

Reparar únicamente la caché git de la herramienta afectada.

El nuevo clon debe pasar la comprobación de git y continuar la preparación. Si vuelve a dañarse, revisa espacio y la interrupción de la descarga.


<a id="steam-03"></a>
#### STEAM-03 · La compilación del módulo amdgpu de SteamOS falla (resolve_btfids, make Error 2)

`BC250-PROTOCOL-001`, `BC250-BUILD-001`, `BC250-BUILD-002` · estado: en análisis · visto en: SteamOS · 5 reportes, último el 2026-11-06

**Qué se ve.** Preparar la compatibilidad de SteamOS falla compilando.

**Por qué pasa.** Las herramientas de compilación de SteamOS (gcc/binutils/libelf) no casan con las que pide el árbol del kernel; resolve_btfids es lo primero que se rompe.

**Cómo se arregla.**

*SteamOS*

Consulta el kernel activo y guarda el primer error del compilador, anterior a «make Error 2».

```bash
uname -r
df -h /home
```

Actualiza la app y vuelve a preparar el backend con espacio suficiente. Si resolve_btfids vuelve a fallar, conserva el registro completo del nuevo intento.

La instalación debe esperar a una compilación verificada. Si falla otra vez, envía el primer error y la versión del kernel para poder reproducirlo.


<a id="steam-04"></a>
#### STEAM-04 · Valor fuera de rango al preparar SteamOS

`BC250-RANGE-001` · estado: en análisis · visto en: SteamOS · 1 reporte, último el 2026-10-28

**Qué se ve.** Una acción de SteamOS, del acceso rápido o del editor de GPU se niega con un mensaje de valor fuera de rango («out of range», «must be between…»).

**Por qué pasa.** El valor pedido está fuera de los límites que la app considera seguros para esa opción, o viene de un perfil guardado con una versión anterior que permitía otros límites.

**Cómo se arregla.**

*SteamOS*

Comprueba si el error ocurre con la versión actual de Control Center y anota el valor solicitado.

Actualiza y repite usando un valor ofrecido por la interfaz. Si reaparece, copia el detalle completo desde la ventana de error.

Si un valor que la interfaz ofrece también se rechaza, copia el detalle completo de la ventana de error y envíalo desde Soporte: eso indica un límite mal calculado.


<a id="steam-05"></a>
#### STEAM-05 · Desinstalar Mesa RADV requiere reiniciar primero

`BC250-GENERAL-001` · estado: comportamiento esperado · visto en: SteamOS · 1 reporte, último el 2026-10-28

**Qué se ve.** La desinstalación se detiene pidiendo reiniciar.

**Por qué pasa.** La política del planificador sigue activa en este arranque; desinstalar ahora dejaría el sistema a medias.

**Cómo se arregla.**

*SteamOS*

Comprueba si amdgpu.sched_policy=2 sigue en los parámetros del arranque actual.

```bash
cat /proc/cmdline
```

Guarda tu trabajo y reinicia para arrancar sin el parámetro que la app ya retiró.

Repite Desinstalar Mesa RADV; debe poder continuar cuando la política anterior deje de estar activa.


<a id="steam-06"></a>
#### STEAM-06 · GE-Proton para SteamOS necesita el backend del kernel y Mesa antes

`BC250-PROTON-001` · estado: comportamiento esperado · visto en: SteamOS · 1 reporte, último el 2026-11-08

**Qué se ve.** Instalar GE-Proton BC-250 se niega.

**Por qué pasa.** Falta preparar antes el módulo y Mesa RADV de SteamOS.

**Cómo se arregla.**

*SteamOS*

Comprueba el estado del kernel y Mesa/RADV en Compatibilidad › SteamOS.

Prepara primero esos dos componentes y aplica el reinicio que solicite el flujo. Después vuelve a instalar el GE-Proton ofrecido.

El paso GE-Proton debe reconocer el backend preparado antes de empezar la instalación.


<a id="steam-07"></a>
#### STEAM-07 · SteamOS: la verificación de escritura necesita autorización interactiva de sudo

`BC250-WORKFLOW-001` · estado: en análisis · visto en: SteamOS · 2 reportes, último el 2026-11-19

**Qué se ve.** Preparar la compatibilidad de SteamOS se detiene con «SteamOS write verification needs interactive sudo authorization» (código de salida 77).

**Por qué pasa.** El instalador necesita sudo para comprobar que puede escribir en el sistema de solo lectura, pero no pudo pedir la contraseña: se ejecutó sin terminal o la cuenta de SteamOS aún no tiene contraseña definida.

**Cómo se arregla.**

*SteamOS*

Define una contraseña si nunca lo hiciste (SteamOS la trae vacía) y comprueba que sudo la acepta.

```bash
passwd
```

```bash
sudo -v
```

Repite «Preparar compatibilidad de SteamOS» desde el Panel y escribe la contraseña cuando se pida.


### Escalado (HelixSR, FSR4, OptiScaler)

<a id="ups-01"></a>
#### UPS-01 · El archivo de HelixSR publicado no es el que la app revisó

`BC250-WORKFLOW-001` · estado: corregido · desde la 1.22.7 · visto en: CachyOS · 11 reportes, último el 2026-11-21

**Qué se ve.** Instalar HelixSR 3.3.0 se niega por la suma SHA-256.

**Por qué pasa.** El autor de HelixSR volvió a subir el mismo archivo con la misma versión (cambió el contenido). En la descarga no coincidió ni con la suma que publica GitHub: subida en curso o descarga cortada.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si el aviso dice que el archivo cambió o que no coincide con la suma publicada por GitHub.

Actualiza Control Center y vuelve a descargar desde la app. Si tampoco coincide con GitHub, espera unos minutos o elige otra versión de HelixSR.

Continúa solo cuando la verificación termine correctamente. Si la descarga vuelve a fallar, conserva versión y mensaje de checksum.


<a id="ups-02"></a>
#### UPS-02 · El setup de HelixSR no conoce --vulkan

`BC250-GENERAL-001` · estado: corregido · desde la 1.22.7 · visto en: CachyOS · 2 reportes, último el 2026-11-12

**Qué se ve.** Construir los archivos de red falla al instante.

**Por qué pasa.** La app pedía la red Vulkan a versiones de HelixSR que no la tienen.

**Cómo se arregla.**

*Todas las distribuciones*

Anota la versión de HelixSR y confirma que el error indica «unknown option: --vulkan».

Actualiza Control Center y elige Construir archivos de red sin Vulkan, o una versión de HelixSR que ofrezca esa opción.

El setup debe aceptar sus argumentos antes de compilar los shaders; conserva el mensaje nuevo si falla después.


<a id="ups-03"></a>
#### UPS-03 · El compilador de shaders (DXC por Wine/Proton) falla

`BC250-GENERAL-001`, `BC250-WORKFLOW-001`, `BC250-WINE-001`, `BC250-WINE-002` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite, Fedora, CachyOS · 7 reportes, último el 2026-11-20

**Qué se ve.** La red de HelixSR o la generación de fotogramas se queda en algún porcentaje compilando shaders y falla.

**Por qué pasa.** Hay dos causas distintas. (a) El Proton elegido no tiene un files/bin/wine que se pueda ejecutar: Proton 10 cambió su estructura, o la app corre dentro de Toolbx sin las bibliotecas de 32 bits. (b) El compilador DXC de Windows, ejecutado con Wine, se cae con un error interno en un shader concreto; en ese caso suele pasar al reintentar.

**Cómo se arregla.**

*Todas las distribuciones*

Distingue entre «Internal compiler error» y Wine que no puede ejecutarse. Comprueba también si la app está dentro de Toolbx o Distrobox.

```bash
systemd-detect-virt --container
```

Si DXC cayó en un shader, reintenta la construcción una vez. Si Wine no abre, verifica Proton Experimental o GE-Proton en Steam y usa una versión ejecutable desde el host.

La compilación debe superar el mismo shader. Si vuelve a fallar, guarda el nombre del shader, Proton y el error del nuevo intento.


<a id="ups-04"></a>
#### UPS-04 · La generación de fotogramas falla leyendo un archivo que no es UTF-8

`BC250-WORKFLOW-001` · estado: en análisis · visto en: CachyOS

**Qué se ve.** HelixSR se instala, pero la generación de fotogramas no se construye.

**Por qué pasa.** El setup de HelixSR lee una salida en otro idioma/codificación (byte 0xd0 = cirílico) como UTF-8.

**Cómo se arregla.**

*Todas las distribuciones*

Confirma que el error es UnicodeDecodeError y que corresponde a la construcción de generación de fotogramas.

Actualiza y repite la construcción desde la app. El escalado puede seguir funcionando aunque la generación de fotogramas aún requiera una corrección.

Si reaparece el fallo UTF-8, copia el registro del setup e indica el idioma del sistema para revisar su codificación.


<a id="ups-05"></a>
#### UPS-05 · La red de HelixSR no se construyó (helixsr_weights.bin ausente) / sin DNS para AUR

`BC250-GENERAL-001` · estado: corregido en desarrollo (falta publicar) · visto en: SteamOS · 2 reportes, último el 2026-11-20

**Qué se ve.** Tras varios minutos compilando shaders, el setup de HelixSR falla porque falta helixsr_weights.bin.

**Por qué pasa.** El script de HelixSR crea los pesos al principio y los borra al incrustarlos en la DLL; dos construcciones simultáneas en la misma carpeta se los borran mutuamente.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si hay dos construcciones trabajando sobre la misma carpeta y si el error nombra helixsr_weights.bin.

Deja terminar las construcciones abiertas y ejecuta un solo intento desde la app. Si también falló DNS, recupera la red antes de descargar de nuevo.

Espera al resumen final. Los archivos de red deben quedar preparados antes de cambiar los archivos del juego.


<a id="ups-06"></a>
#### UPS-06 · Se rechazó la descarga de la DLL de DLSS

`BC250-GENERAL-001` · estado: pendiente · visto en: Linux Mint · 1 reporte, último el 2026-11-10

**Qué se ve.** "Archivos de red" termina sin hacer nada.

**Por qué pasa.** HelixSR necesita la DLL de DLSS de NVIDIA y pregunta antes de descargarla; se respondió que no (o Enter, que por defecto es No).

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba la pregunta «Download it now? [y/N]». Pulsar Enter conserva la opción No.

Si deseas usar esa red y aceptas descargar la DLL, repite y responde y. Si no la deseas, conserva la cancelación.

Con la descarga aceptada, espera a que la red termine. Una descarga rechazada debe finalizar sin cambios.


<a id="ups-07"></a>
#### UPS-07 · Juegos borrados del disco se quedan en la lista de HelixSR (sugerencia)

`BC250-GPU-900` · estado: corregido en desarrollo (falta publicar) · visto en: — · 1 reporte, último el 2026-11-17

**Qué se ve.** Un juego que ya desinstalaste sigue en la lista de HelixSR, y al intentar quitarlo aparece «no game (.exe) found».

**Por qué pasa.** La lista recuerda los juegos en los que instalaste HelixSR. Si borras el juego desde Steam, la app no se enteraba y seguía buscando su ejecutable.

**Cómo se arregla.**

*Todas las distribuciones*

La próxima versión de Control Center quita sola de la lista los juegos cuya carpeta ya no tiene ningún .exe. Actualiza la app cuando esté disponible.

Mientras tanto, esa fila no afecta a nada: no ocupa espacio ni cambia otros juegos. Puedes ignorarla sin riesgo.


<a id="ups-08"></a>
#### UPS-08 · Wine se cierra a mitad de la red de HelixSR (Connection reset by peer)

`BC250-GENERAL-001` · estado: corregido en desarrollo (falta publicar) · visto en: Bazzite · 1 reporte, último el 2026-11-17

**Qué se ve.** La construcción de la red de HelixSR avanza durante más de 20 minutos (por ejemplo 386 de 389 shaders) y termina con «The network was not built».

**Por qué pasa.** El proceso de Wine que compila los shaders se cae de golpe (wine client error: Connection reset by peer). No es un shader rechazado por el compilador: es Wine cerrándose, casi siempre por falta de memoria, un cierre del servidor de Wine o una sesión que lo mata. Se perdió todo el avance de esa ejecución.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba cuánta memoria y swap quedan libres. En una BC-250 con poca memoria compartida, el compilador de shaders puede quedarse sin ella.

```bash
free -h
```

Vuelve a ejecutar «Construir archivos de red» en Ajustes adicionales › Escalado. Desde esta versión la app lo reintenta sola una vez si Wine se cierra a mitad.

Si vuelve a fallar en el mismo shader, guarda el nombre del shader y el Proton usado, y envía el reporte desde Soporte.


### Vídeo por hardware, mesh shaders, DirectMesh y GFX1013

<a id="vid-01"></a>
#### VID-01 · Podman no puede usar overlay sobre Btrfs

`BC250-GENERAL-001`, `BC250-TIMEOUT-001` · estado: corregido en desarrollo (falta publicar) · visto en: CachyOS · 2 reportes, último el 2026-11-15

**Qué se ve.** "Vídeo por hardware · compilar e instalar" falla antes de arrancar el contenedor Fedora.

**Por qué pasa.** El kernel no ofrece overlay utilizable sobre Btrfs para el almacenamiento de Podman de root.

**Cómo se arregla.**

*Todas las distribuciones*

Consulta el controlador de almacenamiento y confirma si el error rechaza overlay sobre Btrfs.

```bash
podman info --format "{{.Store.GraphDriverName}}"
```

Actualiza Control Center y repite Vídeo por hardware para usar el fallback vfs cuando corresponda. Conserva el resto de contenedores y sus datos.

El contenedor debe arrancar y llegar a la compilación; guarda el nuevo error si se detiene en otra fase.


<a id="vid-02"></a>
#### VID-02 · Podman sin rangos de UID subordinados

`BC250-GENERAL-001`, `BC250-CONTAINER-001` · estado: corregido · visto en: CachyOS · 1 reporte, último el 2026-11-13

**Qué se ve.** La imagen Fedora no se puede desempaquetar.

**Por qué pasa.** El usuario no tiene /etc/subuid / /etc/subgid.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba las entradas de tu usuario en subuid/subgid y si Podman puede crear su espacio de nombres.

```bash
grep "^$(id -un):" /etc/subuid /etc/subgid
```

Si ya hay un rango pero Podman no lo ha tomado, cierra tus contenedores y aplica la migración. Si falta un rango, usa el comando específico que imprime la preparación de la app. La migración detiene los contenedores de tu usuario; aplícala después de cerrarlos.

```bash
podman system migrate
```

Vuelve a iniciar la construcción. La imagen debe poder desempaquetarse sin «insufficient UIDs or GIDs».


<a id="vid-03"></a>
#### VID-03 · El driver de vídeo de 32 bits no arranca o no tiene H.264/HEVC

`BC250-WORKFLOW-001` · estado: lo resuelve el usuario · visto en: CachyOS · 1 reporte, último el 2026-10-29

**Qué se ve.** El paso de 32 bits se detiene sin instalar.

**Por qué pasa.** Faltan bibliotecas de 32 bits (multilib) o la verificación del driver construido falló.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba qué arquitectura falló y si tu backend ofrece el driver de 32 bits.

Instala las bibliotecas de esa arquitectura con el gestor de tu distribución. En Arch confirma que multilib esté habilitado antes de repetir. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu lib32-mesa
```

Repite la verificación H.264/HEVC; el driver solo debe instalarse si la supera.

*SteamOS, Ubuntu / Mint, Debian*

Comprueba qué arquitectura falló y si tu backend ofrece el driver de 32 bits.

Instala las bibliotecas de esa arquitectura con el gestor de tu distribución. En Arch confirma que multilib esté habilitado antes de repetir.

Repite la verificación H.264/HEVC; el driver solo debe instalarse si la supera.

*Bazzite*

Comprueba qué arquitectura falló y si tu backend ofrece el driver de 32 bits.

Repite la preparación de Vídeo por hardware compatible con tu imagen. Si esa variante de 32 bits no se ofrece, conserva el driver actual y reporta el resultado de verificación.

Repite la verificación H.264/HEVC; el driver solo debe instalarse si la supera.

*Fedora*

Comprueba qué arquitectura falló y si tu backend ofrece el driver de 32 bits.

Instala las bibliotecas de esa arquitectura con el gestor de tu distribución. En Arch confirma que multilib esté habilitado antes de repetir.

```bash
sudo dnf install mesa-va-drivers.i686
```

Repite la verificación H.264/HEVC; el driver solo debe instalarse si la supera.


<a id="vid-04"></a>
#### VID-04 · El arreglo VA-API no se ve en OBS (SteamOS)

sin código · estado: en análisis · visto en: SteamOS · 1 reporte, último el 2026-11-02

**Qué se ve.** Tras el arreglo, OBS no muestra los codificadores por hardware.

**Por qué pasa.** OBS (Flatpak) usa su propio runtime y no ve el driver del sistema.

**Cómo se arregla.**

*Todas las distribuciones*

Compara las capacidades de vainfo en el host con los codificadores que muestra OBS. Comprueba si OBS procede de Flatpak.

```bash
vainfo
```

Si es Flatpak, actualiza sus runtimes y vuelve a abrir OBS. Si hay una versión de OBS del sistema, compárala para saber si la diferencia es del runtime. Ejecuta flatpak update solo si utilizas OBS Flatpak.

```bash
flatpak update
```

Comprueba si aparece el codificador esperado. Si falta, conserva la salida de vainfo y cómo instalaste OBS para investigar ese entorno.

```bash
vainfo
```


<a id="vid-05"></a>
#### VID-05 · La instalación de vídeo por hardware se quedó en la contraseña

sin código · estado: lo resuelve el usuario · visto en: Bazzite · 1 reporte, último el 2026-10-31

**Qué se ve.** El log termina en la petición de contraseña.

**Por qué pasa.** Ventana cerrada o contraseña no introducida (ver AUTH-01).

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si la terminal se quedó esperando en «[sudo] password for».

Repite la instalación e introduce la contraseña en la terminal solicitada. Si la ventana de autorización no aparece, sigue la guía de autorización.

Mantén la terminal abierta hasta el resumen final; si falla después de autenticarte, conserva ese error nuevo.


<a id="mesh-01"></a>
#### MESH-01 · DirectMesh: el instalador ejecuta nombres de paquete como comandos

`BC250-CMD-001` · estado: corregido · desde la 1.22.5 · visto en: Bazzite, CachyOS · 2 reportes, último el 2026-11-11

**Qué se ve.** Instalar DirectMesh falla en la línea 96 del instalador.

**Por qué pasa.** Fallo del instalador de DirectMesh al construir la lista de dependencias.

**Cómo se arregla.**

*Todas las distribuciones*

Confirma que la línea de error intenta ejecutar libxshmfence-devel o systemd-libs como si fueran programas.

Actualiza Control Center a una versión que incluya la corrección del instalador y repite DirectMesh.

La preparación debe pasar la lista de dependencias y llegar al build; guarda el primer error nuevo si se detiene después.


<a id="mesh-02"></a>
#### MESH-02 · DirectMesh: la fuente descargada está dañada (Missing sections in … .wrap)

`BC250-GENERAL-001` · estado: corregido · desde la 1.22.6 · visto en: CachyOS · 1 reporte, último el 2026-11-12

**Qué se ve.** La compilación de DirectMesh falla en meson.

**Por qué pasa.** Una descarga anterior quedó a medias en la caché.

**Cómo se arregla.**

*Todas las distribuciones*

Confirma que el archivo .wrap incompleto está en la caché de compilación de DirectMesh.

Actualiza y repite la construcción para que la app regenere esa fuente dañada. Conserva intactos los repositorios que hayas modificado personalmente.

Meson debe leer DirectX-Headers.wrap y continuar. Si el archivo vuelve a quedar incompleto, revisa la descarga y el espacio disponible.


<a id="gfx-01"></a>
#### GFX-01 · El cómputo asíncrono GFX1013 solo soporta Bazzite 44

`BC250-WORKFLOW-001` · estado: corregido · visto en: Bazzite · 3 reportes, último el 2026-11-11

**Qué se ve.** La acción se niega en Bazzite 45.

**Por qué pasa.** La release revisada de la herramienta solo cubre Bazzite 44.

**Cómo se arregla.**

*Bazzite*

Comprueba la versión de Bazzite y la release de la herramienta que ofrece Control Center.

Instala únicamente la release ofrecida para tu imagen. Si la herramienta revisada solo cubre Bazzite 44, espera soporte para tu versión actual.

La comprobación de compatibilidad debe superar la versión de la imagen antes de instalar archivos.


<a id="gfx-02"></a>
#### GFX-02 · La instalación por juego activó el driver para todo el sistema

`BC250-WORKFLOW-001` · estado: corregido · visto en: Bazzite · 1 reporte, último el 2026-11-06

**Qué se ve.** La app detuvo la instalación por seguridad.

**Por qué pasa.** Ya había una activación global anterior.

**Cómo se arregla.**

*Bazzite*

Comprueba si el driver ya estaba activado para todo el sistema antes de la instalación por juego.

Actualiza y repite la instalación por juego; conserva la activación global si ya existía y era la que utilizabas.

Revisa el estado global y la configuración del juego después de terminar. Adjunta ambos si la app sigue detectando un cambio inesperado.


<a id="gfx-03"></a>
#### GFX-03 · La descarga de la herramienta GFX1013 devolvió 504

`BC250-NET-001`, `BC250-DBUS-001` · estado: lo resuelve el usuario · visto en: Bazzite · 1 reporte, último el 2026-11-08

**Qué se ve.** La descarga falló dos veces.

**Por qué pasa.** GitHub devolvió 504 temporalmente.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba si curl indica HTTP 504 en la URL de descarga. No corresponde por sí solo a un fallo de D-Bus.

Espera unos minutos y vuelve a descargar la herramienta desde la app. Usa solo el backend ofrecido para tu distribución.

La descarga debe completarse y verificarse. Si persiste el 504, conserva la URL y prueba cuando se recupere el servidor.


<a id="gfx-04"></a>
#### GFX-04 · GFX1013: falla el initramfs de un kernel viejo (dracut)

`BC250-GENERAL-001` · estado: corregido en desarrollo (falta publicar) · visto en: ubuntu · 1 reporte, último el 2026-11-19

**Qué se ve.** Tras compilar 15-30 minutos, la instalación del fix GFX1013 termina con «dracut[F]: image generation failed for kernel» para un kernel que no es el que está en uso.

**Por qué pasa.** El script regeneraba el initramfs de todos los kernels (dracut --regenerate-all). Un kernel viejo sin sus módulos ni su carpeta en la ESP no se puede regenerar y tumbaba toda la instalación.

**Cómo se arregla.**

*Arch / CachyOS*

En Arch se usa mkinitcpio -P; si un preset viejo falla, quítalo de /etc/mkinitcpio.d.

```bash
ls /etc/mkinitcpio.d
```

*Ubuntu / Mint, Debian*

Mira qué kernels quedan instalados y cuál está en uso.

```bash
uname -r
```

```bash
ls /usr/lib/modules
```

Con la versión corregida, solo el initramfs del kernel en uso tiene que regenerarse; un kernel viejo que falla deja un aviso y la instalación sigue.

Si el kernel viejo ya no se usa, quítalo con el gestor de paquetes.

```bash
sudo apt autoremove --purge
```


### Ventiladores y sensores

<a id="fan-01"></a>
#### FAN-01 · El módulo nct6687 no encuentra el chip (No such device, chip ID 0xffff)

`BC250-FAN-001`, `BC250-GENERAL-001` · estado: pendiente · visto en: Linux Mint, Bazzite · 3 reportes, último el 2026-11-15

**Qué se ve.** El servicio nct6687-load falla al arrancar y no hay control de ventiladores.

**Por qué pasa.** El driver no lee un ID de chip válido (0xffff): el SuperIO no responde en ese arranque o otro driver/ACPI tiene reservado el rango de puertos. En Mint se ve el aviso de conflicto con ACPI.

**Cómo se arregla.**

*Todas las distribuciones*

Busca NCT6687, chip ID 0xffff y conflictos ACPI en el registro del kernel.

```bash
sudo dmesg | grep -iE 'nct6687|super.?io|opregion|resource conflict'
```

Apaga completamente y vuelve a arrancar. Si el log confirma un conflicto de recursos ACPI, revisa la opción acpi_enforce_resources=lax desde los ajustes del kernel de la app.

Vuelve a detectar los ventiladores. Si el chip continúa en 0xffff, guarda el kernel y el registro; no fuerces un ID desconocido.


<a id="fan-02"></a>
#### FAN-02 · Las cabeceras del kernel no coinciden con el kernel en uso (Bazzite)

`BC250-KERNEL-001` · estado: corregido · visto en: Bazzite · 1 reporte, último el 2026-11-09

**Qué se ve.** El driver PWM no se compila.

**Por qué pasa.** El kernel activo (…bc250cu) no tiene su kernel-devel; el instalado es de otro despliegue.

**Cómo se arregla.**

*Arch / CachyOS*

Consulta uname -r y comprueba si las cabeceras instaladas corresponden exactamente a ese kernel.

```bash
uname -r
```

Consulta el nombre exacto de tu kernel e instala sus cabeceras correspondientes: linux-headers, linux-cachyos-headers o las del kernel BC-250 que uses.

Repite Preparar PWM y comprueba que supera la comprobación de kernel antes de compilar el driver.

*SteamOS*

Consulta uname -r y comprueba si las cabeceras instaladas corresponden exactamente a ese kernel.

```bash
uname -r
```

Usa la preparación de driver revisada para el kernel de Valve activo. No copies un árbol de cabeceras de otra versión.

Repite Preparar PWM y comprueba que supera la comprobación de kernel antes de compilar el driver.

*Bazzite*

Consulta uname -r y comprueba si las cabeceras instaladas corresponden exactamente a ese kernel.

```bash
uname -r
```

Comprueba rpm-ostree status. Si hay un despliegue pendiente con las cabeceras del kernel correcto, reinicia en él. Si no existe kernel-devel para tu kernel, usa una imagen/kernel que sí lo proporcione.

Repite Preparar PWM y comprueba que supera la comprobación de kernel antes de compilar el driver.

*Fedora*

Consulta uname -r y comprueba si las cabeceras instaladas corresponden exactamente a ese kernel.

```bash
uname -r
```

Instala las cabeceras correctas. En Bazzite, si existe un despliegue pendiente con el kernel correcto, arranca en él; reiniciar no instala cabeceras que no existen.

```bash
sudo dnf install kernel-devel-$(uname -r)
```

Repite Preparar PWM y comprueba que supera la comprobación de kernel antes de compilar el driver.

*Ubuntu / Mint, Debian*

Consulta uname -r y comprueba si las cabeceras instaladas corresponden exactamente a ese kernel.

```bash
uname -r
```

Instala las cabeceras correctas. En Bazzite, si existe un despliegue pendiente con el kernel correcto, arranca en él; reiniciar no instala cabeceras que no existen.

```bash
sudo apt install linux-headers-$(uname -r)
```

Repite Preparar PWM y comprueba que supera la comprobación de kernel antes de compilar el driver.


<a id="fan-03"></a>
#### FAN-03 · No se pudieron activar los ventiladores (Fedora)

sin código · estado: en análisis · visto en: Fedora · 1 reporte, último el 2026-11-11

**Qué se ve.** El control PWM no se aplicaba.

**Por qué pasa.** Al escribir el PWM, la app vuelve a leerlo para confirmar que el chip lo aceptó. En algunas versiones antiguas esa lectura no coincidía con lo escrito y la app daba el cambio por fallido.

**Cómo se arregla.**

*Todas las distribuciones*

Vuelve a detectar el sensor y confirma qué canal físico estás ajustando.

Actualiza y prueba primero Automático. Después aplica un valor manual ofrecido por la app y observa la lectura de vuelta.

Si sigue sin aplicar el control, envía un reporte nuevo desde Ventiladores con el canal y el resultado de lectura.


<a id="fan-04"></a>
#### FAN-04 · No se pudo pasar el ventilador a otro programa

`BC250-HW-001` · estado: en análisis · visto en: Linux Mint · 2 reportes, último el 2026-11-10

**Qué se ve.** Al pasar el control del ventilador a otro programa (por ejemplo CoolerControl), la app muestra «Fan hand-off failed».

**Por qué pasa.** La app solo entrega el canal del ventilador si detecta la BC-250 y su chip de ventiladores (NCT6687). Si la placa no se detecta bien, por ejemplo porque el driver de la GPU o el del chip no cargó, cancela la entrega para no dejar el ventilador sin control.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba que la app detecta la BC-250 y que el programa receptor está instalado y reconoce ese sensor.

Corrige primero la detección del hardware si falta y vuelve a solicitar la entrega al programa elegido.

Comprueba el ventilador desde el programa receptor. Si falla la entrega, conserva el error actual y el nombre del programa.


### Audio HDMI, TV (HDMI-CEC) y periféricos

<a id="aud-01"></a>
#### AUD-01 · Ninguna salida HDMI/DisplayPort ofrece el perfil Dolby Digital 5.1

`BC250-WORKFLOW-001` · estado: comportamiento esperado · visto en: SteamOS · 1 reporte, último el 2026-11-08

**Qué se ve.** Configurar audio 5.1 se detiene.

**Por qué pasa.** El televisor/receptor estaba apagado o no anunció AC3 al conectar.

**Cómo se arregla.**

*Todas las distribuciones*

Enciende el televisor o receptor y comprueba qué perfiles de la salida HDMI anuncia el servidor de audio.

```bash
pactl list cards short
```

Selecciona la salida HDMI correcta y repite la configuración 5.1. El receptor debe anunciar AC3 para poder ofrecer ese perfil.

Comprueba que el perfil aparece y prueba el sonido. Si no se anuncia AC3, revisa el receptor y la conexión antes de cambiar paquetes.


<a id="aud-02"></a>
#### AUD-02 · Falta pactl

`BC250-WORKFLOW-001` · estado: corregido · visto en: Ubuntu · 1 reporte, último el 2026-11-14

**Qué se ve.** Audio HDMI 5.1 se detiene en Ubuntu.

**Por qué pasa.** Ubuntu 26.04 con PipeWire no trae pactl por defecto.

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si Linux encuentra pactl y si puedes consultar el servidor de audio.

```bash
command -v pactl
```

Instala el paquete que proporciona pactl en tu distribución o prepara Audio HDMI desde la app. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu libpulse
```

La consulta de pactl debe responder; después repite la configuración de audio 5.1.

```bash
pactl info
```

*SteamOS*

Comprueba si Linux encuentra pactl y si puedes consultar el servidor de audio.

```bash
command -v pactl
```

Instala el paquete que proporciona pactl en tu distribución o prepara Audio HDMI desde la app.

La consulta de pactl debe responder; después repite la configuración de audio 5.1.

```bash
pactl info
```

*Bazzite*

Comprueba si Linux encuentra pactl y si puedes consultar el servidor de audio.

```bash
command -v pactl
```

Instala el paquete que proporciona pactl en tu distribución o prepara Audio HDMI desde la app. Al terminar rpm-ostree, reinicia en el nuevo despliegue antes de verificar.

```bash
rpm-ostree install pulseaudio-utils
```

La consulta de pactl debe responder; después repite la configuración de audio 5.1.

```bash
pactl info
```

*Fedora*

Comprueba si Linux encuentra pactl y si puedes consultar el servidor de audio.

```bash
command -v pactl
```

Instala el paquete que proporciona pactl en tu distribución o prepara Audio HDMI desde la app.

```bash
sudo dnf install pulseaudio-utils
```

La consulta de pactl debe responder; después repite la configuración de audio 5.1.

```bash
pactl info
```

*Ubuntu / Mint, Debian*

Comprueba si Linux encuentra pactl y si puedes consultar el servidor de audio.

```bash
command -v pactl
```

Instala el paquete que proporciona pactl en tu distribución o prepara Audio HDMI desde la app.

```bash
sudo apt install pulseaudio-utils
```

La consulta de pactl debe responder; después repite la configuración de audio 5.1.

```bash
pactl info
```


<a id="tv-01"></a>
#### TV-01 · Falta cec-ctl para el control del televisor

`BC250-WORKFLOW-001`, `BC250-PKG-001` · estado: corregido · visto en: Fedora, Linux Mint · 1 reporte, último el 2026-10-31

**Qué se ve.** "Apagar el televisor al apagar" o el control CEC falla.

**Por qué pasa.** Falta el paquete v4l-utils, que es el que trae cec-ctl, o el gestor de paquetes no pudo instalarlo porque otro problema lo bloqueó (una PPA rota o el gestor ocupado por otra instalación).

**Cómo se arregla.**

*Arch / CachyOS*

Comprueba si cec-ctl está disponible. Esta utilidad permite consultar el dispositivo CEC.

```bash
command -v cec-ctl
```

Instala v4l-utils con el gestor correspondiente. En Bazzite aplica el reinicio si el paquete queda en el siguiente despliegue. Este comando también actualiza los paquetes del sistema; revisa el resumen antes de aceptar.

```bash
sudo pacman -Syu v4l-utils
```

Comprueba que cec-ctl abre su ayuda y repite el control del televisor desde la app.

```bash
cec-ctl --help
```

*SteamOS*

Comprueba si cec-ctl está disponible. Esta utilidad permite consultar el dispositivo CEC.

```bash
command -v cec-ctl
```

Instala v4l-utils con el gestor correspondiente. En Bazzite aplica el reinicio si el paquete queda en el siguiente despliegue.

Comprueba que cec-ctl abre su ayuda y repite el control del televisor desde la app.

```bash
cec-ctl --help
```

*Bazzite*

Comprueba si cec-ctl está disponible. Esta utilidad permite consultar el dispositivo CEC.

```bash
command -v cec-ctl
```

Instala v4l-utils con el gestor correspondiente. En Bazzite aplica el reinicio si el paquete queda en el siguiente despliegue. Al terminar rpm-ostree, reinicia en el nuevo despliegue antes de verificar.

```bash
rpm-ostree install v4l-utils
```

Comprueba que cec-ctl abre su ayuda y repite el control del televisor desde la app.

```bash
cec-ctl --help
```

*Fedora*

Comprueba si cec-ctl está disponible. Esta utilidad permite consultar el dispositivo CEC.

```bash
command -v cec-ctl
```

Instala v4l-utils con el gestor correspondiente. En Bazzite aplica el reinicio si el paquete queda en el siguiente despliegue.

```bash
sudo dnf install v4l-utils
```

Comprueba que cec-ctl abre su ayuda y repite el control del televisor desde la app.

```bash
cec-ctl --help
```

*Ubuntu / Mint, Debian*

Comprueba si cec-ctl está disponible. Esta utilidad permite consultar el dispositivo CEC.

```bash
command -v cec-ctl
```

Instala v4l-utils con el gestor correspondiente. En Bazzite aplica el reinicio si el paquete queda en el siguiente despliegue.

```bash
sudo apt install v4l-utils
```

Comprueba que cec-ctl abre su ayuda y repite el control del televisor desde la app.

```bash
cec-ctl --help
```


### Red y descargas

<a id="net-01"></a>
#### NET-01 · Sin DNS: no se puede resolver github.com

`BC250-GENERAL-001` · estado: lo resuelve el usuario · visto en: CachyOS, Bazzite · 2 reportes, último el 2026-11-18

**Qué se ve.** Clonar o descargar una herramienta falla.

**Por qué pasa.** Sin red, DNS caído o un bloqueo en la red del usuario.

**Cómo se arregla.**

*Todas las distribuciones*

Consulta la resolución de github.com y después prueba su conexión HTTPS. Son dos comprobaciones distintas.

```bash
getent hosts github.com
curl -I --connect-timeout 10 https://github.com
```

Si no resuelve, revisa la conexión y el DNS de tu red. Si resuelve pero HTTPS falla, comprueba proxy, filtrado y hora del sistema.

Repite ambas comprobaciones y después la descarga. Si sigue fallando, conserva la salida que distingue DNS de conexión.

```bash
getent hosts github.com
curl -I --connect-timeout 10 https://github.com
```


### Ideas y sugerencias

<a id="idea-01"></a>
#### IDEA-01 · Mensajes y sugerencias generales

sin código · estado: pendiente · visto en: CachyOS · 1 reporte, último el 2026-11-07

**Qué se ve.** Mensajes recibidos: felicitaciones; comentario sobre instalación por consola; agradecimiento por la entrega a CoolerControl y sus curvas; propuesta de integrar Boxshelf; reporte de prueba vacío.

**Por qué pasa.** No se confirmó una causa técnica; se conserva como sugerencia o caso pendiente de análisis.

**Cómo se arregla.**

*Todas las distribuciones*

Esta entrada agrupa comentarios de instalación, curvas de ventilador, agradecimientos y la propuesta Boxshelf.

Para un fallo técnico, busca el mensaje concreto en el catálogo. Para ampliar una propuesta, describe el comportamiento que esperas y en qué distribución.

Consulta las notas de desarrollo para distinguir una propuesta por evaluar de una función implementada.


<a id="idea-02"></a>
#### IDEA-02 · Ver el uso de discos externos (coreano)

sin código · estado: corregido · visto en: —

**Qué se ve.** Ver el uso de discos externos (coreano)

**Por qué pasa.** No se confirmó una causa técnica; se conserva como sugerencia o caso pendiente de análisis.

**Cómo se arregla.**

*Todas las distribuciones*

Comprueba qué discos y particiones están montados en este momento.

```bash
df -h -x tmpfs -x devtmpfs
```

Abre Almacenamiento y despliega la lista de discos. Si no aparecen varias unidades, actualiza a una versión que incluya esa vista.

Compara la lista con los sistemas de archivos montados; si falta uno, indica su punto de montaje en el reporte.


<a id="idea-03"></a>
#### IDEA-03 · Ver los reportes enviados y su estado

sin código · estado: corregido en desarrollo (falta publicar) · visto en: —

**Qué se ve.** Ver los reportes enviados y su estado

**Por qué pasa.** No se confirmó una causa técnica; se conserva como sugerencia o caso pendiente de análisis.

**Cómo se arregla.**

*Todas las distribuciones*

Abre Ajustes › Acerca de › Soporte y localiza Reportes enviados.

Busca el envío por su resumen o fecha. Usa Ver para revisar sus datos y Copiar para guardar su referencia.

Conserva el ID al preguntar por tu reporte. La lista es local y no representa un estado de ticket remoto.


<a id="idea-04"></a>
#### IDEA-04 · Idea: mostrar las unidades de cómputo desbloqueadas en el registro del kernel

sin código · estado: pendiente · visto en: —

**Qué se ve.** Un usuario sugiere que, al desbloquear unidades de cómputo, el kernel (o la app) deje constancia en el registro de cuántas quedaron activas.

**Por qué pasa.** Hoy el número de CU activas solo se ve en el mapa de la app (Unidades de cómputo); no queda registro del kernel de esa acción.

**Cómo se arregla.**

*Todas las distribuciones*

Mira cuántas CU están activas en Unidades de cómputo.

```bash
sudo dmesg | grep -i amdgpu
```


## En investigación

Errores reportados que todavía no tienen ficha. Si te pasa uno de estos, manda un reporte desde la app: cada caso ayuda a encontrar la causa.

| Código | Parte de la app | Reportes |
|---|---|---|
| `BC250-WORKFLOW-001` | Kernel, Mesa and distribution support | 3 |
| `BC250-GENERAL-001` | GPU governor (Cyan) | 2 |
| `BC250-WORKFLOW-001` | Dashboard / Prepare dependencies | 1 |
| `BC250-PKG-004` | Drivers, accessories and TV control | 1 |
| `BC250-GENERAL-001` | Dashboard / Prepare dependencies | 1 |
| `BC250-GENERAL-001` | App install or update | 1 |
| `BC250-WORKFLOW-001` | GPU governor (Cyan) | 1 |
| `BC250-CU-001` | Compute Units (40CU) | 1 |
| `BC250-CONFIG-001` | GPU governor (Cyan) | 1 |
| `BC250-WORKFLOW-001` | App install or update | 1 |

<!-- fin de lo generado -->
