# Recuperación de red al arrancar la web

Se capturó el fallo antes de reiniciar el servicio. El proceso había iniciado
unos diez segundos antes de que Wi-Fi completara DHCP. El puerto escuchaba y
loopback respondía 200, pero una petición por la dirección LAN devolvía 403 y
el alias local no estaba publicado.

La causa tenía dos partes: la lista de redes permitidas se calculaba solo al
arrancar, y el publicador mDNS se deshabilitaba por completo cuando esa primera
lista estaba vacía. Esperar un tiempo fijo o cambiar el orden de arranque no
resolvería una reconexión o un cambio posterior de red.

La web observa ahora las redes físicas privadas mientras el acceso LAN está
habilitado. Actualiza la lista permitida al aparecer o desaparecer la conexión;
un fallo de descubrimiento la vacía y se reintenta. No se amplía el acceso a
todas las redes privadas ni se aceptan redes declaradas mediante cabeceras HTTP.
El observador no se ejecuta en modo solo loopback.

El publicador mDNS permanece preparado aunque todavía no haya dirección y
revisa los cambios periódicamente. Ante una nueva IP, HTTPS vuelve a comprobar
el certificado y sustituye el adaptador TLS completo para las conexiones nuevas.
Se conserva la autoridad local y las conexiones existentes. Estos cambios no
reinician el servidor ni invalidan sesiones o permisos de los navegadores.

Validación: 230 pruebas de web, acceso remoto de escritorio y dependencias web
pasan. Incluyen arranque sin red, conexión tardía, desconexión, reconexión en
otra subred, fallo de descubrimiento, reintento de certificados y cierre del
observador. Una prueba con servidor HTTPS real verifica acceso 403 → 200 → 403,
dos IP en los certificados efectivamente servidos y la misma autoridad local.
La entrada principal también se prueba con la red inicialmente vacía para
evitar volver a condicionar los observadores a esa instantánea.

Se aplicó la corrección al servicio existente y se verificaron respuestas 200
con la autoridad local por loopback, IP LAN y `bc250cc.local`; el alias vuelve
a ser la dirección preferida. No se reinició la PC ni se desconectó su Wi-Fi.
La prueba de un reinicio físico completo queda para la siguiente comprobación
del usuario.
