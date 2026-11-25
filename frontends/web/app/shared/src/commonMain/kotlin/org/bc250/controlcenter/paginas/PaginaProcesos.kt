package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.recursos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasSupervision

@Composable
fun PaginaProcesos(aplicacion: Aplicacion) {
    val focoBuscar = remember { FocusRequester() }
    var enBusqueda by remember { mutableStateOf(false) }
    var recargar by remember { mutableStateOf(0) }
    var vista by remember { mutableStateOf("apps") }
    var buscar by remember { mutableStateOf("") }
    var agrupar by remember { mutableStateOf(true) }
    var orden by remember { mutableStateOf("memory") }
    var descendente by remember { mutableStateOf(true) }
    var errorConsulta by remember { mutableStateOf(false) }
    var datos by remember { mutableStateOf(ObjetoVacio) }
    var seleccion by remember { mutableStateOf(setOf<String>()) }
    LaunchedEffect(vista, buscar, agrupar, orden, descendente, seleccion, recargar) {
        delay(120)
        while (true) {
            val respuesta = aplicacion.consultar("processes.rows", mapOf("view" to vista, "search" to buscar,
                "grouped" to if (agrupar) "1" else "0", "sort" to orden,
                "descending" to if (descendente) "1" else "0",
                "selected" to JsonArray(seleccion.map { JsonPrimitive(it) }).toString()))
            errorConsulta = respuesta.isEmpty()
            if (!errorConsulta) datos = respuesta
            val presentes = datos.objetos("rows").map { it.texto("key") }.toSet()
            seleccion = seleccion.intersect(presentes)
            delay(3000)
        }
    }
    val filas = datos.objetos("rows")
    val elegidos = filas.filter { it.texto("key") in seleccion }
    val disponible = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    MarcoSupervision(Modifier.onPreviewKeyEvent { evento ->
        if (evento.type != KeyEventType.KeyDown) false
        else when {
            evento.isCtrlPressed && evento.key == Key.F -> { focoBuscar.requestFocus(); true }
            evento.key == Key.F5 -> { recargar += 1; true }
            evento.key == Key.Delete && !enBusqueda && disponible && elegidos.isNotEmpty() -> { actuarProcesos(aplicacion, elegidos, "end"); true }
            evento.isCtrlPressed && evento.key == Key.A && !enBusqueda -> {
                seleccion = filas.filter { !it.logico("protected") }.map { it.texto("key") }.toSet()
                true
            }
            evento.key == Key.Escape -> { seleccion = emptySet(); true }
            else -> false
        }
    }) { alto ->
        val juego = datos.objeto("game")
        if (juego.isNotEmpty()) {
            JuegoProcesos(aplicacion, juego, datos.logico("oomd"), disponible)
        }
        PestanasSupervision(listOf(Eleccion("apps", t("Apps and games")), Eleccion("background", t("Background")),
            Eleccion("system", t("System")), Eleccion("all", t("All"))), vista) { vista = it }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth < MedidasSupervision.limiteMovil) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    CampoTexto(buscar, { buscar = it.take(256) }, ayuda = t("Search application, PID, or command"), modifier = Modifier.height(34.dp).onFocusChanged { enBusqueda = it.hasFocus }.focusRequester(focoBuscar))
                    CasillaSupervision(t("Group by application"), agrupar, interruptor = true) { agrupar = it }
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                    CampoTexto(buscar, { buscar = it.take(256) }, Modifier.weight(1f).height(34.dp).onFocusChanged { enBusqueda = it.hasFocus }.focusRequester(focoBuscar), ayuda = t("Search application, PID, or command"))
                    CasillaSupervision(t("Group by application"), agrupar, interruptor = true) { agrupar = it }
                }
            }
        }
        TablaProcesos(filas, seleccion, (alto - if (juego.isEmpty()) 251.dp else 353.dp).coerceAtLeast(360.dp), orden,
            descendente, alOrdenar = { nuevo ->
                descendente = if (orden == nuevo) !descendente else nuevo != "name"
                orden = nuevo
            }, alElegir = { clave ->
                seleccion = if (clave in seleccion) seleccion - clave else seleccion + clave
            })
        LineaDivisoria()
        if (elegidos.isNotEmpty()) {
            Texto(datos.texto("selection"), 12)
        }
        FranjaSupervision(izquierda = {
            AccionSupervision(t("Select visible"), filas.any { !it.logico("protected") }) {
                seleccion = filas.filter { !it.logico("protected") }.map { it.texto("key") }.toSet()
            }
            AccionSupervision(t("Clear selection"), seleccion.isNotEmpty()) { seleccion = emptySet() }
        }, derecha = {
            AccionSupervision(t("Release page cache"), disponible) {
                aplicacion.preguntarYEjecutar("processes.cache", t("Release Linux page cache"),
                    t("The files Linux keeps in memory are dropped and read from the disk again when needed."))
            }
            val reanudar = elegidos.isNotEmpty() && elegidos.all { it.logico("paused") }
            AccionSupervision(t(if (reanudar) "Resume" else "Pause"), disponible && elegidos.isNotEmpty()) {
                actuarProcesos(aplicacion, elegidos, if (reanudar) "resume" else "pause")
            }
            AccionSupervision(t("End tasks"), disponible && elegidos.isNotEmpty(), peligro = true) {
                actuarProcesos(aplicacion, elegidos, "end")
            }
        })
        if (errorConsulta) Texto(t("Not connected"), 12, color = ColoresActuales.current.rojo)
        Texto(if (datos.isEmpty()) t("Waiting for process inventory") else if (filas.isEmpty()) t("No results")
            else datos.texto("summary"), 11, color = ColoresActuales.current.apagado)
    }
}

private fun actuarProcesos(aplicacion: Aplicacion, filas: List<JsonObject>, operacion: String) {
    val objetivos = filas.flatMap { it.lista("targets") }.distinct()
    if (objetivos.isEmpty()) return
    val titulo = t(when (operacion) { "end" -> "End tasks"; "pause" -> "Pause"; else -> "Resume" })
    val nombres = filas.joinToString(", ") { it.texto("name") }
    val aviso = if (operacion == "end") t("Each application is asked to close first; whatever is still running 1.5 seconds later is ended. Unsaved work in them is lost. Protected desktop programs are never touched.") else titulo
    aplicacion.preguntarYEjecutar("processes.tasks", titulo, "$aviso\n$nombres",
        mapOf("operation" to JsonPrimitive(operacion), "targets" to JsonArray(objetivos)), peligro = operacion == "end")
}

@Composable
private fun JuegoProcesos(aplicacion: Aplicacion, juego: JsonObject, oomd: Boolean, disponible: Boolean) {
    TituloPanel(t("Playing now"))
    Texto(juego.texto("name"), 15, peso = 800)
    Texto("CPU ${juego.texto("cpu", "—")} % · GPU ${juego.texto("gpu", "—")} % · ${juego.texto("memory")} · ${juego.texto("vram")}", 12)
    if (oomd && juego.logico("paused")) {
        Texto(t("systemd-oomd is running: if the paused game's memory goes to swap, it may close the game and Steam with it."),
            12, color = ColoresActuales.current.naranja)
    }
    HerramientasSupervision {
        AccionSupervision(t(if (juego.logico("paused")) "Resume game" else "Pause game"), disponible && !juego.logico("protected")) {
            actuarProcesos(aplicacion, listOf(juego), if (juego.logico("paused")) "resume" else "pause")
        }
        AccionSupervision(t("Close game"), disponible && !juego.logico("protected"), peligro = true) {
            actuarProcesos(aplicacion, listOf(juego), "end")
        }
    }
    LineaDivisoria()
}

@Composable
private fun TablaProcesos(filas: List<JsonObject>, seleccion: Set<String>, alto: androidx.compose.ui.unit.Dp,
    orden: String, descendente: Boolean, alOrdenar: (String) -> Unit, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val ancho = maxWidth.coerceAtLeast(980.dp)
        Column(Modifier.horizontalScroll(rememberScrollState()).width(ancho)) {
            Row(Modifier.fillMaxWidth().height(32.dp), verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width(40.dp))
                val columnas = listOf("name" to "Application", "cpu" to "CPU", "gpu" to "GPU", "memory" to "Memory", "vram" to "GPU memory")
                for ((clave, titulo) in columnas) {
                    val modificador = if (clave == "name") Modifier.weight(1f) else Modifier.width(if (clave == "memory") 104.dp else 96.dp)
                    Texto(t(titulo).uppercase() + if (clave == orden) { if (descendente) " ↓" else " ↑" } else "", 10,
                        modifier = modificador.pulsable { alOrdenar(clave) }.padding(horizontal = 6.dp), peso = 800, color = paleta.apagado)
                }
                Texto(t("Status").uppercase(), 10, modifier = Modifier.width(130.dp), peso = 800, color = paleta.apagado)
            }
            LazyColumn(Modifier.fillMaxWidth().height(alto)) {
                items(filas, key = { it.texto("key") }) { fila ->
                    val clave = fila.texto("key")
                    val protegida = fila.logico("protected")
                    Row(Modifier.fillMaxWidth().height(MedidasSupervision.filaProceso)
                        .background(if (clave in seleccion) paleta.elegido else paleta.panel)
                        .pulsable(!protegida) { alElegir(clave) }, verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(40.dp), contentAlignment = Alignment.Center) {
                            Casilla(clave in seleccion, { alElegir(clave) }, activa = !protegida)
                        }
                        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Icono(Res.drawable.processes_gray, 26.dp)
                            Column {
                                Texto(fila.texto("name"), 13, peso = 700)
                                Texto(fila.texto("subtitle"), 11, color = paleta.apagado)
                            }
                        }
                        for (campo in listOf("cpu", "gpu", "memory", "vram")) {
                            Column(Modifier.width(if (campo == "memory") 104.dp else 96.dp).padding(horizontal = 6.dp)) {
                                Texto(fila.texto(if (campo in listOf("cpu", "gpu")) campo + "_text" else campo, "—"), 12, peso = 700)
                            }
                        }
                        Texto(fila.texto("status"), 12, modifier = Modifier.width(130.dp), color = if (fila.texto("tone") == "gray") paleta.sutil else paleta.color(fila.texto("tone", "green")))
                    }
                    LineaDivisoria(color = paleta.bordeSuave)
                }
            }
        }
    }
}
