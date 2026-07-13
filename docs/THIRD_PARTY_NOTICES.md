# Third-party tools and credits

BC250 Control Center incluye integracion para herramientas comunitarias externas de BC-250. Estas herramientas no se presentan como autoria propia del proyecto.

La aplicacion no empaqueta estos repositorios dentro del codigo fuente principal ni dentro de los paquetes generados. Cuando el usuario usa `Preparar dependencias` o una accion relacionada, BC250 Control Center detecta herramientas faltantes y puede clonarlas o instalarlas desde sus repositorios oficiales o desde paquetes del sistema disponibles en la distribucion.

## Repositorios integrados

### cyan-skillfish-governor / cyan-skillfish-governor-smu

- Uso dentro de BC250 Control Center: control de rangos GPU BC-250 mediante governor SMU y D-Bus.
- Repositorio oficial: https://github.com/Magnap/cyan-skillfish-governor
- Rama/paquete usado por algunas distribuciones: `cyan-skillfish-governor-smu`
- Creditos: proyecto cyan-skillfish-governor y sus autores/contribuidores.
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

### bc250-40cu-unlock

- Uso dentro de BC250 Control Center: referencia/documentacion comunitaria y credito upstream. No se clona por defecto como dependencia de ejecucion; el flujo live usa `WinnieLV/bc250-cu-live-manager`.
- Repositorio oficial: https://github.com/duggasco/bc250-40cu-unlock
- Creditos: duggasco y contribuidores del repositorio.
- Licencia observada en documentacion local: GPL-2.0.

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
