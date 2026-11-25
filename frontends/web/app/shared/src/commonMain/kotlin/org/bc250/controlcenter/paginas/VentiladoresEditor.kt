package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales

internal fun JsonObject.conCampo(clave: String, valor: JsonElement): JsonObject = JsonObject(this + (clave to valor))

internal fun curvaInicial(): JsonArray = JsonArray(listOf(
    JsonArray(listOf(JsonPrimitive(40), JsonPrimitive(30))),
    JsonArray(listOf(JsonPrimitive(60), JsonPrimitive(50))),
    JsonArray(listOf(JsonPrimitive(72), JsonPrimitive(75))),
    JsonArray(listOf(JsonPrimitive(82), JsonPrimitive(100))),
))

private fun cambiarModo(entrada: JsonObject, modo: String): JsonObject {
    val campos = entrada.toMutableMap()
    campos["mode"] = JsonPrimitive(modo)
    val predeterminados = mapOf<String, JsonElement>(
        "role" to JsonPrimitive("fan"), "stall_detect" to JsonPrimitive(true),
        "percent" to JsonPrimitive(60), "source" to JsonPrimitive("hottest"),
        "points" to curvaInicial(), "mix" to JsonArray(listOf(
        buildJsonObject { put("source", JsonPrimitive("gpu")); put("points", curvaInicial()) },
        buildJsonObject { put("source", JsonPrimitive("vrm")); put("points", curvaInicial()) },
    )),
    )
    for ((clave, valor) in predeterminados) {
        if (clave !in campos) campos[clave] = valor
    }
    return JsonObject(campos)
}

/** Solo las claves del modo elegido viajan al motor que valida en el servidor. */
private fun entradaDelEditor(entrada: JsonObject): JsonObject {
    val modo = entrada.texto("mode", "firmware")
    val claves = when (modo) {
        "firmware" -> setOf("mode")
        "fixed" -> setOf("mode", "role", "percent", "preset", "stall_detect")
        else -> setOf("mode", "role", "stall_detect", "min_percent", "max_percent", "hysteresis_c", "response_delay_seconds",
            "max_up_step_percent", "max_down_step_percent", "start_percent", "deadband_percent") +
            if (modo == "curve") setOf("source", "points") else setOf("mix")
    }
    return JsonObject(entrada.filterKeys { it in claves })
}

@Composable
internal fun EditorVentilador(aplicacion: Aplicacion, canal: JsonObject, datos: JsonObject, disponible: Boolean,
    alto: Dp, alCambiar: (JsonObject, Boolean, String) -> Unit) {
    val numero = canal.entero("pwm")
    val guardada = canal.objeto("entry")
    var entrada by remember(numero) { mutableStateOf(cambiarModo(guardada, guardada.texto("mode", "firmware"))) }
    var nombre by remember(numero) { mutableStateOf(canal.texto("label")) }
    var avanzadas by remember(numero) { mutableStateOf(false) }
    var ultimoIntento by remember(numero) { mutableStateOf(-1) }
    var reintentar by remember(numero) { mutableStateOf(false) }
    var miembro by remember(numero) { mutableStateOf(0) }
    var validacion by remember { mutableStateOf(ObjetoVacio) }
    val enviada = entradaDelEditor(entrada)
    val normalizada = if (validacion.objeto("entry").isEmpty()) enviada else validacion.objeto("entry")
    val sucio = normalizada != guardada || nombre != canal.texto("label")
    LaunchedEffect(numero, enviada, nombre, sucio) { alCambiar(enviada, sucio, nombre) }
    LaunchedEffect(numero, enviada) {
        validacion = ObjetoVacio
        delay(180)
        validacion = aplicacion.consultar("fans.validate", mapOf("entry" to enviada.toString()))
        if (validacion.isEmpty()) validacion = buildJsonObject { put("error", JsonPrimitive(t("Not connected"))) }
    }
    LaunchedEffect(numero, guardada) {
        if (!sucio || normalizada == guardada) entrada = cambiarModo(guardada, guardada.texto("mode", "firmware"))
    }
    LaunchedEffect(aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (ultimoIntento >= 0 && aplicacion.trabajo.id > ultimoIntento && aplicacion.trabajo.terminado && aplicacion.trabajo.titulo == t("Apply")) {
            reintentar = !aplicacion.trabajo.correcto
        }
    }
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth().height(alto).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
      Column(Modifier.fillMaxWidth().weight(1f).marco(paleta.panelAlterno, paleta.bordeSuave, 8.dp).padding(16.dp),
          verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Texto(canal.texto("label").ifEmpty { canal.texto("header") }, 14, peso = 800)
        Texto("PWM $numero · ${canal.texto("header")} · ${canal.texto("rpm", "—")} RPM · ${canal.texto("duty", "—")} %", 11, color = paleta.apagado)
        LineaDivisoria()
        Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Texto(t("Name"), 12, Modifier.width(92.dp).padding(top = 5.dp), color = paleta.apagado)
                CampoTexto(nombre, { nombre = it.take(40) }, Modifier.weight(1f).height(27.dp), ayuda = t("Name this fan"), activo = disponible)
            }
            SelectorVentilador(t("Mode"), listOf(Eleccion("firmware", t("Firmware")), Eleccion("fixed", t("Fixed")),
                Eleccion("curve", t("Curve")), Eleccion("mix", t("Mix"))), entrada.texto("mode"),
                { entrada = cambiarModo(entrada, it) }, disponible = disponible)
            val modo = entrada.texto("mode")
            if (modo == "firmware") {
                Texto(t("The BIOS fan curve drives this header. BC250 Control Center does not write to it."), 12, color = paleta.apagado)
            } else {
                SelectorVentilador(t("Role"), listOf(Eleccion("fan", t("Fan")), Eleccion("pump", t("Pump"))), entrada.texto("role", "fan"), {
                    entrada = entrada.conCampo("role", JsonPrimitive(it))
                    if (it == "pump") entrada = entrada.conCampo("min_percent", JsonPrimitive(50))
                }, disponible = disponible)
                if (modo == "fixed") {
                    VelocidadVentilador(entrada.entero("percent", 60), disponible) {
                        entrada = entrada.conCampo("percent", JsonPrimitive(it))
                    }
                    HerramientasSupervision {
                        for (perfil in datos.objetos("speed_profiles")) {
                            AccionSupervision("${perfil.entero("percent")} %", disponible) {
                                entrada = entrada.conCampo("percent", perfil["percent"] ?: JsonPrimitive(60))
                            }
                        }
                    }
                }
                if (modo == "curve") {
                    FuenteVentilador(entrada.texto("source", "hottest"), disponible) {
                        entrada = entrada.conCampo("source", JsonPrimitive(it))
                    }
                    PuntosVentilador(entrada["points"] as? JsonArray ?: curvaInicial(), disponible,
                        datos.objeto("temperatures").numero(entrada.texto("source", "hottest")), canal.numero("duty")) {
                        entrada = entrada.conCampo("points", it)
                    }
                }
                if (modo == "mix") {
                    val miembros = entrada.objetos("mix")
                    val indice = miembro.coerceIn(0, (miembros.size - 1).coerceAtLeast(0))
                    val actual = miembros.getOrNull(indice) ?: ObjetoVacio
                    FilaEleccion(t("Curve"), miembros.mapIndexed { i, fila -> Eleccion(i.toString(), "${i + 1} · ${fila.texto("source")}") },
                        indice.toString(), { miembro = it.toIntOrNull() ?: 0 })
                    HerramientasSupervision {
                        AccionSupervision(t("Add curve"), disponible && miembros.size < 4) {
                            val nueva = buildJsonObject { put("source", JsonPrimitive("cpu")); put("points", curvaInicial()) }
                            entrada = entrada.conCampo("mix", JsonArray(miembros + nueva))
                            miembro = miembros.size
                        }
                        AccionSupervision(t("Remove curve"), disponible && miembros.size > 2) {
                            entrada = entrada.conCampo("mix", JsonArray(miembros.filterIndexed { i, _ -> i != indice }))
                            miembro = 0
                        }
                    }
                    FuenteVentilador(actual.texto("source", "gpu"), disponible) {
                        val nuevos = miembros.toMutableList()
                        nuevos[indice] = actual.conCampo("source", JsonPrimitive(it))
                        entrada = entrada.conCampo("mix", JsonArray(nuevos))
                    }
                    PuntosVentilador(actual["points"] as? JsonArray ?: curvaInicial(), disponible,
                        datos.objeto("temperatures").numero(actual.texto("source")), canal.numero("duty")) {
                        val nuevos = miembros.toMutableList()
                        nuevos[indice] = actual.conCampo("points", it)
                        entrada = entrada.conCampo("mix", JsonArray(nuevos))
                    }
                }
                HerramientasSupervision {
                    CasillaSupervision(t("Advanced"), avanzadas) { avanzadas = it }
                    val calibrando = !aplicacion.trabajo.terminado && aplicacion.trabajo.titulo == t("Calibrate this fan")
                    AccionSupervision(t(if (calibrando) "Cancel" else "Calibrate"), calibrando ||
                        (disponible && canal.logico("writable") && entrada.texto("role") != "pump")) {
                        if (calibrando) aplicacion.interrumpirTrabajo()
                        else aplicacion.preguntarYEjecutar("fans.calibrate", t("Calibrate this fan"),
                            t("The fan goes to full speed, then down step by step until it stops, then up until it starts again. It takes one to two minutes and stops at once if the board reaches 80 °C. It ends at full speed; nothing is saved until you press Apply."),
                            mapOf("pwm" to JsonPrimitive(numero)), peligro = true)
                    }
                }
                val calibracion = datos.objeto("calibration")
                if (calibracion.entero("pwm") == numero && calibracion.texto("aborted").isEmpty() && calibracion.isNotEmpty()) {
                    AccionSupervision(t("Calibration finished"), disponible) {
                        entrada = cambiarModo(entrada, "curve")
                            .conCampo("min_percent", JsonPrimitive(calibracion.entero("proposed_min")))
                            .conCampo("start_percent", JsonPrimitive(calibracion.entero("proposed_start")))
                        avanzadas = true
                    }
                }
                if (avanzadas) {
                    if (modo != "fixed") {
                        for ((clave, titulo, defecto) in listOf(Triple("min_percent", "Minimum PWM", 0), Triple("max_percent", "Maximum PWM", 100),
                            Triple("max_up_step_percent", "Largest step up", 100), Triple("max_down_step_percent", "Largest step down", 10),
                            Triple("start_percent", "Spin-up kick", 0))) {
                            NumeroVentilador(t(titulo), entrada.entero(clave, defecto), if (clave in listOf("max_up_step_percent", "max_down_step_percent")) 1 else 0, 100, "%", disponible) {
                                entrada = entrada.conCampo(clave, JsonPrimitive(it))
                            }
                        }
                        DecimalVentilador(t("Hysteresis"), entrada.numero("hysteresis_c") ?: 1.0, 10.0, disponible) {
                            entrada = entrada.conCampo("hysteresis_c", JsonPrimitive(it))
                        }
                        DecimalVentilador(t("Response delay"), entrada.numero("response_delay_seconds") ?: 0.0, 30.0, disponible) {
                            entrada = entrada.conCampo("response_delay_seconds", JsonPrimitive(it))
                        }
                    }
                    CasillaSupervision(t("Warn when the fan stops while it should turn"), entrada.logico("stall_detect", true), disponible) {
                        entrada = entrada.conCampo("stall_detect", JsonPrimitive(it))
                    }
                }
            }
            if (validacion.texto("error").isNotEmpty()) Texto(validacion.texto("error"), 12, color = paleta.rojo)
            if (canal.texto("fault").isNotEmpty()) Texto(canal.texto("fault"), 12, color = paleta.naranja)
        }
      }
        Row(Modifier.fillMaxWidth().padding(end = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp, androidx.compose.ui.Alignment.End)) {
            AccionSupervision(t("Revert"), sucio) {
                entrada = cambiarModo(guardada, guardada.texto("mode", "firmware"))
                nombre = canal.texto("label")
            }
            val reanudar = canal.logico("resume") && !sucio
            val textoAplicar = t(if (reanudar) "Resume" else if (reintentar && !sucio) "Retry" else "Apply")
            AccionSupervision(textoAplicar, disponible && numero > 0 && (sucio || reintentar || reanudar) && validacion.logico("valid"), primaria = true) {
                ultimoIntento = aplicacion.trabajo.id
                val velocidadBaja = enviada.texto("mode") == "fixed" && enviada.entero("percent") < datos.entero("low_duty", 30)
                aplicacion.preguntarYEjecutar("fans.apply", t("Apply"),
                    mensaje = if (velocidadBaja) t("A fan this slow can let the board overheat under load.") else textoAplicar,
                    parametros = mapOf(
                    "pwm" to JsonPrimitive(numero), "entry" to enviada, "label" to JsonPrimitive(nombre),
                    "force" to JsonPrimitive(reintentar || reanudar)),
                    peligro = velocidadBaja)
            }
        }
    }
}

@Composable
internal fun FuenteVentilador(fuente: String, disponible: Boolean, alElegir: (String) -> Unit) {
    SelectorVentilador(t("Follows"), listOf(Eleccion("hottest", t("Hottest chip")), Eleccion("gpu", "GPU"), Eleccion("cpu", "CPU"),
        Eleccion("vrm", "VRM"), Eleccion("board", t("Board"))), fuente, alElegir, disponible = disponible)
}

@Composable
internal fun NumeroVentilador(titulo: String, valor: Int, minimo: Int, maximo: Int, unidad: String,
    disponible: Boolean, alCambiar: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Texto(titulo, 12, Modifier.weight(1f).padding(top = 12.dp), color = ColoresActuales.current.apagado)
        CampoNumero(valor, alCambiar, minimo, maximo, Modifier.width(120.dp), sufijo = unidad, activo = disponible)
    }
}

@Composable
private fun DecimalVentilador(titulo: String, valor: Double, maximo: Double, disponible: Boolean, alCambiar: (Double) -> Unit) {
    var texto by remember { mutableStateOf(valor.toString()) }
    var enfocado by remember { mutableStateOf(false) }
    LaunchedEffect(valor, enfocado) {
        if (!enfocado) texto = valor.toString()
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Texto(titulo, 12, Modifier.weight(1f).padding(top = 12.dp), color = ColoresActuales.current.apagado)
        CampoTexto(texto, {
            texto = it
            val numero = it.toDoubleOrNull()
            if (numero != null && numero.isFinite() && numero in 0.0..maximo) alCambiar(numero)
        }, Modifier.width(120.dp).onFocusChanged { enfocado = it.hasFocus }, activo = disponible)
    }
}

@Composable
private fun SelectorVentilador(titulo: String, opciones: List<Eleccion>, elegido: String,
    alElegir: (String) -> Unit, disponible: Boolean) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Texto(titulo, 12, Modifier.width(92.dp).padding(top = 5.dp), color = ColoresActuales.current.apagado)
        SelectorSupervision(opciones, elegido, disponible, Modifier.weight(1f), alElegir)
    }
}
