package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Una página que se desplaza, con el margen del escritorio y su barra fina a la derecha. */
@Composable
fun PaginaDesplazable(
    margen: PaddingValues = PaddingValues(start = 16.dp, top = 12.dp, end = 24.dp, bottom = 20.dp),
    espacio: Dp = Medidas.espacio,
    contenido: @Composable ColumnScope.() -> Unit,
) {
    val paleta = ColoresActuales.current
    val desplazador = rememberScrollState()
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val alto = maxHeight
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(desplazador)
                .padding(margen),
            verticalArrangement = Arrangement.spacedBy(espacio),
            content = contenido,
        )
        if (desplazador.maxValue > 0) {
            val total = alto.value + desplazador.maxValue
            val altoBarra = (alto.value * alto.value / total).coerceAtLeast(44f)
            val recorrido = alto.value - altoBarra - 8f
            val posicion = 4f + recorrido * desplazador.value / desplazador.maxValue
            Box(
                Modifier
                    .align(Alignment.TopEnd)
                    .offset(x = (-1).dp, y = posicion.dp)
                    .width(6.dp)
                    .height(altoBarra.dp)
                    .background(paleta.color("scrollbar"), RoundedCornerShape(2.dp)),
            )
        }
    }
}

/** Una página que todavía no se ha escrito. */
@Composable
fun PaginaPendiente(nombre: String) {
    Box(Modifier.fillMaxWidth().fillMaxHeight(), contentAlignment = Alignment.Center) {
        Texto(nombre, tamano = 17, peso = 800, color = ColoresActuales.current.apagado)
    }
}
