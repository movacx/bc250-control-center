package org.bc250.controlcenter.paginas

import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales

@Composable
internal fun DiagnosticoCajaNegra(aplicacion: Aplicacion, alto: Dp) {
    var datos by remember { mutableStateOf(ObjetoVacio) }
    var revision by remember { mutableStateOf(0) }
    var pestaña by remember { mutableStateOf("all") }
    var buscar by remember { mutableStateOf("") }
    var abiertas by remember { mutableStateOf(setOf<String>()) }
    val portapapeles = LocalClipboardManager.current
    LaunchedEffect(revision) {
        datos = aplicacion.consultar("black_box.diagnosis", mapOf("refresh" to if (revision == 0) "0" else "1"))
        if (datos.isEmpty()) datos = buildJsonObject { put("error", JsonPrimitive(t("Not connected"))) }
        while (datos.logico("loading")) {
            delay(800)
            datos = aplicacion.consultar("black_box.diagnosis")
            if (datos.isEmpty()) datos = buildJsonObject { put("error", JsonPrimitive(t("Not connected"))) }
        }
    }
    val secciones = datos.objetos("sections")
    val visibles = secciones.filter {
        (pestaña == "all" || it.texto("group") == pestaña) &&
            (buscar.isBlank() || it.texto("title").contains(buscar.trim(), true) || it.texto("text").contains(buscar.trim(), true))
    }
    LaunchedEffect(buscar, pestaña, datos) {
        if (buscar.isNotBlank()) abiertas = abiertas + visibles.map { it.texto("title") }
    }
    val listaPestañas = datos.objetos("tabs").map { Eleccion(it.texto("key"), it.texto("label")) }
    PestanasSupervision(listaPestañas, pestaña) { pestaña = it }
    HerramientasSupervision {
        CampoTexto(buscar, { buscar = it }, ayuda = t("Search the diagnosis"), activo = datos.logico("ready"))
        AccionSupervision(t("Expand all"), datos.logico("ready")) { abiertas = abiertas + visibles.map { it.texto("title") } }
        AccionSupervision(t("Collapse all"), datos.logico("ready")) { abiertas = abiertas - visibles.map { it.texto("title") }.toSet() }
    }
    if (datos.isEmpty() || datos.logico("loading")) {
        Texto(t("Collecting the diagnosis… This can take a few seconds."), 12)
    }
    if (datos.texto("error").isNotEmpty()) Texto(datos.texto("error"), 12, color = ColoresActuales.current.rojo)
    if (datos.logico("ready") && visibles.isEmpty()) Texto(t("No section matches your search."), 12)
    LazyColumn(Modifier.fillMaxWidth().height((alto - 150.dp).coerceAtLeast(250.dp)), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items(visibles) { seccion ->
            val titulo = seccion.texto("title")
            val abierta = titulo in abiertas
            Column {
                Row(
                    modifier = Modifier.fillMaxWidth().pulsable {
                        abiertas = if (titulo in abiertas) abiertas - titulo else abiertas + titulo
                    }.padding(vertical = 9.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    FlechaPlegar(abierto = abierta)
                    Texto("$titulo (${seccion.entero("size")} KB)", 12, peso = 700)
                }
                if (abierta) SeccionDiagnostico(seccion.texto("text"))
                LineaDivisoria()
            }
        }
    }
    HerramientasSupervision {
        AccionSupervision(t("Refresh"), !datos.logico("loading")) { revision += 1 }
        AccionSupervision(t("Copy all"), datos.logico("ready")) {
            portapapeles.setText(AnnotatedString(datos.texto("text")))
            aplicacion.avisar(t("Paste it into your problem report."))
        }
        if (datos.logico("ready")) GuardarDocumentoSupervision(aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=diagnosis")
    }
}

@Composable
private fun SeccionDiagnostico(texto: String) {
    var altura by remember { mutableStateOf(220f) }
    var ajustar by remember { mutableStateOf(false) }
    val paleta = ColoresActuales.current
    SelectionContainer {
        Column(Modifier.fillMaxWidth().height(altura.dp).marco(paleta.control, paleta.bordeSuave, 8.dp)
            .verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()).padding(8.dp)) {
            Texto(texto, 11)
        }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
        TresPuntos(Modifier.pointerInput(Unit) {
            detectDragGestures { cambio, arrastre ->
                cambio.consume()
                altura = (altura + arrastre.y / density).coerceIn(90f, 3000f)
            }
        }.pulsable {
            ajustar = !ajustar
            altura = if (ajustar) (texto.lines().size * 16f + 32f).coerceIn(90f, 3000f) else 220f
        }.padding(14.dp))
    }
}
