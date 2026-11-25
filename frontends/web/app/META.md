# Meta de la aplicación web y móvil

Esta meta manda sobre cada sesión de trabajo. El trabajo no está terminado mientras falte un punto.

1. **Copia fiel.** Cada página, a 1920×1000 con los mismos datos, mide lo mismo que en el escritorio
   (`scripts/qa/web/referencia_escritorio.py`): posición y tamaño de cada tarjeta, a lo sumo 2 px de diferencia;
   mismos colores, letras, textos, iconos y estados.
2. **Sin recortes.** Todo botón, opción, diálogo y lista del escritorio existe y funciona en la web,
   incluidos Ajustes adicionales, Procesos, Caja negra, Firmware, Acceso remoto y Configuración.
3. **Independiente.** `scripts/install-web.sh` instala solo la web: sin PyQt6, sin escritorio.
   Las operaciones pasan por los mismos ayudantes protegidos, con `sudo` en la consola de la web.
4. **Seguro.** Se conserva el acceso con clave o QR, HTTPS, CSRF, permisos por dispositivo y la lista cerrada de acciones.
5. **Idiomas.** Los 30 idiomas del escritorio, con los mismos textos en inglés como clave.
6. **Móvil.** La misma base en Android (`androidApp`), con pantallas pensadas para el teléfono, lista para Play Store.
7. **Probado.** Cada página se abre en el navegador, se compara con la referencia y se prueba cada acción con un servicio de ejemplo.

## Cómo se escribe el código

- Nombres y comentarios en español; claro antes que corto.
- Una función hace una cosa. Nada de lambdas encadenadas en una sola línea: se abren en varias o se les da nombre.
- Sin números sueltos repetidos: las medidas viven en `tema/Medidas.kt`.
- Los textos visibles se piden con `t("English source text")`, la misma clave que usa el escritorio.
- Un archivo por página en `paginas/`; las piezas comunes en `componentes/`.

## Módulos

| Módulo | Contenido |
| --- | --- |
| `shared` | Datos, tema, componentes y páginas compartidas (Compose). |
| `webApp` | Entrada del navegador. |
| `androidApp` | Entrada de Android. |
