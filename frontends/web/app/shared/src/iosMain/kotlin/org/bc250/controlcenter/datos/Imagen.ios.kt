package org.bc250.controlcenter.datos

actual val puedeElegirImagen: Boolean = false

actual fun elegirImagen(alElegir: (ImagenLogo) -> Unit) {
}

actual fun reescalarImagen(porcentaje: Int, alTerminar: (ImagenLogo) -> Unit) {
}
