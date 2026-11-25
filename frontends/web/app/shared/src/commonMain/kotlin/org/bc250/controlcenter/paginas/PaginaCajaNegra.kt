package org.bc250.controlcenter.paginas

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasSupervision

@Composable
fun PaginaCajaNegra(aplicacion: Aplicacion) {
    var diagnostico by remember { mutableStateOf(false) }
    var carpeta by remember { mutableStateOf(false) }
    var primeraLectura by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("black_box")
            primeraLectura = true
            delay(1000)
        }
    }
    val datos = aplicacion.lectura("black_box")
    val inicio = datos.objeto("autostart")
    val disponible = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    MarcoSupervision { alto ->
        Column(Modifier.padding(bottom = 2.dp), verticalArrangement = Arrangement.spacedBy(1.dp)) {
          Texto(t("Black box"), 14, peso = 780)
          Texto(t("Records the GPU clock, load, temperatures, voltage, power, fans, CPU clock and free memory four times a second, so the next problem report shows the seconds before a freeze."),
            12, color = ColoresActuales.current.apagado)
        }
        LineaDivisoria()
        Box(Modifier.fillMaxWidth().heightIn(min = 35.dp), contentAlignment = androidx.compose.ui.Alignment.CenterStart) {
          FranjaSupervision(izquierda = {
            val grabando = datos.logico("running")
            BotonRegistro(t(if (grabando) "Stop recording" else "Start recording"), disponible && datos.logico("supported")) {
                controlarCajaNegra(aplicacion, if (grabando) "stop" else "start")
            }
            BotonRegistro(t("Open folder")) { carpeta = true }
            BotonRegistro(t(if (diagnostico) "Back to the recording" else "View full diagnosis")) { diagnostico = !diagnostico }
        }, derecha = {
            if (inicio.logico("supported")) {
                CasillaSupervision(t("Start with the session"), inicio.logico("enabled"), disponible && !inicio.logico("foreign"), interruptor = true) {
                    controlarCajaNegra(aplicacion, "autostart", it)
                }
            }
          })
        }
        if (diagnostico) {
            DiagnosticoCajaNegra(aplicacion, (alto - 200.dp).coerceAtLeast(420.dp))
        } else {
            Texto(datos.texto("message", t(if (primeraLectura) "Not connected" else "Waiting for data…")), 12,
                color = if (datos.texto("state") == "cut-off") ColoresActuales.current.naranja else ColoresActuales.current.apagado)
            LineaDivisoria()
            TablaCajaNegra(datos, (alto - 250.dp).coerceAtLeast(300.dp))
        }
    }
    if (carpeta) {
        // El navegador no tiene acceso al explorador del equipo remoto. Se abre
        // el registro completo como documento seleccionable del dispositivo cliente.
        DocumentoSupervision(
            t("Black box"), textoRegistroCajaNegra(datos),
            aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=recording",
        ) { carpeta = false }
    }
}

internal fun controlarCajaNegra(aplicacion: Aplicacion, operacion: String, habilitar: Boolean = false) {
    val parametros = mutableMapOf<String, JsonElement>("operation" to JsonPrimitive(operacion))
    if (operacion == "autostart") parametros["enabled"] = JsonPrimitive(habilitar)
    val titulo = t(when (operacion) { "start" -> "Start recording"; "stop" -> "Stop recording"; else -> "Start with the session" })
    aplicacion.preguntarYEjecutar("black_box.control", titulo, parametros = parametros)
}

@Composable
private fun TablaCajaNegra(datos: JsonObject, alto: androidx.compose.ui.unit.Dp) {
    val desplazamiento = rememberLazyListState()
    var filas by remember { mutableStateOf(emptyList<JsonObject>()) }
    val nuevas = datos.objetos("rows")
    val siguiendo = desplazamiento.firstVisibleItemIndex == 0 && desplazamiento.firstVisibleItemScrollOffset == 0
    LaunchedEffect(nuevas, siguiendo) {
        if (siguiendo) filas = nuevas
    }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      BoxWithConstraints(Modifier.fillMaxWidth()) {
        val ancho = maxWidth.coerceAtLeast(1150.dp)
        val columnas = datos.objetos("columns")
        Column(Modifier.horizontalScroll(rememberScrollState()).width(ancho)) {
            Row(Modifier.height(MedidasSupervision.cabeceraTabla)) {
                for (columna in columnas) {
                    Texto(columna.texto("label").uppercase(), 10, Modifier.weight(1f).align(Alignment.CenterVertically),
                        peso = 800, color = ColoresActuales.current.apagado, alineado = TextAlign.Center)
                }
            }
            LineaDivisoria(color = ColoresActuales.current.borde)
            LazyColumn(Modifier.height(alto).fillMaxWidth(), state = desplazamiento) {
                items(filas) { fila ->
                    FilaRegistro(fila, columnas)
                }
            }
        }
      }
    if (!siguiendo) Texto(t("Paused while you read. Go back to the top to follow the recording."), 12, color = ColoresActuales.current.apagado)
      Texto(t("{count} rows shown · {path}", "count" to filas.size.toString(), "path" to t("Black box")), 11, color = ColoresActuales.current.apagado)
    }
}

@Composable
private fun FilaRegistro(fila: JsonObject, columnas: List<JsonObject>) {
    Column(Modifier.height(MedidasSupervision.filaRegistro).fillMaxWidth()) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            for (columna in columnas) {
                val aLaDerecha = !columna.logico("left")
                val alineado = if (aLaDerecha) TextAlign.End else TextAlign.Start
                Texto(fila.texto(columna.texto("key"), "–"), 12, Modifier.weight(1f).padding(horizontal = 9.dp), alineado = alineado)
            }
        }
        LineaDivisoria()
    }
}

@Composable
private fun BotonRegistro(texto: String, activo: Boolean = true, alPulsar: () -> Unit) {
    Boton(texto, alPulsar, clase = ClaseBoton.CONTORNO, activo = activo, alto = 33.dp, tamano = 12, peso = 650)
}

internal fun textoRegistroCajaNegra(datos: JsonObject): String {
    val columnas = datos.objetos("columns")
    val cabecera = columnas.joinToString("\t") { it.texto("label") }
    val claves = columnas.map { it.texto("key") }
    val registro = datos.objetos("rows").joinToString("\n") { fila -> claves.joinToString("\t") { fila.texto(it) } }
    return "$cabecera\n$registro"
}
