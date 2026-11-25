package org.bc250.controlcenter.componentes

import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.LetrasActuales
import org.bc250.controlcenter.tema.altoDeLinea
import org.bc250.controlcenter.tema.grosor

/** El estilo de letra del escritorio para un tamaño en píxeles y un grosor de Qt. */
@Composable
fun estiloTexto(
    tamano: Int,
    peso: Int = 400,
    color: Color = ColoresActuales.current.texto,
    alineado: TextAlign = TextAlign.Start,
    espaciado: TextUnit = TextUnit.Unspecified,
    deConsola: Boolean = false,
): TextStyle {
    val letras = LetrasActuales.current
    return TextStyle(
        color = color,
        fontSize = tamano.sp,
        fontWeight = grosor(peso),
        fontFamily = if (deConsola) letras.consola else letras.normal,
        lineHeight = altoDeLinea(tamano).sp,
        lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None),
        textAlign = alineado,
        letterSpacing = espaciado,
    )
}

@Composable
fun Texto(
    texto: String,
    tamano: Int,
    modifier: Modifier = Modifier,
    peso: Int = 400,
    color: Color = ColoresActuales.current.texto,
    alineado: TextAlign = TextAlign.Start,
    lineas: Int = Int.MAX_VALUE,
    espaciado: TextUnit = TextUnit.Unspecified,
) {
    BasicText(
        text = texto,
        modifier = modifier,
        style = estiloTexto(tamano, peso, color, alineado, espaciado),
        maxLines = lineas,
        overflow = TextOverflow.Ellipsis,
    )
}

/** El título de un panel o de una tarjeta. */
@Composable
fun TituloPanel(texto: String, modifier: Modifier = Modifier) {
    Texto(texto, tamano = 14, peso = 780, modifier = modifier)
}

/** La línea pequeña que explica un panel. */
@Composable
fun Leyenda(texto: String, modifier: Modifier = Modifier) {
    Texto(texto, tamano = 10, color = ColoresActuales.current.sutil, modifier = modifier)
}
