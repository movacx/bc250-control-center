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

/** Solo hace falta en el navegador y en Android. */
actual fun abrirDireccion(direccion: String) {
}

actual fun paginaDeLaDireccion(): String {
    return ""
}

actual fun anotarPagina(pagina: String) {
}
