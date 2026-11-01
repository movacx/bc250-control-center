# Caja negra en la web

La barra lateral incorpora **Sistema → Caja negra**. Se mantiene la autenticación
por código/QR y sesión existente, incluida la consulta desde dispositivos con
permiso de monitorización. La barra inferior móvil conserva sus accesos actuales.

La vista de grabación usa el mismo servicio que el escritorio, con sus diez
columnas, las muestras más recientes primero y el estado de fin de la sesión.
Muestra como máximo las últimas 500 lecturas. En PC se presenta una tabla de 50
filas por página; en móvil, grupos de 20 lecturas desplegables. Cada lectura
móvil muestra también temperaturas de GPU/CPU, potencia y frecuencia CPU sin
necesidad de desplegarla. Se omiten la etiqueta y el texto redundantes del estado. Al desplazarse o
paginar se congelan las filas para leerlas; «Seguir lecturas recientes» recupera
el seguimiento. No inicia una grabación automáticamente: si no hay datos, indica que debe
iniciarse con «Iniciar grabación».

Diagnóstico completo comparte los colectores, categorías y ocultación de datos
personales del escritorio. Se recoge al abrir la vista, en segundo plano. Hay
búsqueda, categorías y secciones desplegables. Cada cuadro de texto incluye un
tirador visible para ajustar su altura con ratón o dedo, o con las flechas del
teclado. Un doble clic adapta la altura al texto. La recolección se comparte entre
peticiones concurrentes y las actualizaciones explícitas se limitan a una cada
30 segundos. Las respuestas y secciones tienen límites de tamaño.

La consulta web no ejecuta Polkit. Los registros del kernel que el usuario no
puede leer no se elevan; cada colección conserva su propia caché de lectura,
propagada a sus trabajadores. El escritorio conserva su comportamiento de
solicitar autorización cuando corresponde.

`GET /api/blackbox` está detrás de la comprobación de sesión. Los dispositivos
con permiso de control pueden iniciar y detener la grabación y configurar
«Iniciar con la sesión» mediante `POST /api/blackbox/control`. La ruta exige
sesión, CSRF y conexión HTTPS o local, valida una operación cerrada y reutiliza
los tres métodos del escritorio. Los dispositivos de solo monitorización
conservan la lectura y ven los controles deshabilitados. No se ofrece abrir
carpetas, descargar ni borrar registros. Si el servidor sigue ejecutando código
anterior y devuelve 404, se indica reiniciar el acceso web desde escritorio. El texto del diagnóstico se dibuja como texto, sin interpretar HTML.

Pruebas: `tests/web/test_blackbox.py`, con unittest en el entorno web instalado,
cubre autenticación, límites, solo lectura, errores, agrupación y separación de
las políticas de lectura del kernel. Se comprobó además la interfaz con datos
simulados en Firefox para PC y teléfono: paginación, pausa del seguimiento,
búsqueda, expansión y contenido que contiene etiquetas HTML.
