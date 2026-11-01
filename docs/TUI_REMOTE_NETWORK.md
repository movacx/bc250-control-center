# Diagnóstico y reparación de red en el TUI

En **Acceso remoto → Diagnóstico de red** se muestran el gestor de firewall,
el puerto TCP configurado, las subredes privadas conectadas y el estado de la
dirección `.local`. La pestaña también se abre con la opción del mismo nombre
en la configuración web. Cambiar TCP solo configura el servidor; la pantalla
explica que el firewall se configura por separado.

El diagnóstico se obtiene mediante `web_access.status()`, compartido con la
aplicación gráfica. UFW puede consultarse desde su configuración guardada cuando
su estado requiere root; el TUI lo distingue de una consulta de reglas activas.
Los estados desconocido, gestor personalizado/múltiple, sin red y helper antiguo
muestran la orientación correspondiente. No se ofrecen reparaciones cuando el
backend no las admite ni cuando el acceso por LAN está desactivado.

**Configurar firewall de la red local** muestra la confirmación con puerto y
subredes. Reutiliza `web_access.repair_firewall()`: el helper protegido verifica
el gestor como administrador y configura únicamente el puerto de la app para
las redes privadas detectadas, en UFW o firewalld. No desactiva el firewall.

**Reparar dirección local** usa la reparación mDNS de escritorio: Avahi,
resolución local y comprobación del resultado. Se informa de sus cambios antes
de solicitar autorización. La IP sigue disponible como alternativa.

Ambas acciones pasan por `guarded` y `ui.run`, que registra el agente textual
Polkit en la consola del TUI. No se solicita contraseña durante el diagnóstico
periódico. Cancelar la confirmación o expirar la vista protegida antes de iniciar
la acción impide ejecutar la reparación. Al terminar se refresca el estado y se
muestran los errores, si los hay. Las reglas correctas no garantizan acceso si
el router aísla a los clientes o el teléfono está en otra red.

Validación: 10 pruebas de integración TUI, 10 del helper de firewall y 19 de
resolución local. Se comprobaron UFW, firewalld, cambio de puerto/subred,
confirmación, consola, cancelación, privacidad, errores y representación en
inglés/español de 32 a 80 columnas. También se dibujó la pestaña con curses real
en terminales PTY de 80×24 y 60×14, usando datos simulados y sin modificar el
firewall de la máquina.
