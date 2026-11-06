# BC-250 GE-Proton en SteamOS

En **Ajustes adicionales → Compatibilidad → Kernel y gráficos**, la tarjeta
**BC-250 GE-Proton · SteamOS** ofrece instalar/actualizar, comprobar y quitar.
Después de instalarlo, reinicia Steam y selecciónalo en las propiedades de
compatibilidad del juego.

La aplicación ejecuta sin modificaciones `bc250-proton.sh` de
[keyboardspecialist/bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos).
El checkout separado `ResourceTools/bc250-steamos-proton` sigue su rama `master`
al instalar, actualizar o quitar. La comprobación utiliza la copia local y no
necesita red. La revisión inspeccionada inicialmente fue
`5fe7ae9765c9b419ffbd740eefe1c85d482fa05d`.

El propio script selecciona el paquete GE-Proton BC-250 de MastaG, comprueba
su SHA-256 publicado en GitHub y gestiona instalación, recuperación y retirada
en `~/.local/share/Steam/compatibilitytools.d`. No instala el repositorio
CachyOS ni actualiza bibliotecas del sistema. Los prefijos y partidas quedan
bajo el control de Steam.

Se conserva la comprobación de RADV de upstream. Su variable documentada
`BC250_MESH_TOOL` apunta al gestor protegido de RADV que ya utiliza la app.
La instalación requiere ese backend preparado y el runtime FSR4 RADV activo;
el instalador explica si falta activarlo o completar un reinicio. No se simula
un estado listo ni se instala Mesa como efecto de instalar Proton.

La revisión fijada del backend AMDGPU/RADV y el flujo Arch/CachyOS son
independientes y no cambian con esta integración. La interfaz TUI ofrece las
mismas operaciones mediante el servicio compartido.

Upstream advierte que no se debe utilizar la inyección FSR4 en juegos con
anticheat. Su instalador conserva ese mensaje.

Validación de integración: acciones finitas, ejecución como usuario normal,
restricción SteamOS, prerrequisito RADV, comprobación sin red, retirada sin
exigir RADV instalado y propagación del error original con diagnóstico
BC250-PROTON-001. También se ejecutó la suite de Proton de upstream sobre el
script original: 17 pruebas y 2 subtests aprobados. Esto no equivale a probar
juegos ni a instalar el paquete completo en el equipo.
