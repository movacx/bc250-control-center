package org.bc250.controlcenter.movil

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.tema.ColoresActuales

private const val MILISEGUNDOS = 220

/** Lo que oscurece la página detrás de un menú o una ventana. */
@Composable
fun Velo(visible: Boolean, alTocar: () -> Unit) {
    AnimatedVisibility(visible, enter = fadeIn(tween(MILISEGUNDOS)), exit = fadeOut(tween(MILISEGUNDOS))) {
        Box(
            Modifier.fillMaxSize()
                .background(ColoresActuales.current.color("scrim").copy(alpha = 0.6f))
                .pulsable(alPulsar = alTocar),
        )
    }
}

/** Entra y sale deslizándose, desde abajo o desde la izquierda. */
@Composable
fun Deslizante(visible: Boolean, desdeAbajo: Boolean, contenido: @Composable () -> Unit) {
    val entrada = if (desdeAbajo) slideInVertically(tween(MILISEGUNDOS)) { alto -> alto } else slideInHorizontally(tween(MILISEGUNDOS)) { ancho -> -ancho }
    val salida = if (desdeAbajo) slideOutVertically(tween(MILISEGUNDOS)) { alto -> alto } else slideOutHorizontally(tween(MILISEGUNDOS)) { ancho -> -ancho }
    AnimatedVisibility(visible, enter = entrada, exit = salida) {
        contenido()
    }
}

/** El círculo que gira mientras algo está en marcha. */
@Composable
fun Giro() {
    val paleta = ColoresActuales.current
    val vuelta by rememberInfiniteTransition().animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(1000, easing = LinearEasing)),
    )
    Canvas(Modifier.size(16.dp)) {
        val trazo = Stroke(2.dp.toPx())
        val margen = trazo.width / 2
        val medida = Size(size.width - trazo.width, size.height - trazo.width)
        drawArc(paleta.acentoBorde, 0f, 360f, false, Offset(margen, margen), medida, style = trazo)
        drawArc(paleta.acento, vuelta - 90f, 90f, false, Offset(margen, margen), medida, style = trazo)
    }
}
