package org.bc250.controlcenter.tema

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Las medidas del escritorio, en un solo lugar. */
object Medidas {
    /** La densidad compacta encoge márgenes y separaciones, nunca la letra. */
    var compacta by mutableStateOf(false)

    private fun segunDensidad(comoda: Int, justa: Int): Dp {
        return if (compacta) justa.dp else comoda.dp
    }

    /** El margen entre la ventana y sus dos partes: la barra lateral y la página. */
    val margenVentana = 16.dp
    val margenPagina = 16.dp

    val anchoBarra = 212.dp
    val anchoBarraPlegada = 66.dp
    val altoBotonBarra: Dp get() = segunDensidad(40, 34)

    val espacio: Dp get() = segunDensidad(12, 8)
    val espacioCorto: Dp get() = segunDensidad(8, 6)
    val espacioPanel: Dp get() = segunDensidad(9, 6)

    val radioTarjeta = 10.dp
    val radioBarra = 8.dp
    val radioPanel = 6.dp
    val radioBoton = 5.dp
    val radioChico = 4.dp

    val anchoDesplazador = 8.dp
}
