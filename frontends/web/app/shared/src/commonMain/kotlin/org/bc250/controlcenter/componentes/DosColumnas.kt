package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.PointerIcon
import androidx.compose.ui.input.pointer.pointerHoverIcon
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.tema.ColoresActuales

private const val PARTE_MENOR = 0.3f
private const val PARTE_MAYOR = 0.75f

/** Dos columnas con un agarre en medio: arrastrarlo reparte el ancho, como en el escritorio. */
@Composable
fun DosColumnas(
    parteInicial: Float,
    alto: Dp,
    separacion: Dp = 12.dp,
    conPuntos: Boolean = true,
    izquierda: @Composable (Modifier) -> Unit,
    derecha: @Composable (Modifier) -> Unit,
) {
    var parte by remember { mutableStateOf(parteInicial) }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val total = constraints.maxWidth.toFloat().coerceAtLeast(1f)
        Row(Modifier.fillMaxWidth()) {
            izquierda(Modifier.weight(parte).heightIn(min = alto))
            Box(
                modifier = Modifier
                    .width(separacion)
                    .height(alto)
                    .pointerHoverIcon(PointerIcon.Hand)
                    .pointerInput(total) {
                        detectHorizontalDragGestures { _, movimiento ->
                            parte = (parte + movimiento / total).coerceIn(PARTE_MENOR, PARTE_MAYOR)
                        }
                    },
                contentAlignment = Alignment.Center,
            ) {
                if (conPuntos) {
                    PuntosDeAgarre()
                }
            }
            derecha(Modifier.weight(1f - parte).heightIn(min = alto))
        }
    }
}

@Composable
private fun PuntosDeAgarre() {
    val color = ColoresActuales.current.apagado
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        repeat(3) {
            Box(Modifier.size(4.dp).background(color, CircleShape))
        }
    }
}
