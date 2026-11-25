package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** Sólo conserva lo que dibuja el navegador; las decisiones las toma el servidor. */
internal class EstadoExtras(val aplicacion: Aplicacion, private val tareas: CoroutineScope) {
    var dialogo by mutableStateOf<JsonObject?>(null)
    var solicitud by mutableStateOf(ObjetoVacio)
    var detalle by mutableStateOf<JsonObject?>(null)

    fun abrir(pestana: String, fila: JsonObject, operacion: JsonObject) {
        solicitud = JsonObject(mapOf(
            "tab" to JsonPrimitive(pestana),
            "row" to JsonPrimitive(fila.texto("id")),
            "operation" to JsonPrimitive(operacion.texto("id")),
            "answers" to JsonArray(emptyList()),
        ))
        pedir()
    }

    fun elegir(respuesta: JsonElement) {
        val anteriores = solicitud["answers"] as? JsonArray ?: JsonArray(emptyList())
        solicitud = JsonObject(solicitud + ("answers" to JsonArray(anteriores + respuesta)))
        pedir()
    }

    private fun pedir() {
        dialogo = JsonObject(mapOf("kind" to JsonPrimitive("loading")))
        val enviada = solicitud
        tareas.launch {
            val respuesta = aplicacion.consultar("extras.dialog", mapOf("request" to enviada.toString()))
            if (solicitud == enviada && dialogo != null) {
                dialogo = respuesta
            }
        }
    }

    /** Abre la única operación de una fila con la primera respuesta ya elegida. */
    fun abrirConRespuesta(pestana: String, fila: JsonObject, respuesta: JsonElement) {
        val operacion = fila.objetos("actions").firstOrNull() ?: return
        solicitud = JsonObject(mapOf(
            "tab" to JsonPrimitive(pestana),
            "row" to JsonPrimitive(fila.texto("id")),
            "operation" to JsonPrimitive(operacion.texto("id")),
            "answers" to JsonArray(listOf(respuesta)),
        ))
        pedir()
    }

    /** El diálogo ya preguntó: la operación sale directo a la consola. */
    fun ejecutarConfirmado() {
        val pregunta = dialogo ?: return
        val titulo = t(pregunta.texto("title", t("Additional settings")))
        aplicacion.ejecutar("extras.run", titulo, solicitud, confirmada = true)
        dialogo = null
    }
}

@Composable
fun PaginaAjustesAdicionales(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val estado = remember(aplicacion) { EstadoExtras(aplicacion, tareas) }
    var pestana by remember { mutableStateOf("compatibility") }
    LaunchedEffect(aplicacion.partePedida) {
        if (aplicacion.partePedida.isNotEmpty() && aplicacion.pagina == "extras") {
            pestana = aplicacion.partePedida
            aplicacion.partePedida = ""
        }
    }
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("extras")
            delay(6000)
        }
    }
    val datos = aplicacion.lectura("extras")
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 24.dp),
        ) {
            Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, Medidas.radioTarjeta).padding(1.dp)) {
                Column(Modifier.fillMaxWidth().height(60.dp).padding(horizontal = 16.dp, vertical = 10.dp), Arrangement.spacedBy(3.dp)) {
                    Texto(t("Additional settings"), tamano = 14, peso = 750)
                    Texto(t("Detected system: {distribution}", "distribution" to datos.texto("system", t("Not detected"))),
                        tamano = 11, color = paleta.apagado)
                }
                PestanasExtras(pestana) { elegida -> pestana = elegida }
                LineaDivisoria()
                Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp), Arrangement.spacedBy(8.dp)) {
                    if (datos.isEmpty()) {
                        Texto(t("Waiting for data…"), tamano = 13, color = paleta.apagado)
                        Boton(t("Retry"), { tareas.launch { aplicacion.leerPagina("extras") } })
                    } else {
                        val paneles = datos.objeto("tabs").objeto(pestana).objetos("panels")
                        when (pestana) {
                            "memory" -> MemoriaExtras(estado, datos, paneles)
                            "upscaling" -> EscaladoExtras(estado, datos, paneles)
                            else -> paneles.forEach { panel -> PanelExtras(estado, pestana, panel) }
                        }
                    }
                }
            }
        }
        DialogosExtras(estado)
    }
}

@Composable
private fun PestanasExtras(elegida: String, alElegir: (String) -> Unit) {
    val nombres = listOf(
        "compatibility" to "Compatibility", "upscaling" to "Upscaling",
        "memory" to "Memory & Swap", "drivers" to "Drivers",
    )
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val estrecha = maxWidth < 700.dp
        val desplazable = if (estrecha) Modifier.horizontalScroll(rememberScrollState()) else Modifier
        Row(Modifier.fillMaxWidth().height(44.dp).then(desplazable).padding(horizontal = 12.dp, vertical = 5.dp), Arrangement.spacedBy(6.dp)) {
            nombres.forEach { (clave, titulo) ->
                val ancho = if (estrecha) Modifier.width(160.dp) else Modifier.weight(1f)
                PestanaPanel(t(titulo), elegida == clave, ancho) { alElegir(clave) }
            }
        }
    }
}
