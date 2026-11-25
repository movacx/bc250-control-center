package org.bc250.controlcenter.componentes

import androidx.compose.foundation.Canvas
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

private class SeriePanel(val nombre: String, val valores: List<Double?>)

private fun seriesPanel(datos: JsonObject): List<SeriePanel> {
    return datos.objetos("series").map { serie ->
        val valores = serie.lista("values").map { valor ->
            (valor as? JsonPrimitive)?.doubleOrNull
        }
        SeriePanel(serie.texto("name"), valores)
    }
}

/** Ejes y trazas con tiempos reales: los huecos de muestreo no se comprimen. */
@Composable
fun GraficaPanelRendimiento(
    datos: JsonObject,
    ventana: Int = 120,
    alto: Dp = M.altoGrafica,
    modifier: Modifier = Modifier,
) {
    val paleta = ColoresActuales.current
    val colores = listOf(paleta.acento, paleta.color("green"), paleta.color("orange"),
        paleta.color("purple"), paleta.color("cyan"), paleta.rojo, paleta.color("blue_hover"), paleta.apagado)
    val series = seriesPanel(datos)
    val edades = datos.lista("ages").map { valor -> (valor as? JsonPrimitive)?.doubleOrNull ?: 0.0 }
    val minimo = datos.numero("min") ?: 0.0
    val maximo = (datos.numero("max") ?: 100.0).coerceAtLeast(minimo + 0.001)
    val ticks = datos.objetos("ticks")
    var seleccion by remember { mutableStateOf<Int?>(null) }
    val rejilla = paleta.bordeSuave
    val mapa = datos.logico("heatmap")
    Column(modifier) {
        if (series.isEmpty() || edades.isEmpty()) {
            Box(Modifier.fillMaxWidth().height(alto), contentAlignment = Alignment.Center) {
                Leyenda(t("Waiting for first sample"))
            }
        } else {
            Row(Modifier.fillMaxWidth().height(alto)) {
                Box(Modifier.width(M.anchoEje).fillMaxHeight()) {
                    if (mapa) {
                        for ((indice, serie) in series.withIndex()) {
                            Texto(serie.nombre, tamano = 10, color = paleta.apagado,
                                modifier = Modifier.offset(y = alto * (indice.toFloat() / series.size)))
                        }
                    } else {
                        for (tick in ticks) {
                            val valor = tick.numero("value") ?: 0.0
                            val fraccion = ((maximo - valor) / (maximo - minimo)).coerceIn(0.0, 1.0)
                            Texto(tick.texto("label"), tamano = 10, color = paleta.apagado,
                                modifier = Modifier.offset(y = (alto - 16.dp) * fraccion.toFloat()))
                        }
                    }
                }
                Canvas(Modifier.weight(1f).fillMaxHeight().pointerInput(edades, ventana) {
                    awaitPointerEventScope {
                        while (true) {
                            val evento = awaitPointerEvent()
                            if (evento.type == PointerEventType.Exit) {
                                seleccion = null
                            } else if (evento.type == PointerEventType.Move || evento.type == PointerEventType.Press) {
                                val punto = evento.changes.firstOrNull()?.position
                                if (punto != null) {
                                    val edad = ventana * (1.0 - punto.x / size.width)
                                    seleccion = edades.indices.minByOrNull { indice -> kotlin.math.abs(edades[indice] - edad) }
                                }
                            }
                        }
                    }
                }) {
                    fun x(edad: Double): Float = size.width * (1f - (edad / ventana).toFloat())
                    fun y(valor: Double): Float = size.height * (1f - ((valor - minimo) / (maximo - minimo)).toFloat())
                    for (tick in ticks) {
                        val eje = y(tick.numero("value") ?: 0.0).coerceIn(0f, size.height)
                        drawLine(rejilla, Offset(0f, eje), Offset(size.width, eje), 1.dp.toPx())
                    }
                    for (paso in 0..4) {
                        val eje = size.width * paso / 4
                        drawLine(rejilla, Offset(eje, 0f), Offset(eje, size.height), 1.dp.toPx())
                    }
                    for ((numero, serie) in series.withIndex()) {
                        val color = colores[numero % colores.size]
                        val camino = Path()
                        var anterior: Double? = null
                        for ((indice, valor) in serie.valores.withIndex()) {
                            val edad = edades.getOrNull(indice) ?: continue
                            if (valor == null || !valor.isFinite() || edad > ventana) {
                                anterior = null
                                continue
                            }
                            val px = x(edad)
                            val py = y(valor).coerceIn(0f, size.height)
                            if (mapa) {
                                val altoFila = size.height / series.size
                                val intensidad = ((valor - minimo) / (maximo - minimo)).coerceIn(0.08, 1.0).toFloat()
                                val siguiente = edades.getOrNull(indice + 1) ?: (edad - 1.0)
                                drawRect(color.copy(alpha = intensidad), Offset(px, numero * altoFila),
                                    Size((x(siguiente) - px).coerceAtLeast(1f), (altoFila - 2f).coerceAtLeast(1f)))
                            } else {
                                if (anterior == null || anterior - edad > 4.0) camino.moveTo(px, py)
                                else camino.lineTo(px, py)
                            }
                            anterior = edad
                        }
                        if (!mapa) drawPath(camino, color, style = Stroke(width = 1.6.dp.toPx()))
                    }
                    seleccion?.takeIf { it in edades.indices }?.let { indice ->
                        val px = x(edades[indice]).coerceIn(0f, size.width)
                        drawLine(paleta.texto, Offset(px, 0f), Offset(px, size.height), 1.dp.toPx())
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(start = M.anchoEje).height(M.espacioEje), Arrangement.SpaceBetween) {
                Texto("−${ventana / 60} min", tamano = 10, color = paleta.apagado)
                Texto("−${ventana / 2} s", tamano = 10, color = paleta.apagado)
                Texto(t("Now"), tamano = 10, color = paleta.apagado)
            }
            if (seleccion != null && seleccion!! in edades.indices) {
                val indice = seleccion!!
                Leyenda("−${edades[indice].toInt()} s")
                for (serie in series) {
                    val valor = serie.valores.getOrNull(indice)
                    Leyenda("${serie.nombre}: ${valor ?: "--"} ${datos.texto("unit")}")
                }
            }
        }
    }
}
