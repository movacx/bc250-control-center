package org.bc250.controlcenter.paginas

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.*

/** Colores de las rutas, tomados siempre de la paleta activa. */
private class ColoresRuta(val fondo: Color, val borde: Color, val texto: Color)

@Composable
private fun coloresRuta(token: String): ColoresRuta {
    val paleta = ColoresActuales.current
    return when (token) {
        "D+" -> ColoresRuta(paleta.color("green_soft"), paleta.color("green_border"), paleta.verde)
        "S+" -> ColoresRuta(paleta.color("cyan_soft"), paleta.color("cyan_border"), paleta.color("cyan"))
        "D!" -> ColoresRuta(paleta.rojoSuave, paleta.rojoBorde, paleta.rojo)
        else -> ColoresRuta(paleta.panelAlterno, paleta.bordeSuave, paleta.textoInactivo)
    }
}

@Composable
internal fun LeyendaUnidades() {
    val leyenda = listOf("D+" to "Driver + routed", "S+" to "Live unlock", "D!" to "Driver blocked", "--" to "Not routed")
    SubPanel(margen = PaddingValues(14.dp, 9.dp), espacio = 0.dp, fondo = ColoresActuales.current.panelAlterno) {
        RejillaGpuCu(4, 4) { indice, modificador ->
            val (token, nombre) = leyenda[indice]
            val colores = coloresRuta(token)
            Row(modificador, Arrangement.spacedBy(7.dp), Alignment.CenterVertically) {
                Texto(token, tamano = 11, peso = 830, color = colores.texto,
                    modifier = Modifier.marco(colores.fondo, colores.borde, Medidas.radioChico).padding(8.dp, 4.dp))
                Texto(t(nombre), tamano = 11, peso = 700, color = ColoresActuales.current.apagado)
            }
        }
    }
}

@Composable
internal fun TablaUnidades(filas: List<JsonObject>, editable: Boolean, alAlternar: (Int, Int) -> Unit) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val anchoTabla = maxOf(maxWidth, MedidasGpuCu.anchoTablaMinimo)
        Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(anchoTabla).marco(paleta.panelAlterno, paleta.bordeSuave, Medidas.radioPanel).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
                    for (columna in 0..6) {
                        val titulo = when (columna) { 0 -> t("Shader row"); 6 -> "CUs"; else -> "WGP${columna - 1}" }
                        val detalle = when (columna) { 0 -> "SE / SH"; 6 -> t("active / 10"); else -> "CU ${(columna - 1) * 2}–${(columna - 1) * 2 + 1}" }
                        Column(Modifier.weight(if (columna == 0 || columna == 6) 2f else 3f)
                            .height(MedidasGpuCu.altoCabeceraWgp).marco(paleta.panelElevado, paleta.bordeSuave, Medidas.radioChico),
                            Arrangement.Center, Alignment.CenterHorizontally) {
                            Texto(titulo, tamano = 12, peso = 830)
                            Texto(detalle, tamano = 10, peso = 680, color = paleta.sutil)
                        }
                    }
                }
                for (indice in 0..3) {
                    val fila = filas.getOrNull(indice) ?: ObjetoVacio
                    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
                        CeldaUnidades(fila.texto("name", "SE${indice / 2}.SH${indice % 2}"), "", "", Modifier.weight(2f))
                        for (wgp in 0..4) {
                            val celda = fila.objetos("cells").getOrNull(wgp) ?: ObjetoVacio
                            val token = celda.texto("token", "--")
                            CeldaUnidades(token, t(celda.texto("label", "OFF")), token, Modifier.weight(3f), editable) {
                                alAlternar(indice, wgp)
                            }
                        }
                        CeldaUnidades(fila.texto("count", "0 / 10"), "", "count", Modifier.weight(2f))
                    }
                }
            }
        }
    }
}

@Composable
private fun CeldaUnidades(titulo: String, detalle: String, token: String, modifier: Modifier,
    editable: Boolean = false, alPulsar: () -> Unit = {}) {
    val paleta = ColoresActuales.current
    val colores = if (token == "count") ColoresRuta(paleta.acentoSuave, paleta.acentoBorde, paleta.acento)
        else if (token.isEmpty()) ColoresRuta(paleta.panelAlterno, paleta.bordeSuave, paleta.texto) else coloresRuta(token)
    Column(modifier.height(MedidasGpuCu.altoFilaWgp).marco(colores.fondo, colores.borde, Medidas.radioBoton)
        .pulsable(editable, alPulsar = alPulsar), Arrangement.Center, Alignment.CenterHorizontally) {
        Texto(titulo, tamano = 13, peso = 830, color = colores.texto, alineado = TextAlign.Center)
        if (detalle.isNotEmpty()) Texto(detalle, tamano = 12, peso = 830, color = colores.texto, alineado = TextAlign.Center)
    }
}

@Composable
internal fun RegistrosUnidades(filas: List<JsonObject>) {
    SubPanel {
        TituloGpuCu(t("Register diagnostics"))
        Texto(t("Read-only register values and the pending SPI target."), tamano = 12)
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            val columnas = listOf("Shader row", "Live SPI", "Target SPI", "Driver map", "CC harvest")
            Row(Modifier.width(720.dp)) {
                for (titulo in columnas) Texto(t(titulo), tamano = 12, peso = 700, modifier = Modifier.weight(1f))
            }
            for (fila in filas) {
                Row(Modifier.width(720.dp).padding(vertical = 8.dp)) {
                    for (clave in listOf("name", "live", "target", "driver", "cc")) {
                        TextoConsola(fila.texto(clave), modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}
