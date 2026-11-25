package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Opcion
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoAbierto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Los tres ajustes de memoria, en el orden en que los envía el servidor. */
private const val FILA_SWAP = 0
private const val FILA_TTM = 1
private const val FILA_VRAM = 2

/** Memoria y swap: la política de swap, el límite TTM y el tamaño de la VRAM. */
@Composable
internal fun MemoriaExtras(estado: EstadoExtras, datos: JsonObject, paneles: List<JsonObject>) {
    val lecturas = paneles.firstOrNull()?.objetos("readings") ?: emptyList()
    val filas = paneles.getOrNull(1)?.objetos("rows") ?: emptyList()
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp)) {
        TarjetaSwap(estado, filas.getOrNull(FILA_SWAP) ?: ObjetoVacio, datos, lecturas)
        TarjetaTtm(estado, filas.getOrNull(FILA_TTM) ?: ObjetoVacio)
        TarjetaVram(estado, filas.getOrNull(FILA_VRAM) ?: ObjetoVacio)
    }
}

@Composable
private fun TarjetaMemoria(contenido: @Composable () -> Unit) {
    val paleta = ColoresActuales.current
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .marco(paleta.panelAlterno, paleta.borde, Medidas.radioPanel)
            .padding(horizontal = 22.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        contenido()
    }
}

/** El título de la tarjeta y, a la derecha, sus botones. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EncabezadoMemoria(titulo: String, nota: String, botones: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val estrecha = maxWidth < 700.dp
        val texto: @Composable (Modifier) -> Unit = { modificador ->
            Column(modificador, Arrangement.spacedBy(3.dp)) {
                Texto(titulo, tamano = 16, peso = 750)
                if (nota.isNotEmpty()) {
                    Texto(nota, tamano = 13, color = ColoresActuales.current.apagado)
                }
            }
        }
        if (estrecha) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                texto(Modifier.fillMaxWidth())
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    botones()
                }
            }
        } else {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
                texto(Modifier.weight(1f))
                botones()
            }
        }
    }
}

// -- swap ------------------------------------------------------------------------------------------

@Composable
private fun TarjetaSwap(estado: EstadoExtras, fila: JsonObject, datos: JsonObject, lecturas: List<JsonObject>) {
    val actual = datos.texto("keep_policy", "preserve")
    var elegida by remember { mutableStateOf(actual) }
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado

    fun verEstado() {
        val lineas = lecturas.map { lectura -> lectura.texto("label") + ": " + lectura.texto("value") }
        estado.aplicacion.textoAbierto = TextoAbierto(t("View detailed status"), lineas.joinToString("\n"))
    }

    fun aplicar() {
        estado.abrirConRespuesta("memory", fila, kotlinx.serialization.json.JsonPrimitive(elegida))
    }

    TarjetaMemoria {
        EncabezadoMemoria(t("Swap and compression"), "") {
            Boton(t("View detailed status"), ::verEstado, alto = 36.dp)
            Boton(t("Apply Swap"), ::aplicar, clase = ClaseBoton.PRINCIPAL, activo = libre && elegida != actual, alto = 36.dp)
        }
        TablaSwap(datos.objetos("swap_policies"), elegida) { valor -> elegida = valor }
    }
}

@Composable
private fun TablaSwap(politicas: List<JsonObject>, elegida: String, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, Medidas.radioChico).padding(1.dp)) {
        Row(Modifier.fillMaxWidth().height(30.dp).padding(start = 45.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(t("Option").uppercase(), 11, Modifier.weight(470f), peso = 800, color = paleta.apagado)
            Texto(t("Description").uppercase(), 11, Modifier.weight(1003f), peso = 800, color = paleta.apagado)
        }
        for ((indice, politica) in politicas.withIndex()) {
            val valor = politica.texto("value")
            val fondo = when {
                valor == elegida -> paleta.acentoSuave
                indice % 2 == 1 -> paleta.panelAlterno
                else -> Color.Transparent
            }
            FilaSwap(politica, valor == elegida, fondo) { alElegir(valor) }
        }
    }
}

@Composable
private fun FilaSwap(politica: JsonObject, elegida: Boolean, fondo: Color, alElegir: () -> Unit) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth().background(fondo)) {
        LineaDivisoria()
        Row(
            modifier = Modifier.fillMaxWidth().heightIn(min = 40.dp).pulsable(alPulsar = alElegir).padding(start = 14.dp, end = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Opcion(elegida, color = paleta.acento)
            Texto(politica.texto("title"), 14, Modifier.weight(470f).padding(start = 15.dp), peso = 700)
            Texto(politica.texto("detail"), 13, Modifier.weight(1003f), color = paleta.apagado)
        }
    }
}

// -- TTM y VRAM --------------------------------------------------------------------------------------

@Composable
private fun TarjetaTtm(estado: EstadoExtras, fila: JsonObject) {
    val opciones = fila.objeto("form").objetos("options")
    val restaurar = opciones.firstOrNull { opcion -> opcion.texto("value") == "-1" }
    val tamanos = opciones.filter { opcion -> opcion !== restaurar }
    var elegido by remember { mutableStateOf<JsonElement?>(null) }
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado

    TarjetaMemoria {
        EncabezadoMemoria(t("Dynamic GPU Memory Limit (TTM)"), fila.texto("value")) {
            BotonMantener(t("Keep current TTM limit"), elegido == null) { elegido = null }
            val marcado = restaurar != null && elegido == restaurar["value"]
            BotonMantener(t("Restore previous TTM limit"), marcado, activo = restaurar != null) { elegido = restaurar?.get("value") }
            Boton(t("Apply TTM"), { aplicarValor(estado, fila, elegido) }, clase = ClaseBoton.PRINCIPAL,
                activo = libre && elegido != null, alto = 36.dp)
        }
        CarrilValores(tamanos, elegido, libre) { valor -> elegido = valor }
    }
}

@Composable
private fun TarjetaVram(estado: EstadoExtras, fila: JsonObject) {
    var elegido by remember { mutableStateOf<JsonElement?>(null) }
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado

    TarjetaMemoria {
        EncabezadoMemoria(t("VRAM size (UMA_SIZE)"), t("A reboot may be required.")) {
            BotonMantener(t("Keep current VRAM size"), elegido == null) { elegido = null }
            Boton(t("Apply VRAM"), { aplicarValor(estado, fila, elegido) }, clase = ClaseBoton.PRINCIPAL,
                activo = libre && elegido != null, alto = 36.dp)
        }
        CarrilValores(fila.objeto("form").objetos("options"), elegido, libre) { valor -> elegido = valor }
    }
}

private fun aplicarValor(estado: EstadoExtras, fila: JsonObject, valor: JsonElement?) {
    if (valor != null) {
        estado.abrirConRespuesta("memory", fila, valor)
    }
}

@Composable
private fun BotonMantener(texto: String, marcado: Boolean, activo: Boolean = true, alPulsar: () -> Unit) {
    val clase = if (marcado) ClaseBoton.ACENTO else ClaseBoton.NORMAL
    Boton(texto, alPulsar, clase = clase, activo = activo, alto = 32.dp, tamano = 13, peso = 650)
}

/** Un carril con un punto por valor; se elige tocando el punto o su nombre. */
@Composable
private fun CarrilValores(opciones: List<JsonObject>, elegido: JsonElement?, activo: Boolean, alElegir: (JsonElement) -> Unit) {
    val paleta = ColoresActuales.current
    if (opciones.isEmpty()) {
        return
    }
    BoxWithConstraints(Modifier.fillMaxWidth().height(78.dp)) {
        val borde = 34.dp
        val paso = if (opciones.size > 1) (maxWidth - borde * 2) / (opciones.size - 1) else 0.dp
        val posicionElegida = opciones.indexOfFirst { opcion -> opcion["value"] == elegido }
        Canvas(Modifier.fillMaxWidth().height(30.dp)) {
            val y = 22.dp.toPx()
            drawLine(paleta.bordeFuerte, Offset(borde.toPx(), y), Offset(size.width - borde.toPx(), y), 3f)
            for (indice in opciones.indices) {
                val x = borde.toPx() + paso.toPx() * indice
                drawLine(paleta.apagado, Offset(x, y - 14f), Offset(x, y), 2f)
            }
            if (posicionElegida >= 0) {
                drawCircle(paleta.acento, 7.dp.toPx(), Offset(borde.toPx() + paso.toPx() * posicionElegida, y))
            }
        }
        for ((indice, opcion) in opciones.withIndex()) {
            val alto = if (opciones.size > 4 && indice % 2 == 1) 54.dp else 38.dp
            val color = if (indice == posicionElegida) paleta.acento else paleta.apagado
            Box(
                modifier = Modifier
                    .offset(x = borde + paso * indice - 40.dp, y = 0.dp)
                    .width(80.dp)
                    .height(78.dp)
                    .pulsable(activo) { opcion["value"]?.let(alElegir) },
            ) {
                Texto(opcion.texto("label"), 12, Modifier.fillMaxWidth().padding(top = alto), color = color, alineado = TextAlign.Center)
            }
        }
    }
}
