# Sesiones y gráficas web — 31 de octubre de 2026

Actualización posterior: [Servicio de ventiladores y sesiones recordadas](WEB_FANS_AND_SESSIONS_2026-10-31.md)
describe cómo se conservan ahora las sesiones al reiniciar. La limpieza de
arranque se limita a dispositivos vinculados a claves anteriores.

Se reprodujo el login correcto seguido de una respuesta 401 a los dos segundos.
Había un servidor manual atendiendo el puerto y un servicio de usuario que
reintentaba arrancar. La construcción del segundo servidor borraba el registro
de dispositivos antes de descubrir que el puerto estaba ocupado.

El registro se limpia ahora después de adquirir el puerto. Un arranque fallido
no invalida las sesiones existentes ni publica un alias mDNS competidor.
Activar «Iniciar con la sesión» habilita el servicio para el futuro y solo lo
inicia inmediatamente si no hay un servidor escuchando. Desactivar ese ajuste
no detiene el acceso web actual; para ello existe «Detener acceso web».

La pantalla de acceso ofrece `bc250cc.local` cuando está verificado y conserva
las direcciones numéricas como alternativa. Mientras el alias no está publicado
no lo sustituye por el nombre de la distribución.

También se reprodujeron errores 500 al consultar RAM, disco y red. El catálogo
de vistas detalladas solo tiene entradas CPU/GPU/VRAM: buscar obligatoriamente
una entrada para los otros recursos fallaba. Ahora se usan sus historiales y
escalas generales, conservando las unidades de porcentaje y bytes por segundo.
Una vista inválida o de otro recurso vuelve al resumen correspondiente.

Las regresiones incluyen tres intentos reales de abrir un puerto ya ocupado,
comprobando que el navegador autenticado conserva sesión y permisos; activar y
desactivar persistencia sin duplicar o detener el servidor; y las tres gráficas
con valores, series, tarjetas y escalas, también con parámetros de vista erróneos.
Las 185 pruebas web pasan.

La revisión ampliada con acceso remoto de escritorio y empaquetado pasa 545
pruebas, con dos omisiones por las características del host Bazzite. Se
comprobó además en Chromium con tamaño móvil que las tres selecciones muestran
una gráfica SVG y cuatro tarjetas, y que la sesión sobrevive al activar y
desactivar el inicio con la sesión y a doce segundos adicionales de consultas.
