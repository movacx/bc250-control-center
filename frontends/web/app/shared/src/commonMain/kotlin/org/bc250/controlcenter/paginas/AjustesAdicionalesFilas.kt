package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_down_gray
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

@Composable
internal fun colorExtras(tono: String): Color {
    val paleta = ColoresActuales.current
    return when (tono) {
        "ok", "green" -> paleta.verde
        "warn", "orange" -> paleta.naranja
        "bad", "red" -> paleta.rojo
        "accent", "blue" -> paleta.acento
        else -> paleta.apagado
    }
}

@Composable
internal fun PanelExtras(estado: EstadoExtras, pestana: String, panel: JsonObject) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth().heightIn(min = 36.dp).padding(start = 6.dp, end = 2.dp, top = 14.dp, bottom = 2.dp)) {
            Texto(panel.texto("title"), tamano = 14, peso = 750, modifier = Modifier.weight(1f))
            Texto(panel.texto("value"), tamano = 12, color = paleta.sutil)
        }
        if (panel.texto("detail").isNotEmpty()) {
            Texto(panel.texto("detail"), tamano = 12, color = paleta.apagado)
        }
        val filas = panel.objetos("rows")
        val lecturas = panel.objetos("readings")
        if (filas.isNotEmpty() || lecturas.isNotEmpty()) {
            Column(Modifier.fillMaxWidth().marco(paleta.panelElevado, paleta.borde, Medidas.radioPanel).padding(horizontal = 1.dp, vertical = 3.dp)) {
                lecturas.forEach { lectura ->
                    Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 8.dp), Arrangement.spacedBy(12.dp)) {
                        Texto(lectura.texto("label"), tamano = 12, modifier = Modifier.weight(1f), color = paleta.apagado)
                        Texto(lectura.texto("value"), tamano = 12, color = colorExtras(lectura.texto("tone")))
                    }
                }
                filas.forEachIndexed { indice, fila ->
                    if (indice > 0) LineaDivisoria()
                    FilaExtras(estado, pestana, fila)
                }
            }
        }
    }
}

@Composable
internal fun FilaExtras(estado: EstadoExtras, pestana: String, fila: JsonObject) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val movil = maxWidth < 760.dp
        val descripcion: @Composable () -> Unit = {
            Column(Modifier.padding(vertical = 1.dp), Arrangement.spacedBy(3.dp)) {
                Texto(fila.texto("title"), tamano = 13, peso = 650)
                if (fila.texto("detail").isNotEmpty()) {
                    Texto(fila.texto("detail"), tamano = 12, color = paleta.apagado, lineas = if (movil) 5 else 1)
                }
                if (fila.texto("scope").isNotEmpty()) {
                    Texto(fila.texto("scope"), tamano = 11, color = paleta.sutil, lineas = 1)
                }
                if (fila.texto("blocked").isNotEmpty()) {
                    Texto(fila.texto("blocked"), tamano = 11, color = paleta.naranja)
                }
            }
        }
        if (movil) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 12.dp), Arrangement.spacedBy(10.dp)) {
                descripcion()
                Texto(fila.texto("value"), tamano = 12, peso = 600, color = colorExtras(fila.texto("tone")))
                AccionesFilaExtras(estado, pestana, fila)
            }
        } else {
            Row(Modifier.fillMaxWidth().heightIn(min = 62.dp).padding(horizontal = 18.dp, vertical = 12.dp),
                Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) { descripcion() }
                Texto(fila.texto("value"), tamano = 12, peso = 600, modifier = Modifier.width(130.dp), alineado = TextAlign.End, color = colorExtras(fila.texto("tone")))
                AccionesFilaExtras(estado, pestana, fila)
            }
        }
    }
}

@Composable
private fun AccionesFilaExtras(estado: EstadoExtras, pestana: String, fila: JsonObject) {
    val paleta = ColoresActuales.current
    val acciones = fila.objetos("actions")
    var menu by remember(fila.texto("id")) { mutableStateOf(false) }
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
        val principal = acciones.firstOrNull()
        Box(Modifier.width(190.dp)) {
            if (principal != null) {
                val puede = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado && principal.logico("enabled", true)
                Boton(principal.texto("label"), { estado.pulsar(pestana, fila, principal) }, Modifier.fillMaxWidth(),
                    clase = claseDeFila(fila, principal, puede),
                    activo = puede,
                    alto = 31.dp, tamano = 12, peso = 650)
            }
        }
        Box(Modifier.width(78.dp)) {
            Boton(t("More"), { menu = true }, Modifier.width(72.dp), clase = ClaseBoton.CONTORNO, alto = 32.dp, tamano = 12, peso = 650, icono = Res.drawable.chevron_down_gray, iconoDetras = true)
            if (menu) {
                Popup(onDismissRequest = { menu = false }, properties = PopupProperties(focusable = true)) {
                    Column(Modifier.width(340.dp).heightIn(max = 500.dp).marco(paleta.panel, paleta.borde, Medidas.radioPanel)
                        .verticalScroll(rememberScrollState()).padding(8.dp), Arrangement.spacedBy(5.dp)) {
                        Boton(t("Details"), { menu = false; estado.detalle = fila }, Modifier.fillMaxWidth())
                        acciones.drop(1).forEach { operacion ->
                            Boton(operacion.texto("label"), { menu = false; estado.pulsar(pestana, fila, operacion) }, Modifier.fillMaxWidth(),
                                activo = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado && operacion.logico("enabled", true))
                        }
                        fila.objetos("links").forEach { enlace ->
                            Boton(enlace.texto("label"), { menu = false; estado.aplicacion.abrirEnlace(enlace.texto("url")) }, Modifier.fillMaxWidth())
                        }
                    }
                }
            }
        }
    }
}

/** Verde cuando es el paso siguiente: nunca para lo que ya funciona ni para quitar algo. */
private fun claseDeFila(fila: JsonObject, principal: JsonObject, puede: Boolean): ClaseBoton {
    val yaFunciona = fila.texto("tone") == "ok"
    val esRetirar = principal.logico("removal")
    if (puede && !yaFunciona && !esRetirar) {
        return ClaseBoton.PRINCIPAL
    }
    return ClaseBoton.CONTORNO
}
