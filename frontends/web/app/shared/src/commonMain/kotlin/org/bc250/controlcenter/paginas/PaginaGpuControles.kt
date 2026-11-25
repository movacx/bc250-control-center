package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.input.key.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.style.TextAlign
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.*
import kotlin.math.abs
import kotlin.math.roundToInt

/** Carril con dos extremos: ratón, tacto y teclado recorren los puntos del TOML. */
@Composable
internal fun CarrilGpu(puntos: List<JsonObject>, minimo: Int, maximo: Int, techo: Int,
    activo: Boolean, alCambiar: (Int, Int) -> Unit) {
    val paleta = ColoresActuales.current
    val frecuencias = puntos.map { it.entero("frequency") }.sorted()
    if (frecuencias.isEmpty()) {
        Texto(t("No active voltage safe-points were found. Verify the governor TOML and refresh."), tamano = 13)
        return
    }
    val disponibles = frecuencias.filter { it <= techo }
    var extremo by remember { mutableStateOf("max") }
    fun mover(x: Float, ancho: Float) {
        if (!activo || disponibles.isEmpty()) return
        val proporcion = ((x - 26f) / (ancho - 52f).coerceAtLeast(1f)).coerceIn(0f, 1f)
        val indice = (proporcion * (frecuencias.size - 1)).roundToInt()
        val frecuencia = frecuencias[indice].coerceAtMost(techo)
        if (extremo == "min") alCambiar(frecuencia.coerceAtMost(maximo), maximo)
        else alCambiar(minimo, frecuencia.coerceAtLeast(minimo))
    }
    fun posicion(frecuencia: Int, ancho: Float): Float {
        val indice = frecuencias.indices.minByOrNull { abs(frecuencias[it] - frecuencia) } ?: 0
        return 26f + (ancho - 52f) * indice / (frecuencias.size - 1).coerceAtLeast(1)
    }
    val moverActual by rememberUpdatedState<(Float, Float) -> Unit> { x, ancho -> mover(x, ancho) }
    val minimoActual by rememberUpdatedState(minimo)
    val maximoActual by rememberUpdatedState(maximo)
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val ancho = maxWidth
        Column {
            Box(Modifier.fillMaxWidth().height(MedidasGpuCu.altoCarril)) {
            Canvas(Modifier.fillMaxWidth().height(MedidasGpuCu.altoCarril)
                .semantics { contentDescription = "$minimo – $maximo MHz" }
                .onKeyEvent { evento ->
                    if (!activo || evento.type != KeyEventType.KeyDown) false
                    else if (evento.key == Key.Enter || evento.key == Key.Spacebar) {
                        extremo = if (extremo == "min") "max" else "min"
                        true
                    } else if (evento.key == Key.DirectionLeft || evento.key == Key.DirectionRight) {
                        val actual = if (extremo == "min") minimo else maximo
                        val indice = disponibles.indices.minByOrNull { abs(disponibles[it] - actual) } ?: 0
                        val paso = if (evento.key == Key.DirectionRight) 1 else -1
                        val valor = disponibles[(indice + paso).coerceIn(0, disponibles.lastIndex)]
                        if (extremo == "min") alCambiar(valor.coerceAtMost(maximo), maximo)
                        else alCambiar(minimo, valor.coerceAtLeast(minimo))
                        true
                    } else false
                }.focusable(activo)
                .pointerInput(activo, minimo, maximo, techo, frecuencias) {
                    detectTapGestures { punto ->
                        extremo = if (abs(punto.x - posicion(minimoActual, size.width.toFloat())) < abs(punto.x - posicion(maximoActual, size.width.toFloat()))) "min" else "max"
                        moverActual(punto.x, size.width.toFloat())
                    }
                }.pointerInput(activo, techo, frecuencias) {
                    detectDragGestures(onDragStart = { punto ->
                        extremo = if (abs(punto.x - posicion(minimoActual, size.width.toFloat())) < abs(punto.x - posicion(maximoActual, size.width.toFloat()))) "min" else "max"
                    }) { cambio, _ ->
                        cambio.consume()
                        moverActual(cambio.position.x, size.width.toFloat())
                    }
                }) {
                val y = 24.dp.toPx()
                val bajo = posicion(minimo, size.width)
                val alto = posicion(maximo, size.width)
                drawLine(paleta.bordeFuerte, Offset(26f, y), Offset(size.width - 26f, y), 3f)
                drawLine(paleta.acento, Offset(bajo, y), Offset(alto, y), 4f)
                for (frecuencia in frecuencias) {
                    val x = posicion(frecuencia, size.width)
                    drawLine(if (frecuencia > techo) paleta.rojoBorde else paleta.acento,
                        Offset(x, y - 16f), Offset(x, y), 2f)
                }
                drawCircle(paleta.acento, 7.dp.toPx(), Offset(alto, y))
                drawCircle(paleta.panel, 7.dp.toPx(), Offset(bajo, y))
                drawCircle(paleta.acento, 7.dp.toPx(), Offset(bajo, y), style = androidx.compose.ui.graphics.drawscope.Stroke(1.dp.toPx()))
            }
            for ((indice, frecuencia) in frecuencias.withIndex()) {
                val x = 26.dp + (ancho - 52.dp) * indice / (frecuencias.size - 1).coerceAtLeast(1) - 24.dp
                Texto(frecuencia.toString(), tamano = 9, color = if (frecuencia > techo) paleta.rojo else paleta.sutil,
                    alineado = TextAlign.Center,
                    modifier = Modifier.offset(x = x, y = if (indice % 2 == 0) 42.dp else 58.dp).width(48.dp))
            }
            }
            // Los campos conservan el ajuste fino también sin arrastrar en el teléfono.
            if (ancho < MedidasGpuCu.anchoMovil) {
                Texto(t("Minimum frequency"), tamano = 12)
                CampoNumero(minimo, { alCambiar(it, maximo) }, 300, maximo, activo = activo, sufijo = "MHz")
                Texto(t("Maximum frequency"), tamano = 12)
                CampoNumero(maximo, { alCambiar(minimo, it) }, minimo, techo.coerceAtLeast(minimo), activo = activo, sufijo = "MHz")
            }
        }
    }
}

@Composable
internal fun CompatibilidadGpu(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean) {
    val actual = datos.objeto("cyan_telemetry")
    var metodo by remember { mutableStateOf("smu") }
    var uso by remember { mutableStateOf("busy-flag") }
    var temperatura by remember { mutableStateOf("drm") }
    var metricas by remember { mutableStateOf(true) }
    var frecuencias by remember { mutableStateOf(false) }
    var editado by remember { mutableStateOf(false) }
    LaunchedEffect(actual) {
        if (!editado) {
            metodo = actual.texto("set_method", "smu")
            uso = actual.texto("method", "busy-flag")
            temperatura = actual.texto("temp_read", "drm")
            metricas = actual.logico("fix_metrics", true)
            frecuencias = actual.logico("fix_frequency")
        }
    }
    fun opciones(valores: List<String>): List<Eleccion> {
        return valores.map { Eleccion(it, if (it == "smu") "SMU" else if (it == "drm") "DRM" else it) }
    }
    FilaHerramientaGpuCu(t("Cyan kernel compatibility"), "", tamanoTitulo = 15) {
        val modo = when {
            datos.texto("service_active") != "active" -> t("Governor stopped — press Start governor")
            datos.objeto("high_frequency_points").logico("enabled") -> t("Extended range")
            else -> t("Safe mode")
        }
        Texto(modo, tamano = 11, peso = 700, color = ColoresActuales.current.acento)
    }
    SubPanel(margen = PaddingValues(18.dp, 14.dp), espacio = 12.dp) {
        RejillaGpuCu(3, 3) { indice, modificador ->
            when (indice) {
                0 -> FilaEleccion(t("Governor method"), opciones(listOf("smu", "kernel")), metodo,
                    { metodo = it; editado = true }, modificador, libre)
                1 -> FilaEleccion(t("Usage reading"), opciones(listOf("busy-flag", "process", "kernel")), uso,
                    { uso = it; editado = true }, modificador, libre)
                else -> FilaEleccion(t("Temperature reading"), opciones(listOf("drm", "sysfs")), temperatura,
                    { temperatura = it; editado = true }, modificador, libre && actual.logico("temp_read_supported", true))
            }
        }
        if (uso == "process") {
            Texto(t("The process reading goes through every open file of every program. With a game open, Cyan stops answering: the range, the +2000 MHz points and the voltage lab stop working until the game closes. busy-flag is the default."),
                tamano = 12, color = ColoresActuales.current.naranja)
        }
        LineaDivisoria()
        FilaHerramientaGpuCu("", t("The BC-250 kernel already fixes this telemetry. Its recommended settings: kernel method, kernel usage reading, sysfs temperature, both fixes off.")) {
            Boton(t("Use the BC-250 kernel settings"), {
                metodo = "kernel"
                uso = "kernel"
                temperatura = "sysfs"
                metricas = false
                frecuencias = false
                editado = true
            }, activo = libre, alto = MedidasGpuCu.altoAccion)
        }
        LineaDivisoria()
        RejillaGpuCu(3, 3) { indice, modificador ->
            when (indice) {
                0 -> Row(modificador, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Casilla(metricas, { metricas = it; editado = true }, activa = libre)
                    Texto(datos.objeto("fix_labels").texto("metrics"), tamano = 13)
                }
                1 -> Row(modificador, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Casilla(frecuencias, { frecuencias = it; editado = true }, activa = libre)
                    Texto(datos.objeto("fix_labels").texto("frequency"), tamano = 13)
                }
                else -> Boton(t("Apply compatibility"), {
                    aplicacion.preguntarYEjecutar("gpu.compat", t("Apply Cyan compatibility settings"),
                        "$metodo · $uso · $temperatura\n" + t("Apply compatibility settings"),
                        mapOf("set_method" to JsonPrimitive(metodo), "usage_method" to JsonPrimitive(uso),
                            "metrics" to JsonPrimitive(metricas), "frequencies" to JsonPrimitive(frecuencias),
                            "temp_read" to JsonPrimitive(temperatura)), peligro = metodo == "kernel")
                    editado = false
                }, modificador, activo = libre, alto = MedidasGpuCu.altoAccion)
            }
        }
    }
}

@Composable
internal fun HerramientasGpu(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean,
    alLaboratorio: () -> Unit, alConfiguracion: () -> Unit) {
    val funcionando = datos.texto("service_active") == "active"
    val oberon = datos.texto("governor_backend") == "oberon-governor"
    SubPanel(margen = PaddingValues(18.dp, 14.dp), espacio = 14.dp) {
        FilaHerramientaGpuCu(t("Governor service"), t("Start governor runs it now and saves it for startup (enables the service). Stop governor stops it and removes it from startup (disables the service).")) {
            RejillaAccionesServicioGpu(aplicacion, datos, funcionando, libre)
        }
        LineaDivisoria()
        FilaHerramientaGpuCu(t(if (oberon) "YAML endpoint laboratory" else "Voltage laboratory"),
            t("Point-by-point conservative validation of the selected range.")) {
            AccionesGpuCu(2, 404.dp) { indice, caja ->
                if (indice == 0) Boton(t("Open laboratory"), alLaboratorio, caja, alto = MedidasGpuCu.altoAccion)
                else Boton(t(if (oberon) "Open oberon-config.yaml" else "Open config.toml"), alConfiguracion, caja, alto = MedidasGpuCu.altoAccion)
            }
        }
    }
}

@Composable
private fun RejillaAccionesServicioGpu(aplicacion: Aplicacion, datos: JsonObject, funcionando: Boolean, libre: Boolean) {
    AccionesGpuCu(3, 612.dp) { indice, caja ->
        if (indice == 0) {
            Boton(t("View status"), { aplicacion.ejecutar("gpu.status", t("View status")) }, caja, alto = MedidasGpuCu.altoAccion)
        } else {
            val accion = if (indice == 1) "reiniciar" else if (funcionando) "desactivar" else "activar"
            val titulo = t(if (indice == 1) "Restart" else if (funcionando) "Stop governor" else "Start governor")
            val plan = datos.objeto("service_plans").objeto(accion)
            Boton(titulo, {
                aplicacion.preguntarYEjecutar("gpu.service", titulo, plan.texto("message", titulo),
                    mapOf("action" to JsonPrimitive(accion)), peligro = plan.logico("risk"))
            }, caja, clase = if (accion == "desactivar") ClaseBoton.PELIGRO else ClaseBoton.NORMAL,
                activo = libre, alto = MedidasGpuCu.altoAccion)
        }
    }
}

@Composable
internal fun DiagnosticosGpu(datos: JsonObject, minimo: Int, maximo: Int) {
    val paleta = ColoresActuales.current
    TituloGpuCu(t("Active TOML safe-points"))
    RejillaGpuCu(datos.objetos("rail").size, 4) { indice, modificador ->
        val punto = datos.objetos("rail")[indice]
        val frecuencia = punto.entero("frequency")
        val activos = datos.objetos("safe_points_with_voltage").ifEmpty { datos.objetos("safe_points") }
        val activo = activos.firstOrNull { it.entero("frequency") == frecuencia }
        SubPanel(modificador) {
            Texto("$frecuencia MHz", peso = 700, tamano = 13)
            Texto("${activo?.entero("voltage") ?: punto.entero("voltage")} mV", tamano = 12)
            Texto(t(if (activo == null) "COMMENTED" else if (frecuencia in minimo..maximo) "IN RANGE" else "VALIDATED"),
                tamano = 11, color = if (activo == null) paleta.rojo else paleta.acento)
        }
    }
    for (fila in datos.objetos("diagnostics")) {
        FilaHerramientaGpuCu(fila.texto("label"), fila.texto("detail")) { Texto(fila.texto("value"), tamano = 13) }
    }
    val contrato = listOf(
        t("Device") to "AMD BC-250 · 0x1002 / 0x13fe",
        t("Governor") to datos.texto("governor_backend"),
        t("Active points") to datos.texto("active_points"),
        t("Accepted range") to "$minimo – $maximo MHz",
        t("Allowed ceiling") to "${datos.entero("ceiling")} MHz",
        t("D-Bus API") to t(if (datos.logico("dbus_connected")) "Connected · range running" else "Not connected"),
        t("Configuration") to datos.texto("config_path"),
    )
    for ((nombre, valor) in contrato) FilaHerramientaGpuCu(nombre, valor) { }
}
