package org.bc250.controlcenter.movil

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.consultarProcesos
import org.bc250.controlcenter.paginas.actuarProcesos
import org.bc250.controlcenter.paginas.liberarCacheProcesos
import org.bc250.controlcenter.tema.ColoresActuales

private class EstadoProcesos {
    var vista by mutableStateOf("apps")
    var buscar by mutableStateOf("")
    var agrupar by mutableStateOf(true)
    var orden by mutableStateOf("memory")
    var descendente by mutableStateOf(true)
    var seleccion by mutableStateOf(emptySet<String>())
    var datos by mutableStateOf(ObjetoVacio)
    var fallo by mutableStateOf(false)
    var recarga by mutableIntStateOf(0)
    val filas get() = datos.objetos("rows")
    val elegidos get() = filas.filter { it.texto("key") in seleccion && !it.logico("protected") }

    fun elegir(clave: String) {
        seleccion = if (clave in seleccion) seleccion - clave else seleccion + clave
    }
}

@Composable
fun PaginaProcesosMovil(aplicacion: Aplicacion) {
    val estado = remember { EstadoProcesos() }
    LecturasProcesos(aplicacion, estado)
    val movil = movil()
    val elegidos = estado.elegidos
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val reanudar = elegidos.isNotEmpty() && elegidos.all { it.logico("paused") }
    PaginaMovil("processes", pie = {
        BotonMovil(t(if (reanudar) "Resume" else "Pause"), Modifier.weight(1f), activo = libre && elegidos.isNotEmpty()) {
            actuarProcesos(aplicacion, elegidos, if (reanudar) "resume" else "pause")
        }
        BotonMovil(t("End tasks"), Modifier.weight(1f), ClaseBoton.PELIGRO, libre && elegidos.isNotEmpty()) {
            actuarProcesos(aplicacion, elegidos, "end")
        }
    }) {
        FilaOpciones(vistasDeProcesos(), setOf(estado.vista)) { vista -> estado.vista = vista }
        CampoMovil(estado.buscar, Modifier.fillMaxWidth(), t("Search application, PID, or command")) {
            estado.buscar = it.take(256)
        }
        val juego = estado.datos.objeto("game")
        if (juego.isNotEmpty()) JuegoMovil(aplicacion, juego, estado.datos.logico("oomd"), libre)
        ListaProcesos(estado)
        GrupoMovil {
            FilaInterruptor(t("Group by application"), estado.agrupar) { estado.agrupar = it }
            FilaAbrir(t("Sort and selection"), estado.datos.texto("selection"), t(ordenProceso(estado.orden))) {
                movil.abrirHoja { OpcionesProcesos(estado) }
            }
        }
        BotonMovil(t("Release page cache"), Modifier.fillMaxWidth(), activo = libre) { liberarCacheProcesos(aplicacion) }
        if (estado.fallo) NotaMovil(t("Not connected"), ColoresActuales.current.rojo)
    }
}

@Composable
private fun LecturasProcesos(aplicacion: Aplicacion, estado: EstadoProcesos) {
    LaunchedEffect(estado.vista, estado.buscar, estado.agrupar, estado.orden,
        estado.descendente, estado.seleccion, estado.recarga) {
        delay(120)
        while (true) {
            val respuesta = consultarProcesos(aplicacion, estado.vista, estado.buscar,
                estado.agrupar, estado.orden, estado.descendente, estado.seleccion)
            estado.fallo = respuesta.isEmpty()
            if (!estado.fallo) {
                estado.datos = respuesta
                estado.seleccion = estado.seleccion.intersect(estado.filas.map { it.texto("key") }.toSet())
            }
            delay(3000)
        }
    }
}

@Composable
private fun ListaProcesos(estado: EstadoProcesos) {
    val movil = movil()
    GrupoMovil {
        for (fila in estado.filas) {
            val clave = fila.texto("key")
            val protegida = fila.logico("protected")
            FilaLibre(alPulsar = { estado.elegir(clave) }, activa = !protegida) {
                CasillaMovil(clave in estado.seleccion, !protegida)
                TextosFila(fila.texto("name"), fila.texto("subtitle") + " · " + fila.texto("status"))
                ValorConUnidad(fila.texto("memory", "—"))
                FlechaDetalle {
                    movil.abrirHoja { DetalleProceso(estado.filas.firstOrNull { it.texto("key") == clave } ?: fila) }
                }
            }
        }
        if (estado.filas.isEmpty()) {
            FilaDato(t(if (estado.datos.isEmpty()) "Waiting for process inventory" else "No results"), "")
        }
    }
}

@Composable
private fun OpcionesProcesos(estado: EstadoProcesos) {
    TituloHoja(t("Sort and selection"))
    GrupoMovil {
        TiraAcciones(
            AccionTira(t("Select visible"), estado.filas.any { !it.logico("protected") }) {
                estado.seleccion = estado.filas.filter { !it.logico("protected") }.map { it.texto("key") }.toSet()
            },
            AccionTira(t("Clear selection"), estado.seleccion.isNotEmpty()) { estado.seleccion = emptySet() },
        )
    }
    SeccionMovil(t("Sort by")) {
        GrupoMovil {
            for (clave in listOf("name", "cpu", "gpu", "memory", "vram")) {
                FilaRadio(t(ordenProceso(clave)), estado.orden == clave) {
                    estado.descendente = if (estado.orden == clave) !estado.descendente else clave != "name"
                    estado.orden = clave
                }
            }
            FilaInterruptor(t("Descending"), estado.descendente) { estado.descendente = it }
        }
    }
    BotonMovil(t("Refresh"), Modifier.fillMaxWidth()) { estado.recarga++ }
    CerrarHoja()
}

private fun vistasDeProcesos(): List<Pair<String, String>> {
    return listOf("apps" to "Apps and games", "background" to "Background", "system" to "System", "all" to "All")
        .map { (clave, nombre) -> clave to t(nombre) }
}

private fun ordenProceso(clave: String): String = when (clave) {
    "name" -> "Application"
    "cpu" -> "CPU"
    "gpu" -> "GPU"
    "vram" -> "GPU memory"
    else -> "Memory"
}

@Composable
private fun DetalleProceso(fila: JsonObject) {
    TituloHoja(fila.texto("name"))
    TextoHoja(fila.texto("subtitle"))
    GrupoMovil {
        for (clave in listOf("cpu", "gpu", "memory", "vram")) {
            FilaDato(t(ordenProceso(clave)), fila.texto(if (clave == "cpu" || clave == "gpu") clave + "_text" else clave, "—"))
        }
        FilaDato(t("Status"), fila.texto("status"))
    }
    for (clave in listOf("memory_hint", "vram_hint", "detail")) {
        if (fila.texto(clave).isNotEmpty()) TextoHoja(fila.texto(clave))
    }
    CerrarHoja()
}

@Composable
private fun JuegoMovil(aplicacion: Aplicacion, juego: JsonObject, oomd: Boolean, libre: Boolean) {
    GrupoMovil {
        FilaDato(t("Playing now"), juego.texto("name"))
        FilaDato("CPU · GPU", "${juego.texto("cpu", "—")} % · ${juego.texto("gpu", "—")} %")
        FilaDato(t("Memory"), juego.texto("memory"))
        FilaDato(t("GPU memory"), juego.texto("vram"))
        TiraAcciones(
            AccionTira(t(if (juego.logico("paused")) "Resume game" else "Pause game"), libre && !juego.logico("protected")) {
                actuarProcesos(aplicacion, listOf(juego), if (juego.logico("paused")) "resume" else "pause")
            },
            AccionTira(t("Close game"), libre && !juego.logico("protected")) { actuarProcesos(aplicacion, listOf(juego), "end") },
        )
    }
    if (oomd && juego.logico("paused")) {
        NotaMovil(t("systemd-oomd is running: if the paused game's memory goes to swap, " +
            "it may close the game and Steam with it."), ColoresActuales.current.naranja)
    }
}
