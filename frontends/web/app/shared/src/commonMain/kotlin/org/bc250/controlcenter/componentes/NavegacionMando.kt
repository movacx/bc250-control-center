package org.bc250.controlcenter.componentes

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusManager
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalInputModeManager
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.escucharMando
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.pulsarEnfocado

/** Las páginas, en el orden de la barra lateral: los gatillos L y R pasan de una a otra. */
private val PaginasDelMando = listOf(
    "dashboard", "cpu", "cu", "gpu", "extras", "performance", "fans", "processes", "black_box", "remote", "firmware",
)

/** Mueve el foco con un mando de juego, si la preferencia está encendida. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun NavegacionMando(aplicacion: Aplicacion) {
    val foco = LocalFocusManager.current
    val entrada = LocalInputModeManager.current
    val encendida = aplicacion.preferencias.logico("gamepad_navigation")
    LaunchedEffect(encendida) {
        if (encendida) {
            escucharMando { boton ->
                if (aplicacion.preferencias.logico("gamepad_navigation")) {
                    entrada.requestInputMode(InputMode.Keyboard)
                    atenderMando(boton, aplicacion, foco)
                }
            }
        }
    }
}

private fun atenderMando(boton: String, aplicacion: Aplicacion, foco: FocusManager) {
    when (boton) {
        "arriba" -> mover(foco, FocusDirection.Up, FocusDirection.Previous)
        "abajo" -> mover(foco, FocusDirection.Down, FocusDirection.Next)
        "izquierda" -> mover(foco, FocusDirection.Left, FocusDirection.Previous)
        "derecha" -> mover(foco, FocusDirection.Right, FocusDirection.Next)
        "aceptar" -> pulsarEnfocado()
        "volver" -> aplicacion.volverAtras()
        "anterior" -> cambiarPagina(aplicacion, -1)
        "siguiente" -> cambiarPagina(aplicacion, 1)
    }
}

private fun mover(foco: FocusManager, direccion: FocusDirection, siNoHay: FocusDirection) {
    if (!foco.moveFocus(direccion)) {
        foco.moveFocus(siNoHay)
    }
}

private fun cambiarPagina(aplicacion: Aplicacion, paso: Int) {
    val lugar = PaginasDelMando.indexOf(aplicacion.pagina).coerceAtLeast(0)
    val total = PaginasDelMando.size
    aplicacion.irA(PaginasDelMando[(lugar + paso + total) % total])
}
