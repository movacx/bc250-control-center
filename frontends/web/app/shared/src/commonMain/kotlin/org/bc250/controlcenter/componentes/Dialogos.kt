package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.Confirmacion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.movil.BotonMovil
import org.bc250.controlcenter.movil.CajaDeHoja
import org.bc250.controlcenter.movil.HojaPrestada
import org.bc250.controlcenter.movil.LocalMovil
import org.bc250.controlcenter.movil.LocalTelefono
import org.bc250.controlcenter.movil.ParejaBotones
import org.bc250.controlcenter.movil.Velo
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Una ventana encima de la página, que se oscurece detrás. */
@Composable
fun Dialogo(alCerrar: () -> Unit, ancho: Dp = 480.dp, contenido: @Composable ColumnScope.() -> Unit) {
    val paleta = ColoresActuales.current
    val movil = LocalMovil.current
    if (movil != null) {
        HojaPrestada(movil, alCerrar, contenido)
        return
    }
    if (LocalTelefono.current) {
        Velo(visible = true, alTocar = alCerrar)
        CajaDeHoja(contenido = contenido)
        return
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(paleta.color("scrim").copy(alpha = 0.55f))
            .pulsable(alPulsar = alCerrar),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .padding(16.dp)
                .widthIn(max = ancho)
                .fillMaxWidth()
                .heightIn(max = 820.dp)
                .marco(paleta.panel, paleta.borde, Medidas.radioTarjeta)
                .pulsable { }
                .verticalScroll(rememberScrollState())
                .padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
            content = contenido,
        )
    }
}

/** La pregunta antes de una operación. */
@Composable
fun DialogoConfirmacion(confirmacion: Confirmacion, aplicacion: Aplicacion) {
    fun cerrar() {
        aplicacion.confirmacion = null
    }
    Dialogo(alCerrar = ::cerrar) {
        Texto(confirmacion.titulo, tamano = 17, peso = 800)
        Texto(confirmacion.mensaje, tamano = 13, color = ColoresActuales.current.apagado)
        if (LocalTelefono.current) {
            ParejaBotones {
                BotonMovil(t("Cancel"), Modifier.weight(1f), alPulsar = ::cerrar)
                val clase = if (confirmacion.peligro) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL
                BotonMovil(t("Continue"), Modifier.weight(1f), clase) {
                    cerrar()
                    confirmacion.aceptar()
                }
            }
            return@Dialogo
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End),
        ) {
            Boton(t("Cancel"), alPulsar = ::cerrar)
            Boton(
                texto = t("Continue"),
                clase = if (confirmacion.peligro) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL,
                alPulsar = {
                    cerrar()
                    confirmacion.aceptar()
                },
            )
        }
    }
}
