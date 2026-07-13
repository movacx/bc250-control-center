# Arquitectura MVC - BC250 Control Center

Este proyecto mantiene una estructura MVC simple y directa.

## Capas principales

```text
mvc/
├── Controller/     # Puente entre la vista y el servicio
├── Model/          # Objetos simples de datos
├── Repository/     # Acceso a sistema, archivos, comandos y herramientas externas
├── service/        # Reglas, filtros y validaciones
└── View/           # Interfaz PyQt6, frames, estilos, componentes e idiomas
```

## Repository

`SistemaRepository` se mantiene como fachada principal para no romper el flujo actual del controlador y el servicio.
La implementacion pesada se separo en archivos mas pequenos:

```text
Repository/
├── sistema_repository.py        # fachada compatible y metricas generales
├── terminal_repository.py       # apertura de terminales graficas
├── dependencias_repository.py   # preparacion de dependencias y herramientas BC250
├── gpu_repository.py            # governor, rango GPU y laboratorio de voltaje
├── cpu_repository.py            # CPU OC temporal
├── cu_repository.py             # dashboard y acciones 40CU
├── historial_repository.py      # historial JSONL compacto
└── configuracion_local.py       # rutas locales, Data y ResourceTools
```

## Rutas locales de usuario

La app guarda datos de ejecucion en:

```text
~/.local/share/bc250-control-center/Data/
~/.local/share/bc250-control-center/ResourceTools/
```

`Data` contiene historial, metricas y datos locales.
`ResourceTools` contiene repos clonados o herramientas preparadas por la app.

## Dashboard 40CU

El frame 40CU prioriza `WinnieLV/bc250-cu-live-manager` para mostrar el dashboard real.
Si el sistema requiere sudo interactivo, el boton de refrescar no mezcla el fallback del mapa viejo con errores de sudo.
En ese caso se informa al usuario que debe usar `Abrir dashboard en terminal` para autenticar.

El flujo operativo de 40CU usa `WinnieLV/bc250-cu-live-manager`. `bc250-40cu-unlock` queda como referencia/documentacion comunitaria y credito upstream; ya no se clona como dependencia de ejecucion ni confirma el live routing actual.

## Historial

El historial usa JSONL local. Para no saturar archivos, cuando supera 26 registros se compacta automaticamente y conserva los ultimos 6 eventos.
