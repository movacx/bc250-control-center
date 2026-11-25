package org.bc250.controlcenter.datos

/**
 * Escucha un mando de juego. Cada pulsación llega con su nombre: "arriba", "abajo", "izquierda",
 * "derecha", "aceptar", "volver", "anterior" o "siguiente". Solo el navegador sabe hacerlo.
 */
expect fun escucharMando(alPulsar: (String) -> Unit)

/** Pulsa lo que tiene el foco, como la tecla Intro. */
expect fun pulsarEnfocado()
