package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.check_white
import org.bc250.controlcenter.recursos.chevron_down_gray
import org.bc250.controlcenter.recursos.chevron_up_gray
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** La casilla cuadrada del escritorio. */
@Composable
fun Casilla(
    marcada: Boolean,
    alCambiar: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    activa: Boolean = true,
    deRiesgo: Boolean = false,
) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val color = if (deRiesgo) paleta.rojo else paleta.acento
    val grosorBorde = if (deRiesgo) 2.dp else 1.dp
    val lado = if (deRiesgo) 22.dp else 20.dp
    val forma = RoundedCornerShape(3.dp)
    val fondo = if (marcada) color else if (deRiesgo) paleta.panel else paleta.panelAlterno
    val borde = when {
        marcada || (encima && activa) -> color
        deRiesgo -> paleta.rojoBorde
        else -> paleta.borde
    }
    Box(
        modifier = modifier
            .size(lado)
            .background(fondo, forma)
            .border(grosorBorde, borde, forma)
            .pulsable(activa, interaccion) { alCambiar(!marcada) },
        contentAlignment = Alignment.Center,
    ) {
        if (marcada) {
            Icono(Res.drawable.check_white, tamano = 14.dp)
        }
    }
}

/** El botón redondo de elegir una entre varias. */
@Composable
fun Opcion(elegida: Boolean, modifier: Modifier = Modifier, color: Color = ColoresActuales.current.rojo) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(4.dp)
    val grosorBorde = if (elegida) 5.dp else 2.dp
    val borde = if (elegida) color else paleta.bordeFuerte
    Box(modifier.size(16.dp).background(paleta.panel, forma).border(grosorBorde, borde, forma))
}

/** Un número con flechas para subir y bajar; también se puede escribir. */
@Composable
fun CampoNumero(
    valor: Int,
    alCambiar: (Int) -> Unit,
    minimo: Int,
    maximo: Int,
    modifier: Modifier = Modifier,
    paso: Int = 1,
    sufijo: String = "",
    activo: Boolean = true,
) {
    val paleta = ColoresActuales.current
    var escrito by remember { mutableStateOf(valor.toString()) }
    val interaccion = remember { MutableInteractionSource() }
    val enfocado by interaccion.collectIsFocusedAsState()
    LaunchedEffect(valor, enfocado) {
        if (!enfocado) {
            escrito = valor.toString()
        }
    }
    fun guardar() {
        val numero = escrito.toIntOrNull()
        if (numero != null) {
            alCambiar(numero.coerceIn(minimo, maximo))
        }
    }
    val borde = if (enfocado) paleta.color("focus") else paleta.borde
    val color = if (activo) paleta.texto else paleta.textoInactivo
    Row(
        modifier = modifier.height(43.dp).marco(paleta.control, borde, Medidas.radioPanel).padding(start = 12.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BasicTextField(
            value = escrito,
            onValueChange = { nuevo ->
                escrito = nuevo
                guardar()
            },
            enabled = activo,
            singleLine = true,
            textStyle = estiloTexto(13, 710, color, TextAlign.End),
            cursorBrush = SolidColor(paleta.texto),
            interactionSource = interaccion,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.weight(1f),
        )
        if (sufijo.isNotEmpty()) {
            Texto(" $sufijo", tamano = 13, peso = 710, color = color)
        }
        Column(Modifier.padding(start = 2.dp).fillMaxHeight(), verticalArrangement = Arrangement.SpaceBetween) {
            FlechaNumero(arriba = true, activo = activo && valor < maximo) {
                alCambiar((valor + paso).coerceAtMost(maximo))
            }
            FlechaNumero(arriba = false, activo = activo && valor > minimo) {
                alCambiar((valor - paso).coerceAtLeast(minimo))
            }
        }
    }
}

@Composable
private fun FlechaNumero(arriba: Boolean, activo: Boolean, alPulsar: () -> Unit) {
    val dibujo = if (arriba) Res.drawable.chevron_up_gray else Res.drawable.chevron_down_gray
    Box(
        modifier = Modifier.padding(vertical = 4.dp).size(20.dp, 14.dp).pulsable(activo, alPulsar = alPulsar),
        contentAlignment = Alignment.Center,
    ) {
        Icono(dibujo, tamano = 11.dp)
    }
}

/** Un campo de texto de una línea. */
@Composable
fun CampoTexto(
    valor: String,
    alCambiar: (String) -> Unit,
    modifier: Modifier = Modifier,
    ayuda: String = "",
    secreto: Boolean = false,
    activo: Boolean = true,
    alto: Dp = 40.dp,
    alAceptar: () -> Unit = {},
) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val enfocado by interaccion.collectIsFocusedAsState()
    val borde = if (enfocado) paleta.color("focus") else paleta.borde
    val vista = if (secreto) PasswordVisualTransformation() else VisualTransformation.None
    Box(
        modifier = modifier.height(alto).marco(paleta.control, borde, Medidas.radioPanel).padding(horizontal = 12.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (valor.isEmpty()) {
            Texto(ayuda, tamano = 13, color = paleta.sutil, lineas = 1)
        }
        BasicTextField(
            value = valor,
            onValueChange = alCambiar,
            enabled = activo,
            singleLine = true,
            textStyle = estiloTexto(13, 710),
            cursorBrush = SolidColor(paleta.texto),
            interactionSource = interaccion,
            visualTransformation = vista,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { alAceptar() }),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** Lo que se puede elegir en una lista: el valor, su nombre y, si cabe menos, su forma corta. */
class Eleccion(val valor: String, val nombre: String, val corto: String = nombre)

/** Una fila «nombre … valor» que abre sus opciones. */
@Composable
fun FilaEleccion(
    nombre: String,
    opciones: List<Eleccion>,
    elegida: String,
    alElegir: (String) -> Unit,
    modifier: Modifier = Modifier,
    activa: Boolean = true,
) {
    val paleta = ColoresActuales.current
    var abierta by remember { mutableStateOf(false) }
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val borde = if (encima && activa) paleta.bordeFuerte else paleta.borde
    val actual = opciones.firstOrNull { it.valor == elegida }
    val colorNombre = if (activa) paleta.apagado else paleta.sutil
    val colorValor = if (activa) paleta.texto else paleta.sutil
    Box(modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 38.dp)
                .marco(paleta.ventana, borde, Medidas.radioChico)
                .pulsable(activa, interaccion) { abierta = true }
                .padding(horizontal = 13.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Texto(nombre, tamano = 13, color = colorNombre, modifier = Modifier.weight(1f))
            Texto(actual?.corto ?: "", tamano = 13, peso = 700, color = colorValor, alineado = TextAlign.End)
        }
        if (abierta) {
            MenuOpciones(opciones, elegida, alCerrar = { abierta = false }) { valor ->
                abierta = false
                alElegir(valor)
            }
        }
    }
}

/** La lista que se despliega; se cierra al elegir o al pulsar fuera. */
@Composable
fun MenuOpciones(opciones: List<Eleccion>, elegida: String, alCerrar: () -> Unit, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Popup(
        alignment = Alignment.TopEnd,
        onDismissRequest = alCerrar,
        properties = PopupProperties(focusable = true),
    ) {
        Column(
            modifier = Modifier
                .widthIn(min = 160.dp, max = 560.dp)
                .heightIn(max = 420.dp)
                .marco(paleta.panelElevado, paleta.bordeFuerte, Medidas.radioPanel)
                .verticalScroll(rememberScrollState())
                .padding(5.dp),
        ) {
            for (opcion in opciones) {
                FilaMenu(opcion.nombre, opcion.valor == elegida) { alElegir(opcion.valor) }
            }
        }
    }
}

@Composable
private fun FilaMenu(nombre: String, elegida: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val fondo = if (encima) paleta.controlEncima else Color.Transparent
    Row(
        modifier = Modifier
            .background(fondo, RoundedCornerShape(4.dp))
            .pulsable(true, interaccion, alPulsar)
            .padding(horizontal = 10.dp, vertical = 7.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(14.dp)) {
            if (elegida) {
                Icono(Res.drawable.check_white, tamano = 13.dp, color = paleta.acento)
            }
        }
        Texto(nombre, tamano = 13, peso = if (elegida) 700 else 400)
    }
}
