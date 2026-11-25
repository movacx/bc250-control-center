package org.bc250.controlcenter.movil

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

/** Un campo de texto alto, cómodo para el dedo. */
@Composable
fun CampoMovil(
    valor: String,
    modifier: Modifier = Modifier,
    ayuda: String = "",
    numerico: Boolean = false,
    secreto: Boolean = false,
    activo: Boolean = true,
    alCambiar: (String) -> Unit,
) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val enfocado by interaccion.collectIsFocusedAsState()
    val borde = if (enfocado) paleta.color("focus") else paleta.borde
    Box(
        modifier = modifier.height(46.dp).marco(paleta.control, borde, 6.dp).padding(horizontal = 12.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (valor.isEmpty()) {
            Texto(ayuda, tamano = 14, color = paleta.sutil, lineas = 1)
        }
        BasicTextField(
            value = valor,
            onValueChange = alCambiar,
            enabled = activo,
            singleLine = true,
            textStyle = estiloTexto(14),
            cursorBrush = SolidColor(paleta.texto),
            interactionSource = interaccion,
            visualTransformation = if (secreto) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = if (numerico) KeyboardType.Number else KeyboardType.Text),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** Un cuadro para pegar un texto largo. */
@Composable
fun AreaDeTexto(valor: String, alto: Dp = 220.dp, ayuda: String = "", alCambiar: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxWidth().height(alto).marco(paleta.control, paleta.borde, 6.dp).padding(12.dp)) {
        if (valor.isEmpty()) {
            Texto(ayuda, tamano = 14, color = paleta.sutil)
        }
        BasicTextField(
            value = valor,
            onValueChange = alCambiar,
            textStyle = estiloTexto(14),
            cursorBrush = SolidColor(paleta.texto),
            modifier = Modifier.fillMaxSize(),
        )
    }
}

/** Un texto largo de solo lectura, con letra de consola y un botón para copiarlo. */
@Composable
fun DocumentoMovil(texto: String) {
    val portapapeles = LocalClipboardManager.current
    TextoConsola(texto, Modifier.fillMaxWidth())
    BotonMovil(t("Copy all"), Modifier.fillMaxWidth(), activo = texto.isNotEmpty()) {
        portapapeles.setText(AnnotatedString(texto))
    }
}

/** Un campo con su nombre encima. */
@Composable
fun CampoConNombreMovil(nombre: String, valor: String, numerico: Boolean = false, ayuda: String = "", alCambiar: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Texto(nombre, tamano = 13, color = ColoresActuales.current.apagado)
        CampoMovil(valor, Modifier.fillMaxWidth(), ayuda, numerico, alCambiar = alCambiar)
    }
}

/** Un valor que se desliza, con su nombre y su lectura encima. */
@Composable
fun DeslizadorMovil(nombre: String, valor: Int, unidad: String, minimo: Int, maximo: Int, activo: Boolean = true, alCambiar: (Int) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Texto(nombre, tamano = 13, color = ColoresActuales.current.apagado, modifier = Modifier.weight(1f))
            ValorConUnidad(valor.toString(), unidad, tamano = 16)
        }
        PistaDeslizador(valor, minimo, maximo, activo, alCambiar)
    }
}

@Composable
private fun PistaDeslizador(valor: Int, minimo: Int, maximo: Int, activo: Boolean, alCambiar: (Int) -> Unit) {
    val paleta = ColoresActuales.current
    val avisar by rememberUpdatedState(alCambiar)
    val toque = Modifier.pointerInput(minimo, maximo, activo) {
        if (!activo) {
            return@pointerInput
        }
        val margen = 8.dp.toPx()
        fun mover(x: Float) {
            val parte = ((x - margen) / (size.width - 2 * margen)).coerceIn(0f, 1f)
            avisar((minimo + parte * (maximo - minimo)).roundToInt())
        }
        awaitEachGesture {
            val inicio = awaitFirstDown()
            mover(inicio.position.x)
            drag(inicio.id) { cambio ->
                cambio.consume()
                mover(cambio.position.x)
            }
        }
    }
    val lleno = if (activo) paleta.acento else paleta.textoInactivo
    Box(
        Modifier.fillMaxWidth().height(36.dp).then(toque).drawBehind {
            val margen = 8.dp.toPx()
            val alto = 8.dp.toPx()
            val arriba = (size.height - alto) / 2
            val ancho = size.width - 2 * margen
            val lugar = margen + ancho * (valor - minimo) / (maximo - minimo).coerceAtLeast(1)
            val radio = CornerRadius(alto / 2)
            drawRoundRect(paleta.bordeFuerte, Offset(margen, arriba), Size(ancho, alto), radio)
            drawRoundRect(lleno, Offset(margen, arriba), Size(lugar - margen, alto), radio)
            drawCircle(lleno, 8.dp.toPx(), Offset(lugar, size.height / 2))
        },
    )
}
