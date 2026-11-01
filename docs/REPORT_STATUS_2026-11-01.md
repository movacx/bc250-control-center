# Estado de reportes — 1 de noviembre de 2026

Registro de los 54 reportes presentes en Cloudflare al consultar la bandeja.
Los reportes originales y sus adjuntos se conservan; no se eliminaron ni se
modificaron en Cloudflare. Este documento registra su estado en desarrollo.

El mantenedor confirmó que los problemas anteriores habían sido corregidos en
otras sesiones de trabajo, con la excepción de R-8552cc8f. Los cierres indicados
como «confirmado por mantenedor» recogen esa confirmación; no representan una
nueva reproducción o validación individual realizada en esta revisión.

## R-8552cc8f — Fedora 44: reposo de TV al apagar

**Corrección implementada en desarrollo; pendiente de confirmar en la placa.**

El registro del flujo se detiene porque falta `cec-ctl`. La configuración
comprobaba el ejecutable y terminaba sin preparar su dependencia. En Fedora,
ahora instala `v4l-utils` mediante `sudo dnf install -y` cuando falta la
herramienta y vuelve a comprobarla antes de escribir o activar el servicio.
Si se rechaza la autorización, falla la instalación o el ejecutable sigue
faltando, el flujo se detiene antes de configurar el servicio.

Fuente del paquete: [archivos de v4l-utils para Fedora 44](https://packages.fedoraproject.org/pkgs/v4l-utils/v4l-utils/fedora-44.html).

Validación: 33 pruebas y 4 subpruebas de control de TV/OpenRC pasan. Las nuevas
pruebas ejecutan la preparación con un instalador simulado: dependencia
ausente, dependencia ya disponible, fallo de instalación e instalación que no
proporciona el ejecutable. No se instaló software en el equipo del usuario ni
se envió una orden real a una TV. El reposo físico al apagar Fedora requiere
confirmación en la placa.

## Registro

| Reporte | Estado |
| --- | --- |
| R-109e1d54 | Corregido — confirmado por mantenedor |
| R-10c45cc3 | Corregido — confirmado por mantenedor |
| R-18cd85d8 | Corregido — confirmado por mantenedor |
| R-19627eb5 | Corregido — confirmado por mantenedor |
| R-1c2419c1 | Corregido — confirmado por mantenedor |
| R-20974a0b | Corregido — confirmado por mantenedor |
| R-26457f83 | Corregido — confirmado por mantenedor |
| R-312525ce | Corregido — confirmado por mantenedor |
| R-3163566b | Corregido — confirmado por mantenedor |
| R-31c8eb8a | Corregido — confirmado por mantenedor |
| R-4631ede6 | Corregido — confirmado por mantenedor |
| R-4745effe | Corregido — confirmado por mantenedor |
| R-47f60a05 | Corregido — confirmado por mantenedor |
| R-5079dcd5 | Corregido — confirmado por mantenedor |
| R-50ff31f2 | Corregido — confirmado por mantenedor |
| R-5113cfef | Corregido — confirmado por mantenedor |
| R-536c885c | Corregido — confirmado por mantenedor |
| R-590bf979 | Corregido — confirmado por mantenedor |
| R-5bdaa9a8 | Corregido — confirmado por mantenedor |
| R-60c1e16a | Corregido — confirmado por mantenedor |
| R-6373ea51 | Corregido — confirmado por mantenedor |
| R-6b3d1026 | Corregido — confirmado por mantenedor |
| R-6cd4c6f7 | Corregido — confirmado por mantenedor |
| R-6ff0c948 | Corregido — confirmado por mantenedor |
| R-7191a2f0 | Corregido — confirmado por mantenedor |
| R-7cfcf8d7 | Corregido — confirmado por mantenedor |
| R-80c41cb8 | Corregido — confirmado por mantenedor |
| R-8552cc8f | Corrección implementada; confirmación en placa pendiente |
| R-8b3d9eac | Corregido — confirmado por mantenedor |
| R-8e796dad | Corregido — confirmado por mantenedor |
| R-9305caee | Corregido — confirmado por mantenedor |
| R-9978d9d4 | Corregido — confirmado por mantenedor |
| R-9dfe6c8f | Corregido — confirmado por mantenedor |
| R-9f1caff8 | Corregido — confirmado por mantenedor |
| R-a60ea60d | Corregido — confirmado por mantenedor |
| R-a68c799b | Corregido — confirmado por mantenedor |
| R-a7549131 | Corregido — confirmado por mantenedor |
| R-a8fc77e6 | Corregido — confirmado por mantenedor |
| R-ab4baf4e | Corregido — confirmado por mantenedor |
| R-ad63886f | Corregido — confirmado por mantenedor |
| R-b68ac341 | Corregido — confirmado por mantenedor |
| R-bc2d99b9 | Corregido — confirmado por mantenedor |
| R-c31b77ad | Corregido — confirmado por mantenedor |
| R-d4d87dbd | Corregido — confirmado por mantenedor |
| R-d6495400 | Corregido — confirmado por mantenedor |
| R-d69fb510 | Corregido — confirmado por mantenedor |
| R-dce0d0a0 | Corregido — confirmado por mantenedor |
| R-dd9d2016 | Corregido — confirmado por mantenedor |
| R-df49405e | Corregido — confirmado por mantenedor |
| R-e6aaeafd | Corregido — confirmado por mantenedor |
| R-ee797682 | Corregido — confirmado por mantenedor |
| R-f0ed2fdd | Corregido — confirmado por mantenedor |
| R-f80a5fcc | Corregido — confirmado por mantenedor |
| R-ff91f26c | Corregido — confirmado por mantenedor |
