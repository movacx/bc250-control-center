package org.bc250.controlcenter.movil

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.controlarCajaNegra
import org.bc250.controlcenter.paginas.textoRegistroCajaNegra
import org.bc250.controlcenter.paginas.recordarDiagnosticoCajaNegra
import org.bc250.controlcenter.tema.ColoresActuales

@Composable
fun PaginaCajaNegraMovil(aplicacion: Aplicacion) {
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("black_box")
            delay(1000)
        }
    }
    val estado = movil()
    val datos = aplicacion.lectura("black_box")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val grabando = datos.logico("running")
    var siguiendo by remember { mutableStateOf(true) }
    var inicio by remember { mutableStateOf<Float?>(null) }
    PaginaMovil("black_box") {
        if (estado.detalle.isNotEmpty()) {
            DiagnosticoMovil(aplicacion)
        } else {
            EstadoLecturaMovil(datos)
            GrupoMovil(Modifier.onGloballyPositioned { coordenadas ->
                val y = coordenadas.positionInWindow().y
                val origen = inicio ?: y.also { inicio = it }
                siguiendo = y >= origen - 1f
            }) {
                Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                    BotonMovil(
                        t(if (grabando) "Stop recording" else "Start recording"), Modifier.fillMaxWidth(),
                        if (grabando) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL,
                        libre && datos.logico("supported"),
                    ) { controlarCajaNegra(aplicacion, if (grabando) "stop" else "start") }
                    ParejaBotones {
                        BotonMovil(t("View full diagnosis"), Modifier.weight(1f)) {
                            estado.abrirDetalle(t("View full diagnosis"))
                        }
                        BotonMovil(t("Export"), Modifier.weight(1f)) {
                            estado.abrirHoja { ExportarRegistro(aplicacion) }
                        }
                    }
                }
                val inicio = datos.objeto("autostart")
                if (inicio.logico("supported")) {
                    FilaInterruptor(t("Start with the session"), inicio.logico("enabled"),
                        activa = libre && !inicio.logico("foreign")) {
                        controlarCajaNegra(aplicacion, "autostart", it)
                    }
                }
            }
            NotaMovil(datos.texto("message", t("Waiting for data…")),
                if (datos.texto("state") == "cut-off") ColoresActuales.current.naranja else ColoresActuales.current.apagado,
                tamano = 13)
            RegistroMovil(datos, siguiendo)
        }
    }
}

@Composable
private fun RegistroMovil(datos: JsonObject, siguiendo: Boolean) {
    val estado = movil()
    var filas by remember { mutableStateOf(emptyList<JsonObject>()) }
    val nuevas = datos.objetos("rows")
    LaunchedEffect(nuevas, siguiendo) { if (siguiendo) filas = nuevas }
    val columnas = datos.objetos("columns")
    val resumen = listOf("time", "clock", "busy", "t_gpu", "watts", "cpu")
    val nombres = mapOf("time" to t("Time"), "clock" to "GPU", "busy" to t("Load"),
        "t_gpu" to "°C", "watts" to "W", "cpu" to "CPU")
    val visibles = resumen.mapNotNull { clave -> columnas.firstOrNull { it.texto("key") == clave } }
    GrupoMovil {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val ancho = maxWidth.coerceAtLeast(380.dp)
            Column(Modifier.horizontalScroll(rememberScrollState()).width(ancho)) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 10.dp)) {
                    for (columna in visibles) {
                        Texto(nombres[columna.texto("key")].orEmpty(), 12, Modifier.weight(1f), color = ColoresActuales.current.apagado,
                            alineado = TextAlign.End)
                    }
                }
                for (fila in filas) {
                    Row(Modifier.fillMaxWidth().lineaArriba().heightIn(min = 44.dp)
                        .pulsable { estado.abrirHoja { DetalleRegistro(fila, columnas) } }
                        .padding(horizontal = 8.dp, vertical = 9.dp)) {
                        for (columna in visibles) {
                            val valor = fila.texto(columna.texto("key"), "–")
                            Texto(valorCorto(columna.texto("key"), valor), 12, Modifier.weight(1f), alineado = TextAlign.End, lineas = 1)
                        }
                    }
                }
            }
        }
    }
    if (!siguiendo) NotaMovil(t("Paused while you read. Go back to the top to follow the recording."))
}

/** La hora sin milésimas y los relojes sin unidad, que ya está en el título. */
private fun valorCorto(clave: String, valor: String): String {
    return if (clave == "time") valor.substringBefore(".") else valor.removeSuffix("MHz").trim()
}

@Composable
private fun DetalleRegistro(fila: JsonObject, columnas: List<JsonObject>) {
    TituloHoja(fila.texto("time"))
    GrupoMovil {
        for (columna in columnas) FilaDato(columna.texto("label"), fila.texto(columna.texto("key"), "–"))
    }
    CerrarHoja()
}

@Composable
private fun ExportarRegistro(aplicacion: Aplicacion) {
    val datos = aplicacion.lectura("black_box")
    val texto = textoRegistroCajaNegra(datos)
    val portapapeles = LocalClipboardManager.current
    TituloHoja(t("Black box"))
    SelectionContainer { TextoHoja(texto) }
    ParejaBotones {
        BotonMovil(t("Copy all"), Modifier.weight(1f)) { portapapeles.setText(AnnotatedString(texto)) }
        BotonMovil(t("Save as file…"), Modifier.weight(1f)) {
            abrirDireccion(aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=recording")
        }
    }
    CerrarHoja()
}

@Composable
private fun DiagnosticoMovil(aplicacion: Aplicacion) {
    var revision by remember { mutableIntStateOf(0) }
    var grupo by remember { mutableStateOf("all") }
    var buscar by remember { mutableStateOf("") }
    var abiertas by remember { mutableStateOf(setOf<String>()) }
    val portapapeles = LocalClipboardManager.current
    val datos = recordarDiagnosticoCajaNegra(aplicacion, revision)
    val visibles = datos.objetos("sections").filter {
        (grupo == "all" || it.texto("group") == grupo) && (buscar.isBlank() ||
            it.texto("title").contains(buscar.trim(), true) || it.texto("text").contains(buscar.trim(), true))
    }
    LaunchedEffect(buscar, grupo, datos) {
        if (buscar.isNotBlank()) abiertas = abiertas + visibles.map { it.texto("title") }
    }
    val opciones = datos.objetos("tabs").map { it.texto("key") to it.texto("label") }
    if (opciones.isNotEmpty()) {
        val estado = movil()
        GrupoMovil {
            FilaAbrir(t("View full diagnosis"), valor = opciones.firstOrNull { it.first == grupo }?.second ?: "") {
                estado.abrirLista(t("View full diagnosis"), opciones, grupo) { grupo = it }
            }
        }
    }
    CampoMovil(buscar, Modifier.fillMaxWidth(), t("Search the diagnosis"), activo = datos.logico("ready")) { buscar = it }
    GrupoMovil {
        TiraAcciones(
            AccionTira(t("Expand all"), datos.logico("ready")) { abiertas = abiertas + visibles.map { it.texto("title") } },
            AccionTira(t("Collapse all"), datos.logico("ready")) {
                abiertas = abiertas - visibles.map { it.texto("title") }.toSet()
            },
        )
    }
    if (datos.isEmpty() || datos.logico("loading")) {
        NotaMovil(t("Collecting the diagnosis… This can take a few seconds."))
    }
    EstadoLecturaMovil(datos)
    if (datos.logico("ready") && visibles.isEmpty()) NotaMovil(t("No section matches your search."))
    for (seccion in visibles) {
        val titulo = seccion.texto("title")
        GrupoMovil {
            FilaAbrir(titulo, valor = "${seccion.entero("size")} KB") {
                abiertas = if (titulo in abiertas) abiertas - titulo else abiertas + titulo
            }
            if (titulo in abiertas) {
                SelectionContainer { Texto(seccion.texto("text"), 11, Modifier.padding(14.dp)) }
            }
        }
    }
    GrupoMovil {
        TiraAcciones(
            AccionTira(t("Refresh"), !datos.logico("loading")) { revision++ },
            AccionTira(t("Copy all"), datos.logico("ready")) {
                portapapeles.setText(AnnotatedString(datos.texto("text")))
                aplicacion.avisar(t("Paste it into your problem report."))
            },
        )
    }
    BotonMovil(t("Save as file…"), Modifier.fillMaxWidth(), activo = datos.logico("ready")) {
        abrirDireccion(aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=diagnosis")
    }
}
