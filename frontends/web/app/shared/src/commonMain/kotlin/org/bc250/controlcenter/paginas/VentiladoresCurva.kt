package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

internal fun puntosDe(datos: JsonArray): List<Pair<Int, Int>> {
    return datos.mapNotNull { elemento ->
        val punto = elemento as? JsonArray
        val temperatura = (punto?.getOrNull(0) as? JsonPrimitive)?.content?.toIntOrNull()
        val velocidad = (punto?.getOrNull(1) as? JsonPrimitive)?.content?.toIntOrNull()
        if (temperatura == null || velocidad == null) null else temperatura to velocidad
    }
}

internal fun datosDe(puntos: List<Pair<Int, Int>>): JsonArray {
    return JsonArray(puntos.sortedBy { it.first }.map { (temperatura, velocidad) ->
        JsonArray(listOf(JsonPrimitive(temperatura), JsonPrimitive(velocidad)))
    })
}

@Composable
internal fun PuntosVentilador(datos: JsonArray, disponible: Boolean, temperatura: Double?, salida: Double?, alCambiar: (JsonArray) -> Unit) {
    val puntos = puntosDe(datos)
    val actuales by rememberUpdatedState(puntos)
    val cambiar by rememberUpdatedState(alCambiar)
    val paleta = ColoresActuales.current
    Canvas(Modifier.fillMaxWidth().height(240.dp).pointerInput(disponible) {
        var elegido = -1
        detectDragGestures(onDragStart = { posicion ->
            elegido = actuales.indices.minByOrNull { indice ->
                val punto = actuales[indice]
                val x = punto.first / 120f * size.width
                val y = (1f - punto.second / 100f) * size.height
                (x - posicion.x) * (x - posicion.x) + (y - posicion.y) * (y - posicion.y)
            } ?: -1
        }, onDragEnd = { elegido = -1 }, onDragCancel = { elegido = -1 }) { cambio, _ ->
            if (disponible && elegido in actuales.indices) {
                cambio.consume()
                val nuevos = actuales.toMutableList()
                val minimo = if (elegido == 0) 0 else actuales[elegido - 1].first + 1
                val maximo = if (elegido == actuales.lastIndex) 120 else actuales[elegido + 1].first - 1
                if (minimo <= maximo) {
                    val grados = (cambio.position.x / size.width * 120).roundToInt().coerceIn(minimo, maximo)
                    val porcentaje = ((1f - cambio.position.y / size.height) * 100).roundToInt().coerceIn(0, 100)
                    nuevos[elegido] = grados to porcentaje
                    cambiar(datosDe(nuevos))
                }
            }
        }
    }) {
        for (linea in 0..4) {
            val y = linea / 4f * size.height
            drawLine(paleta.bordeSuave, Offset(0f, y), Offset(size.width, y))
        }
        for (linea in 0..6) {
            val x = linea / 6f * size.width
            drawLine(paleta.bordeSuave, Offset(x, 0f), Offset(x, size.height))
        }
        fun posicion(punto: Pair<Int, Int>): Offset = Offset(punto.first / 120f * size.width, (1f - punto.second / 100f) * size.height)
        for (indice in 1 until puntos.size) drawLine(paleta.acento, posicion(puntos[indice - 1]), posicion(puntos[indice]), 2.dp.toPx())
        for (punto in puntos) drawCircle(paleta.acento, 5.dp.toPx(), posicion(punto))
        if (temperatura != null) {
            val x = (temperatura / 120).toFloat().coerceIn(0f, 1f) * size.width
            drawLine(paleta.naranja, Offset(x, 0f), Offset(x, size.height), 1.dp.toPx())
            if (salida != null) drawCircle(paleta.verde, 4.dp.toPx(), Offset(x, (1f - salida.toFloat() / 100f) * size.height))
        }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Texto("0 °C", 10, color = paleta.apagado)
        Texto("60 °C · 0–100 %", 10, color = paleta.apagado)
        Texto("120 °C", 10, color = paleta.apagado)
    }
    Texto(t("Drag a point to move it."), 11, color = paleta.apagado)
    if (temperatura != null) Texto(t("Now") + " $temperatura °C · " + t("Real output") + " ${salida ?: "—"} %", 11)
    for ((indice, punto) in puntos.withIndex()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CampoNumero(punto.first, { valor ->
                val nuevos = puntos.toMutableList()
                nuevos[indice] = valor to punto.second
                alCambiar(datosDe(nuevos))
            }, if (indice == 0) 0 else puntos[indice - 1].first + 1,
                if (indice == puntos.lastIndex) 120 else puntos[indice + 1].first - 1,
                Modifier.weight(1f), sufijo = "°C", activo = disponible)
            CampoNumero(punto.second, { valor ->
                val nuevos = puntos.toMutableList()
                nuevos[indice] = punto.first to valor
                alCambiar(datosDe(nuevos))
            }, 0, 100, Modifier.weight(1f), sufijo = "%", activo = disponible)
            AccionSupervision("×", disponible && puntos.size > 2) {
                alCambiar(datosDe(puntos.filterIndexed { i, _ -> i != indice }))
            }
        }
    }
    AccionSupervision(t("Add point"), disponible && puntos.size < 8) {
        val hueco = (0..120).firstOrNull { candidato -> puntos.none { it.first == candidato } }
        if (hueco != null) alCambiar(datosDe(puntos + (hueco to 50)))
    }
}

@Composable
internal fun VelocidadVentilador(valor: Int, disponible: Boolean, alCambiar: (Int) -> Unit) {
    val actual by rememberUpdatedState(valor)
    val cambiar by rememberUpdatedState(alCambiar)
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Texto(t("Speed"), 12, Modifier.width(92.dp), color = paleta.apagado)
        Canvas(Modifier.weight(1f).height(27.dp).pointerInput(disponible) {
            detectDragGestures(onDragStart = { posicion ->
                if (disponible) cambiar((posicion.x / size.width * 100).roundToInt().coerceIn(0, 100))
            }) { cambio, _ ->
                if (disponible) {
                    cambio.consume()
                    cambiar((cambio.position.x / size.width * 100).roundToInt().coerceIn(0, 100))
                }
            }
        }.pointerInput(disponible) {
            detectTapGestures { posicion ->
                if (disponible) cambiar((posicion.x / size.width * 100).roundToInt().coerceIn(0, 100))
            }
        }) {
            val centro = size.height / 2
            val final = size.width * actual / 100f
            drawLine(paleta.pista, Offset(0f, centro), Offset(size.width, centro), 3.dp.toPx())
            drawLine(paleta.acento, Offset(0f, centro), Offset(final, centro), 3.dp.toPx())
            drawCircle(if (disponible) paleta.acento else paleta.textoInactivo, 6.dp.toPx(), Offset(final, centro))
        }
        CampoNumero(valor, alCambiar, 0, 100, Modifier.width(96.dp).height(27.dp), sufijo = "%", activo = disponible)
    }
}
