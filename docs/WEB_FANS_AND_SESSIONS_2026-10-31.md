# Servicio de ventiladores y sesiones recordadas

La web incluye el servicio de ventiladores dentro del mismo panel de control:
estado, persistencia de arranque, activación/desactivación y sincronización de
la política guardada. El editor permite guardar su curva y activar el servicio
en una sola operación. Todas las acciones requieren el permiso de hardware,
confirmación y el flujo de autenticación existente. No se activa el servicio
automáticamente al abrir la página. Se comprueba nuevamente si el ventilador
está cedido a otro programa antes de ejecutar la operación.

La duración y el permiso de cada navegador permanecen en el registro privado.
Ahora la cookie puede recuperar esa sesión después de reiniciar el servidor:
se comprueba su huella, vencimiento y vínculo con la clave de acceso vigente.
El token CSRF se deriva con HMAC a partir de esa clave y la cookie aleatoria;
no se guarda la cookie ni el token CSRF en disco. El permiso se consulta de
nuevo en cada petición y no se infiere del código visible del dispositivo.

El arranque conserva los dispositivos de la clave actual y elimina los de
claves anteriores. Cerrar sesión, revocar el dispositivo, cambiar la clave o
alcanzar el plazo elegido invalidan el acceso. No se renueva automáticamente
un plazo fijo de 30 días. Un error temporal de conexión no borra del cliente
una sesión que ya estaba autenticada.

El recuerdo corresponde al mismo navegador y dirección: la IP y el nombre
local tienen cookies distintas. Borrar las cookies o usar una sesión privada
nueva requiere autenticarse como un dispositivo nuevo.

Las pruebas cubren activación y sincronización con la curva editada, retirada
de una política desactivada, bloqueo por control externo, falta de política,
validación de parámetros y rechazo del dispositivo de solo monitorización.
También se comprueban la recuperación de 30 días y permisos al crear otro
servidor, CSRF después de reinicio, vencimiento, revocación, cambio de clave y
rechazo de un código de dispositivo presentado como cookie.

Validación: 381 pruebas de web, TUI y acceso remoto del escritorio, más una
prueba de enlace de otro servidor, pasan. Chromium con tamaño móvil comprueba
un reinicio real y recarga sin perder plazo o permisos, tolerancia a un error
503 temporal y los botones confirmados de activación del servicio y guardado
de curva con persistencia. Las acciones de ventilación del navegador se
interceptan; la prueba no modifica PWM ni activa el servicio de la placa.
