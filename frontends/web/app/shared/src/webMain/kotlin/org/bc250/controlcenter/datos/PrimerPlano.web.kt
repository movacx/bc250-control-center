package org.bc250.controlcenter.datos

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun alCambiarVisibilidad(avisar: (Boolean) -> Unit): Unit =
    js("{ document.addEventListener('visibilitychange', () => avisar(!document.hidden)); }")

@OptIn(kotlin.js.ExperimentalWasmJsInterop::class)
private fun quitarInicio(): Unit = js("{ document.getElementById('inicio')?.remove(); }")

actual fun vigilarPrimerPlano() {
    quitarInicio()
    alCambiarVisibilidad { seVe -> PrimerPlano.visible.value = seVe }
}
