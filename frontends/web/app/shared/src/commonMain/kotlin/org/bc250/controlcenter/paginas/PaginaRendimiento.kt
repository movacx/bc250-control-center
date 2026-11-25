package org.bc250.controlcenter.paginas

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonNull
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

/** Cada pestaña conserva su vista y escala mientras llegan muestras. */
@Composable
fun PaginaRendimiento(aplicacion: Aplicacion) {
    var pestaña by remember { mutableStateOf("sensors") }
    val vistas = remember { mutableStateMapOf<String, String>() }
    val escalas = remember { mutableStateMapOf<String, String>() }
    var ventana by remember { mutableIntStateOf(120) }
    var tipos by remember { mutableStateOf<Set<Int>>(emptySet()) }
    var buscar by remember { mutableStateOf("") }
    var ocultar by remember { mutableStateOf(true) }
    var marcados by remember { mutableStateOf<Set<String>?>(null) }
    var distribucion by remember { mutableStateOf("split") }
    var datos by remember { mutableStateOf(ObjetoVacio) }
    var fallo by remember { mutableStateOf(false) }
    var preferenciasLeidas by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        aplicacion.leerPagina("performance")
        val preferencias = aplicacion.lectura("performance").objeto("preferences")
        if (preferencias.isNotEmpty()) {
            distribucion = preferencias.texto("layout", "split")
            ocultar = preferencias.logico("hide", true)
            ventana = preferencias.entero("window", 120)
            tipos = preferencias.textos("kinds").mapNotNull { it.toIntOrNull() }.toSet()
            if (preferencias["ticked"] != null && preferencias["ticked"] != JsonNull) {
                marcados = preferencias.textos("ticked").toSet()
            }
        }
        preferenciasLeidas = true
    }
    LaunchedEffect(preferenciasLeidas, distribucion, ocultar, ventana, tipos, marcados) {
        if (preferenciasLeidas && aplicacion.puedeControlar) {
            delay(250)
            aplicacion.guardar("performance.preferences", mapOf(
                "layout" to JsonPrimitive(distribucion), "hide" to JsonPrimitive(ocultar),
                "window" to JsonPrimitive(ventana), "kinds" to JsonArray(tipos.sorted().map(::JsonPrimitive)),
                "ticked" to (marcados?.let { claves -> JsonArray(claves.sorted().map(::JsonPrimitive)) } ?: JsonNull),
            ), "performance")
        }
    }
    val vista = vistas[pestaña] ?: pestaña
    val escala = escalas[pestaña] ?: "auto"
    LaunchedEffect(pestaña, vista, escala, ventana, tipos, buscar, ocultar, marcados) {
        while (true) {
            val parametros = mutableMapOf("tab" to pestaña, "view" to vista, "scale" to escala,
                "window" to ventana.toString(), "kinds" to tipos.sorted().joinToString(","), "q" to buscar,
                "hide" to if (ocultar) "1" else "0")
            if (marcados != null) parametros["ticked"] = marcados!!.joinToString(",")
            val respuesta = aplicacion.consultar("performance", parametros)
            fallo = respuesta.isEmpty()
            if (!fallo) datos = respuesta
            delay(1000)
        }
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
        .padding(start = M.margenHorizontal, top = M.margenSuperior, end = M.margenHorizontal, bottom = 24.dp)) {
        val paleta = ColoresActuales.current
        Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, Medidas.radioTarjeta).padding(1.dp).padding(18.dp, 14.dp),
            Arrangement.spacedBy(10.dp)) {
            PestañasRendimiento(datos, pestaña, vista, distribucion, ventana,
                { nueva -> pestaña = nueva }, { vistas[pestaña] = it },
                { distribucion = it }, { ventana = it })
            if (fallo) Leyenda(t("Waiting for data…"))
            if (datos.texto("error").isNotEmpty()) Leyenda(datos.texto("error"))
            if (datos.isEmpty() || datos.logico("waiting")) {
                Leyenda(t("Waiting for first sample"))
            } else if (pestaña == "sensors") {
                SensoresRendimiento(aplicacion, datos, buscar, { buscar = it.take(160) }, tipos,
                    { indice ->
                        tipos = if (indice == 0) emptySet() else if (indice in tipos) tipos - indice else tipos + indice
                    }, ocultar, { ocultar = it }, distribucion, { distribucion = it },
                    ventana, { ventana = it }) { clave ->
                    val actuales = marcados ?: datos.textos("ticked").toSet()
                    marcados = if (clave in actuales) actuales - clave else actuales + clave
                }
            } else {
                RecursoRendimiento(datos, vista, { vistas[pestaña] = it }, escala,
                    { escalas[pestaña] = it }, ventana, { ventana = it })
            }
        }
    }
}

@Composable
internal fun VentanaRendimiento(ventana: Int, alCambiar: (Int) -> Unit, modifier: Modifier = Modifier) {
    val opciones = listOf(60, 120, 300, 600, 1800).map { segundos ->
        Eleccion(segundos.toString(), "${segundos / 60} min")
    }
    FilaEleccion(t("History window"), opciones, ventana.toString(), { alCambiar(it.toInt()) }, modifier)
}

@Composable
private fun RecursoRendimiento(
    datos: JsonObject, vista: String, alVista: (String) -> Unit,
    escala: String, alEscala: (String) -> Unit, ventana: Int, alVentana: (Int) -> Unit,
) {
    Texto(datos.texto("title"), tamano = 18, peso = 850)
    Leyenda(datos.texto("hint"))
    Texto(datos.texto("primary", "--"), tamano = 20, peso = 860)
    Leyenda(datos.texto("context"))
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < M.anchoMovil) {
            Column(verticalArrangement = Arrangement.spacedBy(Medidas.espacioCorto)) {
                EscalaRendimiento(datos.logico("percent"), escala, alEscala)
                VentanaRendimiento(ventana, alVentana)
            }
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(Medidas.espacio)) {
                EscalaRendimiento(datos.logico("percent"), escala, alEscala, Modifier.weight(1f))
                VentanaRendimiento(ventana, alVentana, Modifier.weight(1f))
            }
        }
    }
    GraficaPanelRendimiento(datos.objeto("chart"), ventana)
    for (serie in datos.objetos("legend")) {
        Leyenda("${serie.texto("name")}  ·  ${t("Min")} ${serie.texto("min")}  ·  ${t("Avg")} ${serie.texto("avg")}  ·  ${t("Max")} ${serie.texto("max")}")
    }
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(10.dp)) {
        for (tarjeta in datos.objetos("cards")) {
            TarjetaLectura(tarjeta.texto("label"), tarjeta.texto("value"), Modifier.width(220.dp))
        }
    }
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(12.dp)) {
        Leyenda(t(if (datos.texto("error").isEmpty()) "Sampling" else "Read error"))
        if (ventana == 120) Leyenda(t("120 samples · 1 s cadence · 2 minute window"))
        Leyenda(t("Last sample {time}", "time" to datos.texto("sampled", "--:--:--")))
    }
}

@Composable
private fun EscalaRendimiento(porcentaje: Boolean, escala: String, alCambiar: (String) -> Unit, modifier: Modifier = Modifier) {
    FilaEleccion(t("Scale"), listOf(Eleccion("auto", t("Auto")), Eleccion("fixed", "0–100%")),
        escala, alCambiar, modifier, activa = porcentaje)
}
