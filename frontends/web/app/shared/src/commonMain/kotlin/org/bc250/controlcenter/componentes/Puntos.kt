package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_down_gray
import org.bc250.controlcenter.recursos.chevron_right_gray
import org.bc250.controlcenter.recursos.chevron_up_gray
import org.bc250.controlcenter.tema.ColoresActuales

/** Los tres puntos con los que se arrastra el alto de una pieza. */
@Composable
fun TresPuntos(modifier: Modifier = Modifier) {
    val color = ColoresActuales.current.apagado
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        repeat(3) {
            Box(Modifier.size(4.dp).background(color, RoundedCornerShape(2.dp)))
        }
    }
}

/** La flecha de un grupo: abajo si está abierto, a la derecha si está plegado. */
@Composable
fun FlechaPlegar(abierto: Boolean, tamano: Dp = 11.dp) {
    val dibujo = if (abierto) Res.drawable.chevron_down_gray else Res.drawable.chevron_right_gray
    Icono(dibujo, tamano)
}

/** La flecha de una columna ordenada. */
@Composable
fun FlechaOrden(descendente: Boolean, tamano: Dp = 10.dp) {
    val dibujo = if (descendente) Res.drawable.chevron_down_gray else Res.drawable.chevron_up_gray
    Icono(dibujo, tamano)
}
