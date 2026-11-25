package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales

/** Las ventanas de Ajustes adicionales: el detalle de una fila y los pasos de una operación. */
@Composable
internal fun DialogosExtras(estado: EstadoExtras) {
    val detalle = estado.detalle
    if (detalle != null) {
        DetalleFila(estado, detalle)
    }
    val paso = estado.dialogo
    if (paso != null) {
        PasoOperacion(estado, paso)
    }
}

@Composable
private fun DetalleFila(estado: EstadoExtras, fila: JsonObject) {
    val paleta = ColoresActuales.current
    fun cerrar() {
        estado.detalle = null
    }
    Dialogo(::cerrar, ancho = 680.dp) {
        Texto(fila.texto("title"), tamano = 17, peso = 800)
        Texto(fila.texto("value"), tamano = 13, peso = 700, color = colorExtras(fila.texto("tone")))
        Texto(fila.texto("detail"), tamano = 13, color = paleta.apagado)
        ParteDetalle(t("DANGER ZONE"), fila.texto("risk"))
        ParteDetalle(t("Restore"), fila.texto("undo"))
        ParteDetalle(t("Unavailable"), fila.texto("blocked"))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp, Alignment.End)) {
            for (enlace in fila.objetos("links")) {
                Boton(enlace.texto("label"), { estado.aplicacion.abrirEnlace(enlace.texto("url")) })
            }
            Boton(t("Close"), ::cerrar)
        }
    }
}

@Composable
private fun ParteDetalle(titulo: String, texto: String) {
    if (texto.isEmpty()) {
        return
    }
    Texto(titulo, tamano = 12, peso = 750)
    Texto(texto, tamano = 13, color = ColoresActuales.current.apagado)
}

@Composable
private fun PasoOperacion(estado: EstadoExtras, paso: JsonObject) {
    val paleta = ColoresActuales.current
    fun cerrar() {
        estado.dialogo = null
    }
    Dialogo(::cerrar, ancho = 640.dp) {
        Texto(t(paso.texto("title", t("Additional settings"))), tamano = 17, peso = 800)
        when (paso.texto("kind")) {
            "loading" -> Texto(t("Loading"), tamano = 13, color = paleta.apagado)
            "choice" -> {
                for (opcion in paso.objetos("options")) {
                    val valor = opcion["value"]
                    Boton(opcion.texto("label"), { if (valor != null) estado.elegir(valor) }, Modifier.fillMaxWidth(), alto = 38.dp)
                }
            }
            "error" -> Texto(paso.texto("error"), tamano = 13, color = paleta.naranja)
            else -> Texto(paso.texto("detail"), tamano = 13, color = paleta.apagado)
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp, Alignment.End)) {
            Boton(t("Cancel"), ::cerrar)
            if (paso.texto("kind") == "confirm") {
                val clase = if (paso.logico("danger")) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL
                Boton(t("Continue"), estado::ejecutarConfirmado, clase = clase)
            }
        }
    }
}
