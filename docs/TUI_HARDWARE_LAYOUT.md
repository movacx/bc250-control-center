# Organización de hardware en el TUI

CPU, CU, governor y ajustes adicionales conservan los recuadros, perfiles y
botones del modelo de presentación. Los recuadros se apilan en terminales
estrechas y los grupos de botones se distribuyen según el espacio disponible.
Los botones mantienen bordes de texto incluso en modo monocromo y los perfiles
muestran explícitamente cuál está seleccionado.

CPU reúne perfiles, prueba de escala, aplicar y persistencia de arranque en
Control de hardware. Sensores y recuperación de núcleos conservan vistas
separadas. La escala editable aparece cuando se habilita el modo manual.

CU reúne la matriz WGP, aplicar y guardar/instalar/quitar el servicio en la vista
principal. Los registros y el estado bruto permanecen en Diagnóstico de
registros. Se conservan las comprobaciones del backend protegido y las
confirmaciones existentes.

Governor reúne selección de perfiles, rango, aplicar, persistencia y servicio.
Elegir un perfil prepara el rango; no ejecuta cambios hasta Revisar y aplicar.
El guardado para arranque queda deshabilitado mientras hay un rango pendiente,
para evitar guardar accidentalmente el rango anterior. La exportación a Decky
permanece al final del formulario. Laboratorio de voltaje y Sensores conservan
sus pestañas dedicadas.

En ajustes adicionales cada grupo muestra su estado y permite desplegar sus
opciones con Configurar. Abrir o cerrar un grupo no ejecuta acciones del
sistema. Memoria, controladores y reescalado conservan su organización temática.

Los destinos de teclado se ordenan por su posición dibujada y se remapean las
zonas del ratón. Tab sigue el orden visual; las flechas horizontales recorren
los perfiles o botones de una fila aunque tengan acciones Editar intercaladas.
Las flechas verticales eligen el control de la siguiente fila más próximo a la
columna actual. Las acciones deshabilitadas se omiten y la página sigue
pudiendo desplazarse por contenido sin botones.

Validación: 11 pruebas del flujo de hardware, 10 de red TUI y las 12 pruebas
existentes de contenido/layout ejecutables sin fixtures. Incluyen selección
sin aplicar, cancelación, confirmaciones, persistencia visible, límites de ancho,
propiedad de zonas interactivas y navegación entre perfiles. Se dibujaron las
cuatro secciones y todas sus pestañas con curses en PTY de 60×14, 80×24 y
120×40, usando datos simulados en inglés y español. No se aplicaron cambios al
hardware durante estas comprobaciones.
