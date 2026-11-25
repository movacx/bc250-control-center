package org.bc250.controlcenter.componentes

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.background
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasSupervision


@Composable
fun MarcoSupervision(modifier: Modifier = Modifier, contenido: @Composable ColumnScope.(Dp) -> Unit) {
    BoxWithConstraints(modifier.fillMaxSize()) {
        val alto = (maxHeight - MedidasSupervision.margenSuperior - MedidasSupervision.margenInferior).coerceAtLeast(420.dp)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(
            start = MedidasSupervision.margenHorizontal, end = MedidasSupervision.margenHorizontal,
            top = MedidasSupervision.margenSuperior, bottom = MedidasSupervision.margenInferior,
        )) {
            TarjetaPagina(Modifier.fillMaxWidth().heightIn(min = alto), espacio = MedidasSupervision.espacio) {
                contenido(alto)
            }
        }
    }
}

/** Herramientas que se apilan en un teléfono. */
@Composable
fun HerramientasSupervision(contenido: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < MedidasSupervision.limiteMovil) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { contenido() }
        } else {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically) { contenido() }
        }
    }
}

@Composable
fun AccionSupervision(texto: String, activa: Boolean = true, peligro: Boolean = false, primaria: Boolean = false, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val color = when {
        !activa -> paleta.textoInactivo
        peligro -> paleta.rojo
        primaria -> paleta.acento
        else -> paleta.texto
    }
    val borde = when {
        !activa -> paleta.bordeSuave
        peligro -> paleta.rojoBorde
        primaria -> paleta.acentoBorde
        encima -> paleta.bordeFuerte
        else -> paleta.borde
    }
    val fondo = if (encima && activa) paleta.controlEncima else paleta.panel
    Box(Modifier.height(MedidasSupervision.boton).marco(fondo, borde, 8.dp)
        .pulsable(activa, interaccion, alPulsar).padding(horizontal = 14.dp), contentAlignment = Alignment.Center) {
        Texto(texto, 12, peso = 650, color = color)
    }
}

@Composable
fun PestanasSupervision(opciones: List<Eleccion>, elegida: String, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
        for (opcion in opciones) {
            Column(Modifier.width(IntrinsicSize.Max).pulsable { alElegir(opcion.valor) }) {
                Texto(opcion.nombre, 12, peso = 700, color = if (elegida == opcion.valor) paleta.texto else paleta.apagado,
                    modifier = Modifier.padding(vertical = 9.dp))
                Box(Modifier.fillMaxWidth().height(2.dp).background(if (elegida == opcion.valor) paleta.acento else paleta.bordeSuave))
            }
        }
    }
}

@Composable
fun CasillaSupervision(texto: String, marcada: Boolean, activa: Boolean = true, interruptor: Boolean = false, alCambiar: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (interruptor) {
            val paleta = ColoresActuales.current
            Canvas(Modifier.size(44.dp, 26.dp).toggleable(marcada, enabled = activa, role = Role.Switch, onValueChange = alCambiar)) {
                val color = if (marcada) paleta.acento else paleta.color("control_pressed")
                drawRoundRect(color, Offset(2.dp.toPx(), 2.dp.toPx()), Size(40.dp.toPx(), 22.dp.toPx()),
                    CornerRadius(11.dp.toPx()), alpha = if (activa) 1f else 0.45f)
                drawCircle(if (marcada) paleta.sobreAcento else paleta.apagado, 8.dp.toPx(),
                    Offset((if (marcada) 31.dp else 13.dp).toPx(), 13.dp.toPx()), alpha = if (activa) 1f else 0.45f)
            }
        } else Casilla(marcada, alCambiar, activa = activa)
        Texto(texto, 12, color = ColoresActuales.current.apagado)
    }
}

/** Texto seleccionable y copia disponibles también en Android y JVM. */
@Composable
fun DocumentoSupervision(titulo: String, texto: String, descarga: String = "", alCerrar: () -> Unit) {
    val portapapeles = LocalClipboardManager.current
    Dialogo(alCerrar, ancho = 900.dp) {
        TituloPanel(titulo)
        SelectionContainer {
            Column(Modifier.fillMaxWidth().heightIn(max = 480.dp).verticalScroll(rememberScrollState())
                .horizontalScroll(rememberScrollState())) {
                Texto(texto, 11)
            }
        }
        HerramientasSupervision {
            AccionSupervision(t("Copy all")) { portapapeles.setText(AnnotatedString(texto)) }
            GuardarDocumentoSupervision(descarga)
            AccionSupervision(t("Close"), alPulsar = alCerrar)
        }
    }
}

/** Abre un documento local en el cliente; ninguna ruta del servidor entra en la petición. */
@Composable
fun GuardarDocumentoSupervision(descarga: String) {
    if (descarga.isEmpty()) return
    val enlaces = LocalUriHandler.current
    var error by remember { mutableStateOf(false) }
    AccionSupervision(t("Save as file…")) {
        try {
            enlaces.openUri(descarga)
        } catch (fallo: Exception) {
            error = true
        }
    }
    if (error) {
        Dialogo({ error = false }) {
            Texto(t("Could not save the file: {reason}", "reason" to t("Not connected")), 12)
            AccionSupervision(t("Close")) { error = false }
        }
    }
}

/** Selector compacto del escritorio, con el menú común accesible por teclado. */
@Composable
fun SelectorSupervision(opciones: List<Eleccion>, elegida: String, activo: Boolean = true, modifier: Modifier = Modifier,
    alElegir: (String) -> Unit) {
    var abierto by remember { mutableStateOf(false) }
    val paleta = ColoresActuales.current
    val actual = opciones.firstOrNull { it.valor == elegida }
    Box(modifier) {
        Row(Modifier.fillMaxWidth().height(27.dp).marco(paleta.control, paleta.borde, 7.dp)
            .pulsable(activo) { abierto = true }.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(actual?.nombre.orEmpty(), 12, Modifier.weight(1f), peso = 710,
                color = if (activo) paleta.texto else paleta.textoInactivo)
            FlechaPlegar(abierto = true)
        }
        if (abierto) MenuOpciones(opciones, elegida, { abierto = false }) {
            abierto = false
            alElegir(it)
        }
    }
}

@Composable
fun FranjaSupervision(izquierda: @Composable () -> Unit, derecha: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < 1000.dp) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                izquierda()
                derecha()
            }
        } else {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) { izquierda() }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) { derecha() }
            }
        }
    }
}

/** La explicación de una lectura, también expuesta a lectores de pantalla. */
@Composable
fun AyudaSupervision(texto: String, modifier: Modifier = Modifier, contenido: @Composable () -> Unit) {
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val paleta = ColoresActuales.current
    Box(modifier.hoverable(interaccion).semantics { stateDescription = texto }) {
        contenido()
        if (encima && texto.isNotBlank()) {
            Popup(alignment = Alignment.BottomCenter, properties = PopupProperties(focusable = false)) {
                Box(Modifier.widthIn(max = 420.dp).marco(paleta.panelElevado, paleta.bordeFuerte, 4.dp).padding(8.dp)) {
                    Texto(texto, 12)
                }
            }
        }
    }
}
