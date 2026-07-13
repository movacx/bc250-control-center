# BC250 Control Center

Interfaz grafica para administrar una AMD BC-250 desde Linux. Reune monitoreo, procesos, memoria, GPU, CPU OC y 40CU en una sola app, con advertencias y validaciones para no depender de comandos sueltos.

## Instalacion

### Opcion rapida con script

Usa esta opcion si estas ejecutando desde el codigo fuente o desde un tarball:

```bash
PREFIX="$HOME/.local" ./scripts/install-local.sh
"$HOME/.local/bin/bc250-control-center"
```

Para desinstalar esa instalacion:

```bash
PREFIX="$HOME/.local" ./scripts/uninstall-local.sh
```

Si ya borraste la carpeta del proyecto, el instalador deja una copia aqui:

```bash
PREFIX="$HOME/.local" "$HOME/.local/share/bc250-control-center/scripts/uninstall-local.sh"
```

### Paquetes por distribucion

Los paquetes generados localmente quedan juntos en:

```text
packaging/packages/arch/      Arch, CachyOS, Manjaro
packaging/packages/fedora/    Fedora, Nobara
packaging/packages/bazzite/   Bazzite / Fedora Atomic
```

Arch/CachyOS/Manjaro:

```bash
sudo pacman -U packaging/packages/arch/bc250-control-center-git-*.pkg.tar.zst
```

Fedora/Nobara:

```bash
sudo dnf install packaging/packages/fedora/bc250-control-center-*.noarch.rpm
```

Bazzite/Fedora Atomic:

```bash
sudo rpm-ostree install packaging/packages/bazzite/bc250-control-center-*.noarch.rpm
systemctl reboot
```

## Primer uso

1. Abre `bc250-control-center`.
2. Entra a **BC250**.
3. Pulsa **Preparar dependencias**.
4. Revisa **Informacion > Uso seguro BC250** antes de aplicar OC, 40CU o cambios persistentes.

## Funciones principales

- Procesos agrupados por aplicacion.
- Vista de rendimiento con CPU, memoria, swap, GPU, disco, ventiladores y sensores.
- Panel BC250 con metricas en vivo.
- GPU mediante safe-points del TOML de `cyan-skillfish-governor-smu`.
- CPU OC temporal y persistente con limites visibles.
- Dashboard y acciones 40CU/24CU con `bc250-cu-live-manager`.
- Historial local en JSONL.
- Traducciones desde configuracion.

## Herramientas externas y creditos

BC250 Control Center no reemplaza ni reclama autoria sobre las herramientas comunitarias. La app las instala, clona o ejecuta desde sus fuentes oficiales cuando corresponde.

Repositorios usados o referenciados:

- `cyan-skillfish-governor`: https://github.com/Magnap/cyan-skillfish-governor
- `bc250_smu_oc`: https://github.com/bc250-collective/bc250_smu_oc
- `bc250-cu-live-manager`: https://github.com/WinnieLV/bc250-cu-live-manager
- `bc250-40cu-unlock`: https://github.com/duggasco/bc250-40cu-unlock

Mas detalles en `docs/THIRD_PARTY_NOTICES.md`.

## Seguridad

Overclock, 40CU y cambios de frecuencia pueden causar congelamientos, apagones, perdida de datos o dano de hardware. Cada BC-250 es distinta. Prueba por pasos y bajo tu responsabilidad.

## Estructura rapida

```text
mvc/                 aplicacion PyQt6
scripts/             launchers e instalador local
packaging/           recetas y salidas de paquetes
docs/                creditos, arquitectura y notas del proyecto
```
