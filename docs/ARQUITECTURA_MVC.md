# Arquitectura MVC — BC250 Control Center

La aplicación conserva una arquitectura MVC con una única interfaz PyQt6 y una fachada de Controller como límite obligatorio entre frontend y backend.

## Flujo principal

```text
View → Controller → service → Repository → sistema / archivos / D-Bus / herramientas
                         └── Model
Daemon → service → Repository
```

La View no importa ni accede directamente a `Repository`, `service` o `Daemon`. Las operaciones de lectura lenta o con privilegios se ejecutan fuera del hilo de interfaz y sus resultados regresan mediante señales/callbacks de Qt.

## Capas

```text
mvc/
├── Controller/     # Fachada pública consumida por la interfaz
├── Model/          # Objetos de datos y contratos simples
├── Repository/     # Sistema, archivos, procesos, hardware y herramientas externas
├── service/        # Reglas, validaciones y coordinación de repositorios
├── Daemon/         # Supervisión opcional reutilizando service/Repository
├── View/           # Única interfaz PyQt6 definitiva
├── logging_config.py
└── main.py          # Configuración de logging, QApplication y arranque
```

## Estructura definitiva de View

```text
View/
├── application.py          # Ventana principal, navegación y preferencias globales
├── components/
│   ├── async_tools.py      # Ejecución no bloqueante para la interfaz
│   ├── dialogs.py          # Ajuste adaptativo y centrado de diálogos
│   ├── page_widgets.py     # Componentes reutilizables de páginas
│   ├── sidebar.py          # Navegación lateral
│   └── widgets.py          # Tarjetas, indicadores y diálogo informativo
├── core/
│   ├── alerts.py           # Alertas inteligentes sin modificar hardware
│   ├── preferences.py      # Normalización y migración de preferencias
│   └── state.py            # Caché breve y estado compartido de frontend
├── i18n/
│   ├── backend_catalog.py  # Catálogo compatible de mensajes del backend
│   ├── catalog.py          # Textos dinámicos y de seguridad
│   ├── interface_catalog.py# Copia visible de la interfaz
│   └── __init__.py         # Resolución, formato y traducción en caliente
├── pages/
│   ├── dashboard.py
│   ├── performance.py
│   ├── processes.py
│   ├── cpu_smu.py
│   ├── gpu_governor.py
│   ├── compute_units.py
│   ├── fans.py
│   └── settings.py
└── theme/
    ├── __init__.py         # Paletas, escalado y QSS central
    └── icons/              # Iconos SVG
```

`components/` evita duplicar controles y políticas de diálogo; `pages/` agrupa módulos navegables; `core/` contiene estado y servicios exclusivos del frontend; `theme/` e `i18n/` aíslan dos preocupaciones transversales que se actualizan en caliente.

## Repositorios principales

`SistemaRepository` continúa como fachada de composición del backend. Las responsabilidades especializadas viven en módulos separados:

```text
Repository/
├── sistema_repository.py
├── terminal_repository.py
├── dependencias_repository.py
├── gpu_repository.py
├── cpu_repository.py
├── cu_repository.py
├── fan_repository.py
├── historial_repository.py
├── configuracion_local.py
└── Os_repository/          # Estrategias por distribución
```

## Estado, historial y rutas locales

Los datos de usuario se guardan bajo:

```text
~/.local/share/bc250-control-center/Data/
~/.local/share/bc250-control-center/ResourceTools/
```

El historial usa JSONL, escritura protegida y retención de hasta 1.000 registros; al compactarse conserva los 800 más recientes. La interfaz traduce los eventos estructurados al idioma activo sin alterar el registro canónico del backend.

## Operaciones BC250

Las páginas CPU, GPU, Compute Units y Fans llaman únicamente a la fachada del Controller. El Controller delega validación y reglas al servicio, que usa los repositorios especializados y las estrategias de sistema operativo. Las lecturas se invalidan y refrescan después de cada acción para evitar que la GUI muestre un estado anterior como si fuera actual.
