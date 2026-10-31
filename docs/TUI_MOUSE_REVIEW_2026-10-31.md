# Revisión complementaria del TUI — 31 de octubre de 2026

Esta revisión actualiza la decisión anterior sobre el ratón: el usuario pidió
soporte completo sin perder la navegación por teclado. No se recupera el modo
táctil. La sección de sensores del TUI conserva su implementación.

- Ratón: navegación lateral, pestañas, opciones, flechas de valores, selección
  exacta de celdas CU, rueda, barras de desplazamiento y diálogos locales.
  El contenido situado detrás de un diálogo o una consola activa no recibe
  clics. Se rechazan las coordenadas anteriores a un cambio de tamaño y las
  acciones correspondientes a datos que ya cambiaron desde el último dibujo.
- Navegación lateral agrupada como en escritorio; Firmware y Configuración
  permanecen al pie, incluso al reducir la terminal. Se conservan los atajos.
- Dashboard contrastado con el escritorio: voltaje CPU, OC registrado en este
  arranque, uso del disco, filas VRM ausentes explícitas, núcleos ocultos y
  propietario real del control de ventiladores. Incluye instalación y gestión
  de BC250-Telemetry mediante el flujo con confirmación y consola existente.
- Curva automática: guardar y activar el servicio de arranque o sincronizarlo
  desde el propio editor. Los puntos editados se conservan si falla el servicio.
  Desactivar la curva también retira la política anterior del servicio.

## Cierre del escritorio

El diario y el volcado registraron SIGABRT durante un cierre que ya estaba en
curso. Un QRunnable terminó una lectura e intentó emitir señales de un QObject
destruido. El registro no identifica qué inició el cierre. Se comprueba la vida
del emisor y se protege también la carrera entre comprobación y emisión.
Las pruebas incluyen eliminar el QObject mientras un trabajador real de Qt
está bloqueado y comprobar que el proceso termina correctamente.

## Validación

969 pruebas del TUI, dashboard y ventiladores del escritorio pasan en el host.
Incluyen terminales reales simuladas xterm/Linux, navegación con informes SGR
de ratón, cambio de tamaño, salida normal y la regresión de cierre de Qt.
Ruff y la comprobación de espacios del diff pasan.

La matriz reutiliza las imágenes preparadas descritas en
`TUI_REVIEW_2026-10-31.md`: instalación local, ejecución del punto de entrada,
rechazo de entrada no interactiva, 161 pruebas TUI por perfil y desinstalación.
Los contenedores no reciben dispositivos, puertos del host ni privilegios.
Las escrituras de hardware se simulan; esto no certifica el arranque físico,
PAM/Polkit ni lecturas de una placa en cada distribución.
