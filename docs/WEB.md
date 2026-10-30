# Interfaz web de BC250 Control Center

La guía actual está en [Acceso web](WEB_ACCESS.md). El [diagrama de arquitectura y mapa de archivos](WEB_ARCHITECTURE.md) explica las capas y el flujo de autorización.

La interfaz usa React para el móvil y los servicios existentes de CPU, GPU, CU,
ventiladores y monitoreo. El servidor HTTPS usa Cheroot con límites de conexiones y acceso a subredes domésticas directamente conectadas. Los dispositivos nuevos solo pueden monitorizar; el propietario habilita o revoca el control desde Acceso remoto, con el QR visible en una única tarjeta. HTTPS protege las credenciales. La clave web se pide
al iniciar sesión; las operaciones mantienen su confirmación sin repetirla.
Cada navegador dispone de una terminal privada como usuario normal, local o
por OpenSSH con host key fijada. Sudo autentica los helpers existentes en esa
terminal, sin diálogos de escritorio ni cambios de sudoers o políticas Polkit.

Los cambios de frecuencias de GPU se realizan desde perfiles. SSH está en la
tarjeta del Dashboard. Los controles detallados de escritorio conservan su GUI.
