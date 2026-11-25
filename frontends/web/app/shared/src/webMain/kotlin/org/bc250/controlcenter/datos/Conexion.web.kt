package org.bc250.controlcenter.datos

import io.ktor.client.HttpClient
import io.ktor.client.engine.js.Js

actual fun crearClienteHttp(): HttpClient {
    return HttpClient(Js)
}

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun origenDeLaPagina(): String = js("window.location.origin")

actual fun direccionInicial(): String {
    return origenDeLaPagina()
}

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun abrirPestana(direccion: String): Unit = js("{ window.open(direccion, '_blank', 'noopener'); }")

actual fun abrirDireccion(direccion: String) {
    abrirPestana(direccion)
}

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun leerMarca(): String = js("window.location.hash.slice(1)")

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun escribirMarca(marca: String): Unit = js("{ window.history.replaceState(null, '', '#' + marca); }")

actual fun paginaDeLaDireccion(): String {
    return leerMarca()
}

actual fun anotarPagina(pagina: String) {
    escribirMarca(pagina)
}
