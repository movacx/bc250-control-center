package org.bc250.controlcenter.datos

import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO

actual fun crearClienteHttp(): HttpClient {
    return HttpClient(CIO)
}

/** Aquí la dirección la escribe la persona o la trae el código QR. */
actual fun direccionInicial(): String {
    return ""
}

/** Quien inicia la aplicación dice cómo se abre una dirección. */
var abridorDeDirecciones: (String) -> Unit = {}

actual fun abrirDireccion(direccion: String) {
    abridorDeDirecciones(direccion)
}

actual fun paginaDeLaDireccion(): String {
    return ""
}

actual fun anotarPagina(pagina: String) {
}
