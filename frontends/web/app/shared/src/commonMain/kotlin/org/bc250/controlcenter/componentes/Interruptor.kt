package org.bc250.controlcenter.componentes

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.tema.ColoresActuales

/** El interruptor del escritorio: 44 por 26, con la bola que se desliza. */
@Composable
fun Interruptor(encendido: Boolean, alCambiar: (Boolean) -> Unit, modifier: Modifier = Modifier, activo: Boolean = true) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(12.dp)
    val fondo = if (encendido) paleta.acento else paleta.color("control_pressed")
    val borde = if (encendido) paleta.acento else paleta.bordeFuerte
    val lugar by animateDpAsState(if (encendido) 20.dp else 3.dp)
    Box(
        modifier = modifier.size(44.dp, 26.dp).pulsable(activo) { alCambiar(!encendido) },
        contentAlignment = Alignment.Center,
    ) {
        Box(Modifier.size(40.dp, 22.dp).background(fondo, forma).border(1.dp, borde, forma), Alignment.CenterStart) {
            val bola = if (encendido) paleta.sobreAcento else paleta.apagado
            Box(Modifier.offset(x = lugar).size(16.dp).background(bola, CircleShape))
        }
    }
}
