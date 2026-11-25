package org.bc250.controlcenter.movil

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.drag
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.input.pointer.PointerInputScope
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.unit.dp
import kotlin.math.hypot

/** Qué tan cerca hay que tocar un punto para moverlo. */
private val AlcanceDelDedo = 26.dp

/**
 * Elegir un punto tocándolo y moverlo arrastrando. Un toque lejos de todos no estorba al desplazamiento
 * de la página.
 */
suspend fun PointerInputScope.moverPuntos(
    lugares: () -> List<Offset>,
    alElegir: (Int) -> Unit,
    alMover: (Int, Offset) -> Unit,
) {
    awaitEachGesture {
        val inicio = awaitFirstDown()
        val puntos = lugares()
        val cercano = puntos.indices.minByOrNull { indice -> distancia(puntos[indice], inicio.position) }
        if (cercano != null && distancia(puntos[cercano], inicio.position) <= AlcanceDelDedo.toPx()) {
            inicio.consume()
            alElegir(cercano)
            drag(inicio.id) { cambio ->
                cambio.consume()
                alMover(cercano, cambio.position)
            }
        }
    }
}

private fun distancia(uno: Offset, otro: Offset): Float {
    return hypot(uno.x - otro.x, uno.y - otro.y)
}

/** Una línea quebrada que pasa por todos los puntos. */
fun DrawScope.dibujarLinea(puntos: List<Offset>, color: Color, punteada: Boolean = false) {
    val trazo = if (punteada) PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())) else null
    for (indice in 1 until puntos.size) {
        drawLine(color, puntos[indice - 1], puntos[indice], 2.dp.toPx(), pathEffect = trazo)
    }
}

/** Un punto cuadrado; el elegido es más grande. */
fun DrawScope.dibujarPunto(lugar: Offset, elegido: Boolean, color: Color) {
    val medio = if (elegido) 6.dp.toPx() else 4.5.dp.toPx()
    drawRoundRect(color, Offset(lugar.x - medio, lugar.y - medio), Size(medio * 2, medio * 2), CornerRadius(2.dp.toPx()))
}

/** Dónde queda un texto respecto a su punto. */
enum class Lado { ANTES, CENTRO, DESPUES }

/** Un texto pequeño de los ejes, centrado en vertical sobre ``lugar``. */
fun DrawScope.dibujarTexto(medidor: TextMeasurer, texto: String, estilo: TextStyle, lugar: Offset, lado: Lado) {
    val medido = medidor.measure(texto, estilo)
    val ancho = medido.size.width
    val x = when (lado) {
        Lado.ANTES -> lugar.x - ancho
        Lado.CENTRO -> lugar.x - ancho / 2f
        Lado.DESPUES -> lugar.x
    }
    drawText(medido, topLeft = Offset(x.coerceAtLeast(0f), lugar.y - medido.size.height / 2f))
}
