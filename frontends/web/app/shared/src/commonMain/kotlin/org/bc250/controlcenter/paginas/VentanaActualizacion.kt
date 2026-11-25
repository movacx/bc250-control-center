package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales

/** La versión publicada, sus notas y el botón que la instala. */
@Composable
fun VentanaActualizacion(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    var datos by remember { mutableStateOf(ObjetoVacio) }
    LaunchedEffect(Unit) {
        datos = aplicacion.consultar("settings.update")
    }
    fun cerrar() {
        aplicacion.actualizacionAbierta = false
    }
    fun instalar() {
        cerrar()
        aplicacion.preguntarYEjecutar("settings.update", t("Update application"), datos.texto("version"))
    }
    Dialogo(::cerrar, ancho = 760.dp) {
        Texto(t("Update application"), tamano = 18, peso = 800)
        val error = datos.texto("error")
        when {
            datos.isEmpty() -> Texto(t("Reading the latest release…"), tamano = 13, color = paleta.apagado)
            error.isNotEmpty() -> Texto(error, tamano = 13, color = paleta.naranja)
            else -> {
                Texto(datos.texto("installed") + "  →  " + datos.texto("version"), tamano = 15, peso = 750)
                TextoConsola(datos.texto("notes"), Modifier.fillMaxWidth().heightIn(max = 420.dp))
                if (datos.texto("reason").isNotEmpty()) {
                    Texto(datos.texto("reason"), tamano = 12, color = paleta.naranja)
                }
            }
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp, Alignment.End)) {
            if (datos.texto("page").isNotEmpty()) {
                Boton(t("See what's new"), { aplicacion.abrirEnlace(datos.texto("page")) })
            }
            Boton(t("Close"), ::cerrar)
            val puede = datos.logico("newer") && datos.texto("kind") != "manual" && aplicacion.puedeControlar
            Boton(t("Update application"), ::instalar, clase = ClaseBoton.PRINCIPAL, activo = puede)
        }
    }
}
