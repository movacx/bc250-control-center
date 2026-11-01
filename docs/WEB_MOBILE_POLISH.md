# Ajustes móviles de acceso web

La web móvil comparte ahora el flujo de autenticación de PC: un cuadro compacto
con contexto de la operación, contraseña y botones para autenticar o cancelar.
No incluye una terminal ni el encabezado decorativo anterior. Las confirmaciones
y diálogos comunes mantienen el nombre de la acción dentro del contenido.

Después de autenticar se muestra el progreso compacto. Se puede abrir la salida
para diagnóstico; las operaciones fallidas muestran los detalles. Cancelar
interrumpe el trabajo. El envío conserva la protección HTTPS y los permisos de
la sesión, limpia la contraseña y admite un nuevo intento.

El dashboard móvil muestra CU y VRAM en pequeño bajo el título del encabezado,
sin la tarjeta AMD BC-250. Incorpora OC registrado y escala, CU efectivas, uso del disco
y BIOS. Conserva los paneles principales móviles de CPU y GPU. GDDR6 presenta
solo los ocho chips en dos columnas y el control de monitorización de ancho completo, sin título,
promedio, punto caliente ni barra de progreso duplicada en el dashboard. Usa muestras
recientes del trabajo como las del colector. Las muestras del trabajo con más de
15 segundos no se reutilizan; los chips sin lectura muestran un guion.

Validación: compilación web y `node tests/web/mobile-ui-check.mjs` para paridad del
dashboard y muestras GDDR6 recientes, antiguas, parciales y del colector. En
Firefox headless a 390 × 844, con API simulada, se verificaron autenticación,
error de envío, reintento, cancelación, bloqueo sin permiso, monitorización en
segundo plano y terminal de diagnóstico sin encabezado. No se ejecutan cambios
de hardware en estas comprobaciones.
