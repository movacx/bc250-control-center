# Third-party tools and credits

BC250 Control Center incluye integracion para herramientas comunitarias externas de BC-250. Estas herramientas no se presentan como autoria propia del proyecto.

La aplicacion no empaqueta estos repositorios dentro del codigo fuente principal ni dentro de los paquetes generados. Cuando el usuario usa `Preparar dependencias` o una accion relacionada, BC250 Control Center detecta herramientas faltantes y puede clonarlas o instalarlas desde sus repositorios oficiales o desde paquetes del sistema disponibles en la distribucion.

## Repositorios integrados

### cyan-skillfish-governor / cyan-skillfish-governor-smu

- Uso dentro de BC250 Control Center: control de rangos GPU BC-250 mediante governor SMU y D-Bus.
- Repositorio SMU usado/recomendado: https://github.com/filippor/cyan-skillfish-governor/tree/smu
- Paquete usado por algunas distribuciones: `cyan-skillfish-governor-smu`
- Creditos: fork/rama SMU de filippor y proyecto cyan-skillfish-governor con sus autores/contribuidores.
- Licencia observada en paquetes/repositorios disponibles: MIT.

### bc250_smu_oc

- Uso dentro de BC250 Control Center: overclock/undervolt temporal de CPU mediante `bc250-detect --frequency ... --vid ... --temp ... --keep`.
- Repositorio oficial: https://github.com/bc250-collective/bc250_smu_oc
- Creditos: `bc250-collective` y sus contribuidores.
- Licencia observada: MIT.

### bc250-cu-live-manager

- Uso dentro de BC250 Control Center: dashboard live de WGP/CU y acciones temporales para activar/restaurar perfiles 40CU/24CU.
- Repositorio oficial: https://github.com/WinnieLV/bc250-cu-live-manager
- Creditos: WinnieLV y contribuidores del repositorio.
- Nota: BC250 Control Center clona/usa este proyecto desde su repositorio oficial cuando el usuario prepara dependencias o ejecuta acciones 40CU relacionadas. No se elimina ni reemplaza el credito upstream.

### bc250-cu-live-manager-SteamOS

- Uso dentro de BC250 Control Center: backend alternativo para SteamOS cuando el live-manager original no puede leer/enrutar el estado 40CU correctamente en ese entorno.
- Repositorio oficial: https://github.com/F5GO/bc250-cu-live-manager-SteamOS
- Creditos: F5GO y contribuidores del repositorio upstream.
- Nota: BC250 Control Center lo clona/usa desde su repositorio oficial unicamente en sistemas SteamOS detectados o cuando se requiere ese flujo compatible.

### bc250-40cu-unlock

- Uso dentro de BC250 Control Center: referencia/documentacion comunitaria y credito upstream. No se clona por defecto como dependencia de ejecucion; el flujo live usa `WinnieLV/bc250-cu-live-manager`.
- Repositorio oficial: https://github.com/duggasco/bc250-40cu-unlock
- Creditos: duggasco y contribuidores del repositorio.
- Licencia observada en documentacion local: GPL-2.0.

### bc250-core-unlock

- Uso dentro de BC250 Control Center: herramienta upstream clonada en `ResourceTools` y lanzada desde la interfaz para desbloquear temporalmente los dos núcleos Zen 2 ocultos mediante SMU.
- Repositorio oficial: https://github.com/rw-r-r-0644/bc250-core-unlock
- Créditos: `rw-r-r-0644` y contribuidores del repositorio.
- Integración: la aplicación clona/actualiza el repositorio oficial y ejecuta directamente su `bc250-unlock-cores.py`. Un helper privilegiado local valida el origen y el estado limpio del clon, detiene el governor incompatible y reinicia; no reimplementa la escritura SMU.
- Comportamiento confirmado en el código upstream: cambia la máscara `0x77` a `0xff`; requiere detener `cyan-skillfish-governor-smu`, reiniciar para enumerar 8 núcleos/16 hilos y se revierte al cortar completamente la alimentación.
- Alcance de validación upstream observado: BIOS 3.0 y kernel 6.18.40. Otras combinaciones son experimentales y no están garantizadas.

### nct6687d

- Uso dentro de BC250 Control Center: control PWM experimental de ventiladores BC-250 mediante el modulo `nct6687` cuando el usuario prepara PWM ventilador.
- Repositorio oficial: https://github.com/Fred78290/nct6687d
- Creditos: Fred78290 y contribuidores del repositorio.
- Nota: el modulo puede instalarse como DKMS desde AUR en sistemas Arch-like. La aplicacion solo lo prepara cuando el usuario lo solicita.

## Politica de integracion

BC250 Control Center funciona como interfaz grafica, monitor, integrador y lanzador seguro. El objetivo es facilitar el uso de herramientas comunitarias sin ocultar su origen.

- Los repositorios externos se referencian por su URL oficial.
- Las herramientas externas se clonan o instalan desde fuentes upstream cuando el usuario lo solicita.
- La documentacion y la interfaz muestran enlaces a los repositorios oficiales cuando corresponde.
- Las licencias, autoria y creditos de cada proyecto pertenecen a sus respectivos autores.
- Si un repositorio externo cambia su licencia, instrucciones o funcionamiento, debe respetarse la documentacion upstream vigente.

## Seguridad

Las herramientas de BC-250 pueden modificar frecuencias, voltajes, rangos GPU, servicios systemd o enrutamiento de unidades de computo. Usarlas puede causar cuelgues, apagones, perdida de datos o dano de hardware si la configuracion no es estable.

BC250 Control Center aplica validaciones conservadoras, pero la estabilidad final depende de cada placa, fuente de poder, refrigeracion, kernel, distribucion y configuracion local.
