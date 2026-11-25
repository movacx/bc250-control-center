package org.bc250.controlcenter.movil

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.GraficaPanelRendimiento
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.consultarRendimiento
import org.bc250.controlcenter.paginas.guardarPreferenciasRendimiento
import org.bc250.controlcenter.paginas.reiniciarRendimiento
import org.bc250.controlcenter.paginas.GraficaTraza
import org.bc250.controlcenter.tema.ColoresActuales

private class EstadoRendimiento {
    var pestana by mutableStateOf("sensors")
    val vistas = mutableStateMapOf<String, String>()
    val escalas = mutableStateMapOf<String, String>()
    var ventana by mutableIntStateOf(120)
    var tipos by mutableStateOf(emptySet<Int>())
    var buscar by mutableStateOf("")
    var ocultar by mutableStateOf(true)
    var marcados by mutableStateOf<Set<String>?>(null)
    var distribucion by mutableStateOf("split")
    var leidas by mutableStateOf(false)
    var datos by mutableStateOf(ObjetoVacio)
    var fallo by mutableStateOf(false)
    val vista get() = vistas[pestana] ?: pestana
    val escala get() = escalas[pestana] ?: "auto"

    fun alternarTipo(indice: Int) {
        tipos = when (indice) {
            0 -> emptySet()
            in tipos -> tipos - indice
            else -> tipos + indice
        }
    }

    fun marcar(clave: String) {
        val actuales = marcados ?: datos.textos("ticked").toSet()
        marcados = if (clave in actuales) actuales - clave else actuales + clave
    }
}

@Composable
fun PaginaRendimientoMovil(aplicacion: Aplicacion) {
    val estado = remember { EstadoRendimiento() }
    LecturasRendimiento(aplicacion, estado)
    PaginaMovil("performance") {
        PestanasRendimiento(estado)
        EstadoLecturaMovil(estado.datos)
        if (estado.fallo) NotaMovil(t("Waiting for data…"))
        if (estado.datos.logico("waiting")) NotaMovil(t("Waiting for first sample"))
        if (estado.pestana == "sensors") SensoresMovil(aplicacion, estado) else RecursoMovil(estado)
    }
}

@Composable
private fun LecturasRendimiento(aplicacion: Aplicacion, estado: EstadoRendimiento) {
    LaunchedEffect(Unit) {
        aplicacion.leerPagina("performance")
        val preferencias = aplicacion.lectura("performance").objeto("preferences")
        if (preferencias.isNotEmpty()) {
            estado.distribucion = preferencias.texto("layout", "split")
            estado.ocultar = preferencias.logico("hide", true)
            estado.ventana = preferencias.entero("window", 120)
            estado.tipos = preferencias.textos("kinds").mapNotNull { it.toIntOrNull() }.toSet()
            if (preferencias["ticked"] != null && preferencias["ticked"] != JsonNull) {
                estado.marcados = preferencias.textos("ticked").toSet()
            }
        }
        estado.leidas = true
    }
    LaunchedEffect(estado.leidas, estado.distribucion, estado.ocultar, estado.ventana, estado.tipos, estado.marcados) {
        if (estado.leidas && aplicacion.puedeControlar) {
            delay(250)
            guardarPreferenciasRendimiento(aplicacion, estado.distribucion, estado.ocultar,
                estado.ventana, estado.tipos, estado.marcados)
        }
    }
    LaunchedEffect(estado.pestana, estado.vista, estado.escala, estado.ventana,
        estado.tipos, estado.buscar, estado.ocultar, estado.marcados) {
        while (true) {
            val respuesta = consultarRendimiento(aplicacion, estado.pestana, estado.vista, estado.escala,
                estado.ventana, estado.tipos, estado.buscar, estado.ocultar, estado.marcados)
            estado.fallo = respuesta.isEmpty()
            if (!estado.fallo) estado.datos = respuesta
            delay(1000)
        }
    }
}

@Composable
private fun PestanasRendimiento(estado: EstadoRendimiento) {
    val iniciales = listOf("sensors" to "Sensors", "cpu" to "CPU", "gpu" to "GPU", "vram" to "VRAM",
        "memory" to "RAM", "disk" to "Disk", "network" to "Network")
    val opciones = estado.datos.objetos("tabs").map { it.texto("key") to it.texto("title") }.ifEmpty {
        iniciales.map { it.first to t(it.second) }
    }
    FilaOpciones(opciones, setOf(estado.pestana)) { clave -> estado.pestana = clave }
}

/** La fila que abre las vistas, la ventana de tiempo y la escala. */
@Composable
private fun FilaVistas(estado: EstadoRendimiento) {
    val movil = movil()
    GrupoMovil {
        FilaAbrir(t("Views"), valor = "${estado.ventana / 60} min") {
            movil.abrirHoja { OpcionesRendimiento(estado) }
        }
    }
}

@Composable
private fun SensoresMovil(aplicacion: Aplicacion, estado: EstadoRendimiento) {
    val plegados = remember { mutableStateMapOf<String, Boolean>() }
    CampoMovil(estado.buscar, Modifier.fillMaxWidth(), t("Filter by name")) { estado.buscar = it.take(160) }
    val tipos = estado.datos.objetos("kinds").map { tipo -> tipo.texto("index") to tipo.texto("title") }
    val elegidos = if (estado.tipos.isEmpty()) setOf("0") else estado.tipos.map { it.toString() }.toSet()
    FilaOpciones(tipos, elegidos) { valor -> estado.alternarTipo(valor.toInt()) }
    if (estado.distribucion != "list") {
        for (traza in estado.datos.objetos("traces")) {
            GrupoMovil {
                FilaDato(traza.texto("label"), traza.texto("value"))
                GraficaTraza(traza.objeto("chart"), estado.ventana,
                    ColoresActuales.current.color(traza.texto("tone")),
                    Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp).height(76.dp))
            }
        }
        for (traza in estado.datos.objetos("missing_traces")) {
            GrupoMovil { FilaDato(traza.texto("label"), t("Waiting for first sample")) }
        }
        if (estado.datos.objetos("traces").isEmpty() && estado.datos.objetos("missing_traces").isEmpty()) {
            NotaMovil(t("Tick a sensor in the list to draw its last two minutes here."))
        }
    }
    if (estado.distribucion != "graphs") {
        GrupoMovil {
            var grupo = ""
            for (fila in estado.datos.objetos("rows")) {
                if (fila.containsKey("group")) {
                    grupo = fila.texto("group")
                    val nombre = grupo
                    FilaLibre(alPulsar = { plegados[nombre] = plegados[nombre] != true }) {
                        TextosFila(nombre)
                        Texto(if (plegados[nombre] == true) "+" else "−", tamano = 16)
                    }
                } else if (plegados[grupo] != true) {
                    FilaSensor(fila, estado)
                }
            }
            FilaInterruptor(t("Hide unused channels"), estado.ocultar) { estado.ocultar = it }
        }
    } else {
        GrupoMovil { FilaInterruptor(t("Hide unused channels"), estado.ocultar) { estado.ocultar = it } }
    }
    FilaVistas(estado)
    BotonMovil(t("Reset min/max"), Modifier.fillMaxWidth(), activo = aplicacion.puedeControlar) {
        reiniciarRendimiento(aplicacion)
    }
}

@Composable
private fun FilaSensor(fila: JsonObject, estado: EstadoRendimiento) {
    val movil = movil()
    FilaLibre(alPulsar = { estado.marcar(fila.texto("key")) }) {
        CasillaMovil(fila.logico("ticked"))
        Box(Modifier.size(8.dp).background(ColoresActuales.current.color(fila.texto("tone"))))
        Texto(fila.texto("label"), tamano = 14, modifier = Modifier.weight(1f))
        ValorConUnidad(fila.texto("value"))
        FlechaDetalle { movil.abrirHoja { EstadisticasSensor(fila, estado) } }
    }
}

@Composable
private fun EstadisticasSensor(original: JsonObject, estado: EstadoRendimiento) {
    val fila = estado.datos.objetos("rows").firstOrNull { it.texto("key") == original.texto("key") } ?: original
    TituloHoja(fila.texto("label"))
    GrupoMovil {
        for (clave in listOf("value", "min", "avg", "max")) {
            FilaDato(t(clave.replaceFirstChar { it.uppercase() }), fila.texto(clave))
        }
        FilaInterruptor(t("Graphs"), fila.texto("key") in (estado.marcados ?: estado.datos.textos("ticked").toSet())) {
            estado.marcar(fila.texto("key"))
        }
    }
    CerrarHoja()
}

@Composable
private fun RecursoMovil(estado: EstadoRendimiento) {
    val datos = estado.datos
    GrupoMovil {
        val principal = datos.texto("primary", "--")
        TituloLectura(datos.texto("title"), principal.substringBefore(" "), principal.substringAfter(" ", ""))
        GraficaPanelRendimiento(datos.objeto("chart"), estado.ventana, 200.dp, Modifier.padding(14.dp))
    }
    val series = datos.objetos("legend")
    for (serie in series) {
        SeccionMovil(if (series.size > 1) serie.texto("name") else t("Statistics")) {
            GrupoMovil {
                for (clave in listOf("min", "avg", "max")) {
                    FilaDato(t(clave.replaceFirstChar { it.uppercase() }), serie.texto(clave))
                }
            }
        }
    }
    if (datos.objetos("cards").isNotEmpty()) {
        GrupoMovil {
            for (tarjeta in datos.objetos("cards")) {
                FilaDato(tarjeta.texto("label"), tarjeta.texto("value"))
            }
        }
    }
    FilaVistas(estado)
    if (datos.texto("error").isNotEmpty()) NotaMovil(t("Read error"), ColoresActuales.current.naranja)
}

@Composable
private fun OpcionesRendimiento(estado: EstadoRendimiento) {
    TituloHoja(t("Views"))
    GrupoMovil {
        val sensores = estado.pestana == "sensors"
        for (opcion in estado.datos.objetos(if (sensores) "layouts" else "views")) {
            val clave = opcion.texto("key")
            FilaRadio(opcion.texto("title"), clave == if (sensores) estado.distribucion else estado.vista,
                detalle = opcion.texto("hint"), activa = sensores || opcion.logico("available")) {
                if (sensores) estado.distribucion = clave else estado.vistas[estado.pestana] = clave
            }
        }
    }
    SeccionMovil(t("History window")) {
        GrupoMovil {
            for (segundos in listOf(60, 120, 300, 600, 1800)) {
                FilaRadio("${segundos / 60} min", estado.ventana == segundos) { estado.ventana = segundos }
            }
        }
    }
    if (estado.pestana != "sensors") {
        SeccionMovil(t("Scale")) {
            GrupoMovil {
                for ((clave, nombre) in listOf("auto" to t("Auto"), "fixed" to "0–100%")) {
                    FilaRadio(nombre, estado.escala == clave, activa = estado.datos.logico("percent")) {
                        estado.escalas[estado.pestana] = clave
                    }
                }
            }
        }
    }
    CerrarHoja()
}

