package org.bc250.controlcenter.datos

private val guardados = mutableMapOf<String, String>()

actual val pideDireccion: Boolean = true

actual fun leerGuardado(clave: String): String {
    return guardados[clave] ?: ""
}

actual fun guardarDato(clave: String, valor: String) {
    guardados[clave] = valor
}
