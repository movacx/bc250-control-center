package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** El recorrido guiado: cada parada abre su página y dice para qué sirve. */
@Composable
fun VentanaRecorrido(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    var paradas by remember { mutableStateOf<List<JsonObject>>(emptyList()) }
    var numero by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        paradas = aplicacion.consultar("settings.tour").objetos("stops")
    }
    val parada = paradas.getOrNull(numero)
    LaunchedEffect(parada) {
        if (parada != null) {
            aplicacion.irA(parada.texto("page"))
        }
    }
    fun salir() {
        aplicacion.recorridoAbierto = false
    }
    fun seguir() {
        if (numero + 1 < paradas.size) {
            numero += 1
        } else {
            salir()
        }
    }
    if (parada == null) {
        return
    }
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.BottomEnd) {
        Column(
            modifier = Modifier
                .widthIn(max = 420.dp)
                .marco(paleta.panelElevado, paleta.acentoBorde, Medidas.radioTarjeta)
                .pulsable { }
                .padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Texto("${numero + 1} / ${paradas.size}", tamano = 11, color = paleta.apagado)
            Texto(parada.texto("titulo"), tamano = 15, peso = 780)
            Texto(parada.texto("cuerpo"), tamano = 13, color = paleta.apagado)
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp, Alignment.End)) {
                Boton(t("End tour"), ::salir)
                Boton(t("Next"), ::seguir, clase = ClaseBoton.PRINCIPAL)
            }
        }
    }
}
