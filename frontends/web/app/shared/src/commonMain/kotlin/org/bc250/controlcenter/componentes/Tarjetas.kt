package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Un rectángulo con fondo, línea fina y esquinas redondeadas. */
@Composable
fun Modifier.marco(fondo: Color, borde: Color, radio: Dp): Modifier {
    val forma = RoundedCornerShape(radio)
    return this.background(fondo, forma).border(1.dp, borde, forma)
}

/** La tarjeta grande de una página. */
@Composable
fun TarjetaPagina(
    modifier: Modifier = Modifier,
    margen: PaddingValues = PaddingValues(horizontal = 20.dp, vertical = 18.dp),
    espacio: Dp = Medidas.espacio,
    contenido: @Composable ColumnScope.() -> Unit,
) {
    val paleta = ColoresActuales.current
    Column(
        modifier = modifier.marco(paleta.panel, paleta.borde, Medidas.radioTarjeta).padding(1.dp).padding(margen),
        verticalArrangement = Arrangement.spacedBy(espacio),
        content = contenido,
    )
}

/** El panel que va dentro de una tarjeta. */
@Composable
fun SubPanel(
    modifier: Modifier = Modifier,
    fondo: Color = ColoresActuales.current.grupo,
    borde: Color = ColoresActuales.current.borde,
    margen: PaddingValues = PaddingValues(start = 14.dp, top = 12.dp, end = 14.dp, bottom = 13.dp),
    espacio: Dp = Medidas.espacioPanel,
    contenido: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier.fillMaxWidth().marco(fondo, borde, Medidas.radioPanel).padding(1.dp).padding(margen),
        verticalArrangement = Arrangement.spacedBy(espacio),
        content = contenido,
    )
}

/** Una línea fina de lado a lado. */
@Composable
fun LineaDivisoria(modifier: Modifier = Modifier, color: Color = ColoresActuales.current.bordeSuave) {
    Box(modifier.fillMaxWidth().height(1.dp).background(color))
}

/** Una lectura pequeña: su nombre y su valor. */
@Composable
fun TarjetaLectura(nombre: String, valor: String, modifier: Modifier = Modifier) {
    val paleta = ColoresActuales.current
    Column(
        modifier = modifier
            .marco(paleta.panelAlterno, paleta.bordeSuave, 7.dp)
            .padding(horizontal = 13.dp, vertical = 11.dp),
        verticalArrangement = Arrangement.spacedBy(1.dp, androidx.compose.ui.Alignment.CenterVertically),
    ) {
        Texto(nombre, tamano = 11, peso = 760, color = paleta.apagado, modifier = Modifier.padding(vertical = 3.5.dp))
        Texto(valor, tamano = 15, peso = 830)
    }
}

/** Una barra de uso, de 0 a 100. */
@Composable
fun BarraUso(porcentaje: Double?, modifier: Modifier = Modifier, alto: Dp = 4.dp) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(alto / 2)
    Box(modifier.height(alto).background(paleta.pista, forma)) {
        if (porcentaje != null && porcentaje > 0) {
            val parte = (porcentaje / 100.0).coerceIn(0.0, 1.0).toFloat()
            Box(Modifier.fillMaxWidth(parte).height(alto).background(paleta.acento, forma))
        }
    }
}
