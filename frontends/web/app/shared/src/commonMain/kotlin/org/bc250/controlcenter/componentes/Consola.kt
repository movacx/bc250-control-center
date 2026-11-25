package org.bc250.controlcenter.componentes

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.selection.SelectionContainer
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.Trabajo
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_down_gray
import org.bc250.controlcenter.recursos.close_gray
import org.bc250.controlcenter.recursos.copy_gray
import org.bc250.controlcenter.recursos.stop_red
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.jetbrains.compose.resources.DrawableResource

private val AltoInicial = 280.dp
private val AltoMenor = 140.dp
private val AltoMayor = 500.dp
private const val SALTO = 12f
private const val DURACION_SALTO = 750

/** El texto de una consola; se desplaza solo si su alto está fijado, si no crece con la ventana. */
@Composable
fun TextoConsola(texto: String, modifier: Modifier = Modifier, color: Color? = null) {
    val paleta = ColoresActuales.current
    val desplazador = rememberScrollState()
    LaunchedEffect(texto) {
        desplazador.scrollTo(desplazador.maxValue)
    }
    BoxWithConstraints(
        modifier = modifier
            .marco(paleta.color("console_bg"), paleta.color("console_border"), Medidas.radioPanel)
            .padding(horizontal = 15.dp, vertical = 14.dp),
    ) {
        val desplazable = if (constraints.hasBoundedHeight) Modifier.verticalScroll(desplazador) else Modifier
        SelectionContainer {
            BasicText(
                text = texto,
                style = estiloTexto(11, 400, color ?: paleta.color("console_text"), deConsola = true),
                modifier = desplazable,
            )
        }
    }
}

/** El panel que sube desde abajo, con una pestaña por operación. */
@Composable
fun PanelConsola(aplicacion: Aplicacion, modifier: Modifier = Modifier) {
    val paleta = ColoresActuales.current
    val densidad = LocalDensity.current
    var alto by remember { mutableStateOf(AltoInicial) }
    val trabajo = aplicacion.trabajoEnPantalla()
    val arrastre = Modifier.pointerInput(Unit) {
        detectVerticalDragGestures { _, movimiento ->
            val cambio = with(densidad) { movimiento.toDp() }
            alto = (alto - cambio).coerceIn(AltoMenor, AltoMayor)
        }
    }
    Column(modifier.fillMaxWidth().height(alto).background(paleta.color("console_bg"))) {
        LineaDivisoria(color = paleta.bordeFuerte)
        CabeceraConsola(aplicacion, trabajo, arrastre)
        LineaDivisoria(color = paleta.color("console_border"))
        TextoConsola(trabajo.texto, Modifier.fillMaxWidth().weight(1f))
        if (trabajo.esperaClave || trabajo.esperaRespuesta) {
            RespuestaConsola(aplicacion, trabajo)
        }
    }
}

// -- cabecera ----------------------------------------------------------------------------------------

@Composable
private fun CabeceraConsola(aplicacion: Aplicacion, trabajo: Trabajo, arrastre: Modifier) {
    val paleta = ColoresActuales.current
    Row(
        modifier = arrastre
            .fillMaxWidth()
            .height(46.dp)
            .background(paleta.panelAlterno)
            .padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(Modifier.weight(1f).horizontalScroll(rememberScrollState()), Arrangement.spacedBy(4.dp)) {
            for (abierto in aplicacion.trabajos) {
                PestanaConsola(aplicacion, abierto, abierto.id == trabajo.id)
            }
            if (aplicacion.trabajos.isEmpty()) {
                Texto(t("Terminal"), tamano = 13, peso = 760, modifier = Modifier.padding(horizontal = 8.dp))
            }
        }
        if (trabajo.fallo) {
            Boton(
                texto = t("Report this problem"),
                alPulsar = { aplicacion.abrirAjustes("support_report") },
                clase = ClaseBoton.CONTORNO,
                alto = 30.dp,
                tamano = 12,
            )
        }
        AccionesConsola(aplicacion, trabajo)
    }
}

@Composable
private fun PestanaConsola(aplicacion: Aplicacion, trabajo: Trabajo, elegida: Boolean) {
    val paleta = ColoresActuales.current
    val varias = aplicacion.trabajos.size > 1
    val fondo = if (varias && elegida) paleta.color("console_bg") else Color.Transparent
    val color = if (varias && !elegida) paleta.apagado else paleta.texto
    Column(Modifier.width(IntrinsicSize.Max).background(fondo)) {
        Row(
            modifier = Modifier
                .height(32.dp)
                .pulsable { aplicacion.trabajoElegido = trabajo.id }
                .padding(start = 8.dp, end = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextoMono(">_", tamano = 11, color = color)
            Texto(trabajo.titulo, tamano = 13, peso = if (varias && !elegida) 620 else 760, color = color, lineas = 1)
            if (trabajo.terminado) {
                BotonIcono(
                    icono = Res.drawable.close_gray,
                    alPulsar = { aplicacion.cerrarTrabajo(trabajo.id) },
                    lado = 18.dp,
                    tamano = 11.dp,
                    conMarco = false,
                )
            }
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(colorDeEstado(trabajo)))
    }
}

/** La raya bajo la pestaña dice cómo va: en marcha, bien, mal o detenida. */
@Composable
private fun colorDeEstado(trabajo: Trabajo): Color {
    val paleta = ColoresActuales.current
    return when {
        !trabajo.terminado -> paleta.acento
        trabajo.correcto -> paleta.verde
        trabajo.cancelado -> paleta.naranja
        else -> paleta.rojo
    }
}

@Composable
private fun AccionesConsola(aplicacion: Aplicacion, trabajo: Trabajo) {
    val paleta = ColoresActuales.current
    val portapapeles = LocalClipboardManager.current
    fun copiar() {
        portapapeles.setText(AnnotatedString(trabajo.texto))
    }
    Row(
        modifier = Modifier.marco(Color.Transparent, paleta.bordeSuave, 4.dp).padding(2.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (!trabajo.terminado) {
            AccionConsola(Res.drawable.stop_red, t("Stop"), aplicacion::interrumpirTrabajo)
        }
        AccionConsola(Res.drawable.copy_gray, t("Copy"), ::copiar)
        AccionConsola(Res.drawable.chevron_down_gray, t("Hide")) { aplicacion.consolaVisible = false }
    }
}

@Composable
private fun AccionConsola(icono: DrawableResource, nombre: String, alPulsar: () -> Unit) {
    Row(
        modifier = Modifier.height(28.dp).pulsable(alPulsar = alPulsar).padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icono(icono, 16.dp)
        Texto(nombre, tamano = 13, peso = 640, color = ColoresActuales.current.apagado)
    }
}

// -- respuesta -----------------------------------------------------------------------------------------

@Composable
private fun RespuestaConsola(aplicacion: Aplicacion, trabajo: Trabajo) {
    val paleta = ColoresActuales.current
    var respuesta by remember(trabajo.id, trabajo.esperaClave) { mutableStateOf("") }
    fun enviar() {
        aplicacion.responderTrabajo(respuesta)
        respuesta = ""
    }
    LineaDivisoria(color = paleta.color("console_border"))
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 12.dp, top = 8.dp, end = 10.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val color = if (trabajo.esperaClave) paleta.naranja else paleta.apagado
        Texto(t(if (trabajo.esperaClave) "Linux password" else "Input"), tamano = 13, peso = 700, color = color)
        CampoTexto(
            valor = respuesta,
            alCambiar = { nuevo -> respuesta = nuevo },
            secreto = trabajo.esperaClave,
            ayuda = t("Type here and press Enter"),
            alAceptar = ::enviar,
            modifier = Modifier.weight(1f),
        )
        Boton(t("Send"), ::enviar, clase = ClaseBoton.PRINCIPAL, alto = 36.dp)
    }
}

// -- baliza ----------------------------------------------------------------------------------------------

/** El botón que salta cuando hay una operación en marcha y la consola está escondida. */
@Composable
fun BalizaConsola(aplicacion: Aplicacion, modifier: Modifier = Modifier) {
    val paleta = ColoresActuales.current
    val movimiento = rememberInfiniteTransition()
    val subida by movimiento.animateFloat(
        initialValue = 0f,
        targetValue = -SALTO,
        animationSpec = infiniteRepeatable(tween(DURACION_SALTO, easing = FastOutSlowInEasing), RepeatMode.Reverse),
    )
    Box(
        modifier = modifier
            .padding(end = 26.dp)
            .offset(y = subida.dp)
            .size(54.dp)
            .background(paleta.color("blue"), CircleShape)
            .pulsable { aplicacion.consolaVisible = true },
        contentAlignment = Alignment.Center,
    ) {
        TextoMono(">_", tamano = 18, color = paleta.sobreAcento)
    }
}
