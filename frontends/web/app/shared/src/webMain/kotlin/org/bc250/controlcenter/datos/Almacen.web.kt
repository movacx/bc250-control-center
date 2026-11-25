package org.bc250.controlcenter.datos

/** El navegador ya sabe a qué equipo pertenece la página y guarda su propia sesión. */
actual val pideDireccion: Boolean = false

actual fun leerGuardado(clave: String): String {
    return ""
}

actual fun guardarDato(clave: String, valor: String) {
}
