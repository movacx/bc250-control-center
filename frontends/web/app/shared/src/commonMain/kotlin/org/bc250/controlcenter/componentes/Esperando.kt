package org.bc250.controlcenter.componentes

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.tema.ColoresActuales

private const val VUELTA = 360f
private const val ARCO = 100f
private const val DURACION = 1000

/** El anillo que gira mientras se espera algo. */
@Composable
fun Esperando(lado: Dp = 14.dp) {
    val color = ColoresActuales.current.color("cyan")
    val giro = rememberInfiniteTransition()
    val angulo by giro.animateFloat(
        initialValue = 0f,
        targetValue = VUELTA,
        animationSpec = infiniteRepeatable(tween(DURACION, easing = LinearEasing)),
    )
    Canvas(Modifier.size(lado)) {
        val grosor = maxOf(1.5f, lado.value / 8) * density
        val borde = grosor / 2 + density / 2
        val esquina = Offset(borde, borde)
        val medida = Size(size.width - 2 * borde, size.height - 2 * borde)
        drawArc(color.copy(alpha = 0.22f), 0f, VUELTA, false, esquina, medida, style = Stroke(grosor))
        drawArc(color, angulo, ARCO, false, esquina, medida, style = Stroke(grosor, cap = StrokeCap.Round))
    }
}
