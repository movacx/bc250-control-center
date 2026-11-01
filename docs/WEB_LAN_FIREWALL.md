# Diagnóstico del firewall para acceso web local

Acceso remoto comprueba el firewall cuando está habilitado el acceso por LAN.
Distingue este diagnóstico del de resolución del nombre `.local`: una IP válida
no evita el bloqueo del puerto por UFW o firewalld.

El botón **Configurar firewall de la red local** solicita autorización mediante
Polkit. El helper protegido vuelve a detectar el gestor activo y las subredes
privadas conectadas, permite el puerto TCP configurado y comprueba el resultado.
En UFW las reglas son persistentes; en firewalld se agregan al estado actual y a
la configuración permanente de la zona de la interfaz. No se desactiva el firewall
ni se abre el puerto a todo Internet. Se excluyen interfaces virtuales y VPN.

El diagnóstico periódico no solicita contraseña. Cuando UFW impide consultar su
estado sin root, se lee su configuración y se muestra un posible bloqueo; la
reparación exige verificar el estado real como administrador antes de escribir.
Ante reglas conflictivas, varios gestores o un firewall personalizado, conserva
la configuración y avisa. Si falla la comprobación final, intenta retirar solo
las reglas que acaba de agregar y comunica cualquier fallo de esa reversión.

Las reglas siguen limitadas a las subredes detectadas al aplicar la reparación.
Al cambiar de red puede ser necesario repetirla. La aplicación no verifica desde
el teléfono: aislamiento Wi-Fi, VPN del cliente o filtros del router pueden
impedir la conexión incluso con reglas correctas. El teléfono necesita estar en
la misma red y admitir mDNS para usar `.local`; siempre se ofrece también la IP.

Instalaciones anteriores deben actualizar el paquete para disponer del helper.
