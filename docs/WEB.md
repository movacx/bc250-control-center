# Interfaz web local

Tercer frontend de BC250 Control Center, junto al escritorio y la TUI: una página que sirve la propia placa en la red local, para abrirla desde el móvil, la tableta u otro PC. No es un panel remoto genérico: llama a los mismos servicios (`bc250cc.application`, el controlador que usa la TUI) y no reimplementa nada de hardware.

```
bc250-control-center web [--host 127.0.0.1] [--port 8250]
```

Se enciende y se apaga desde **Acceso remoto → Telemetría web** en el escritorio, que también muestra la dirección, la clave de acceso, copia ambas y ofrece «Iniciar con la sesión» (servicio de usuario de systemd, `bc250-web.service`; sobrevive al modo juego de Bazzite porque vive en el gestor de usuario, que el cambio de modo no reinicia).

## Estructura

| Parte | Dónde |
| --- | --- |
| Servidor (solo biblioteca estándar de Python) | `frontends/web/server.py`, `data.py`, `jobs.py`, `actions.py` |
| Interfaz React (código fuente, solo para desarrollar) | `frontends/web/app/` |
| Interfaz compilada, **versionada** | `frontends/web/dist/` |
| Ajustes, clave, servicio de usuario | `src/bc250cc/infrastructure/web_control.py` (vía `application/system/web_access.py`) |

Node solo hace falta para regenerar `dist/` (`scripts/development/build-web.sh`); instalar o ejecutar no lo necesita, y todo funciona sin internet (sin CDN ni fuentes externas). El tema sale del propio escritorio: el servidor genera `/theme.css` con `frontends/desktop/theme.theme_palette` (estilo formal, acento violeta), así que claro/oscuro nunca se desincronizan de la aplicación. Los textos salen de los catálogos del escritorio: el build recoge cada `t("…")` en `dist/strings.json` y `/api/i18n` devuelve solo esas frases ya traducidas.

## Seguridad

- **Clave obligatoria**: 8 caracteres sin ambigüedades (`XXXX-XXXX`), guardada en `~/.config/bc250-control-center/web.json` (0600). No existe modo sin clave. Comparación en tiempo constante; 5 fallos bloquean al origen 5 minutos.
- Cookie de sesión `HttpOnly; SameSite=Strict` (12 h), token CSRF en todo POST, comprobación de `Origin` y de `Host` (contra DNS rebinding), sin CORS, `Content-Security-Policy` sin `unsafe-inline`, solo GET y POST.
- Escucha en `127.0.0.1` salvo que el usuario active «Accesible desde la red local».
- Nada se registra: ni rutas, ni IPs, ni la clave (el servidor no escribe un log de peticiones; la salida de las tareas pasa por `redact_machine`).
- **Lista cerrada de acciones** (`actions.py`): cada una valida sus parámetros y llama a un método del servicio existente. No hay endpoint que reciba un comando. Un cambio de hardware exige confirmación explícita; las zonas de riesgo (+2000 MHz, desbloqueo de núcleos, tabla de CU en vivo, curva de voltaje, método kernel, parar el governor, ventilador por debajo del 30 %) piden además la clave otra vez. El servidor lo exige, no solo la página.

## Privilegios: la decisión

El servidor corre como el usuario y varias acciones necesitan root (pkexec/polkit, ayudantes de `privileged/`). Se reutiliza exactamente el mecanismo de la TUI por SSH (commit «Polkit: las acciones que ya piden contraseña también la piden por SSH»):

1. Cada acción es una *tarea* con su propio pseudo-terminal (`frontends/tui/console.py`). El servicio llama a pkexec/sudo y estos piden la contraseña en ese terminal; `pkttyagent` queda registrado para el proceso del servidor mientras dure la tarea, igual que en la TUI.
2. La página muestra la salida de la tarea y, mientras corre, un campo de contraseña. Lo escrito va **solo** al `stdin` de ese pty: no se guarda, no se registra, no hay `sudo -S` ni la contraseña en argumentos o variables de entorno.
3. Se acepta la contraseña únicamente desde este mismo equipo (`127.0.0.1`/`::1`). Desde otro equipo de la red se rechaza, **porque el tráfico no va cifrado** y la contraseña de administrador no debe cruzar el aire en claro, salvo que el dueño active «Aceptar la contraseña de administrador desde la red» (con la advertencia visible). Sin esa opción, desde el móvil se usan las acciones que no piden contraseña (lecturas y las que el polkit ya permite sin ella) y para el resto se usa el PC o la TUI por SSH.
4. No se debilita ninguna política polkit ni se añaden reglas: la web no concede privilegios, solo es otra puerta hacia las mismas acciones, con las mismas ventanas de autorización.

Qué no cubre: HTTPS. Sin dependencias nuevas no hay forma razonable de emitir certificados que el móvil acepte; por eso la clave y la contraseña se tratan como se explica arriba y la página avisa de que debe usarse solo en una red de confianza.

## Pantallas

Panel de control, CPU / SMU, Unidades de cómputo, Governor de GPU, Rendimiento (sensores con lista/gráficas y las vistas por CPU, GPU, VRAM, RAM, disco y red, con ejes 1-2-5 y ventana de 2 minutos) y Ventiladores (manual y curva automática), más Configuración (tema y salir). Quedan fuera por ahora: Ajustes adicionales, Procesos, Caja negra, Acceso remoto, Firmware, el laboratorio de voltaje personalizado y el control de ventiladores desde el arranque.
