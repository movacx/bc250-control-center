package org.bc250.controlcenter.paginas

import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.style.TextAlign
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.AccionesGpuCu
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.CampoNumero
import org.bc250.controlcenter.componentes.CasillaChica
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Eleccion
import org.bc250.controlcenter.componentes.FilaEleccion
import org.bc250.controlcenter.componentes.FilaHerramientaGpuCu
import org.bc250.controlcenter.componentes.Leyenda
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.RejillaGpuCu
import org.bc250.controlcenter.componentes.SeccionGpuCu
import org.bc250.controlcenter.componentes.SubPanel
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TituloGpuCu
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasGpuCu
import org.bc250.controlcenter.tema.Paleta
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
                        extremo = if (abs(punto.x - posicion(minimoActual,
                            size.width.toFloat())) < abs(punto.x - posicion(maximoActual, size.width.toFloat()))) "min" else "max"
                        moverActual(punto.x, size.width.toFloat())
                    }
                }.pointerInput(activo, techo, frecuencias) {
                    detectDragGestures(onDragStart = { punto ->
                        extremo = if (abs(punto.x - posicion(minimoActual,
                            size.width.toFloat())) < abs(punto.x - posicion(maximoActual, size.width.toFloat()))) "min" else "max"
                    }) { cambio, _ ->
                        cambio.consume()
                        moverActual(cambio.position.x, size.width.toFloat())
                    }
                }) {
                val y = 20.dp.toPx()
                val bajo = posicion(minimo, size.width)
                val alto = posicion(maximo, size.width)
                val fin = size.width - 26f
                drawLine(paleta.bordeSuave, Offset(26f, y), Offset(fin, y), 3.dp.toPx())
                drawLine(paleta.rojoBorde.copy(alpha = 0.55f), Offset(posicion(techo, size.width), y), Offset(fin, y), 4.dp.toPx())
                drawLine(paleta.acento, Offset(bajo, y), Offset(alto, y), 4.dp.toPx())
                for ((indice, frecuencia) in frecuencias.withIndex()) {
                    val x = posicion(frecuencia, size.width)
                    val final = y - if (indice % 2 == 0) 2.dp.toPx() else 5.dp.toPx()
                    val color = colorDeMarca(frecuencia, minimo, maximo, techo, paleta)
                    drawLine(color, Offset(x, y - 17.dp.toPx()), Offset(x, final), 2.dp.toPx())
                }
                dibujarTope(Offset(alto, y), paleta.acento, paleta.acento)
                dibujarTope(Offset(bajo, y), paleta.ventana, paleta.acento)
            }
            for ((indice, frecuencia) in frecuencias.withIndex()) {
                val x = 26.dp + (ancho - 52.dp) * indice / (frecuencias.size - 1).coerceAtLeast(1) - 24.dp
                Texto(frecuencia.toString(), tamano = 9, color = colorDelPunto(frecuencia, minimo, maximo, techo, paleta),
                    alineado = TextAlign.Center,
                    modifier = Modifier.offset(x = x, y = if (indice % 2 == 0) 36.dp else 52.dp).width(48.dp))
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
internal fun CompatibilidadGpu(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean, clasica: Boolean = false) {
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
    fun aplicar() {
        aplicarCompatibilidad(aplicacion, AjusteCyan(metodo, uso, temperatura, metricas, frecuencias))
        editado = false
    }
    @Composable
    fun filas() {
        RejillaGpuCu(3, 3, separacion = 10.dp) { indice, modificador ->
            when (indice) {
                0 -> FilaEleccion(t("Governor method"), opciones(listOf("smu", "kernel")), metodo,
                    { valor ->
                        metodo = valor
                        editado = true
                    }, modificador, libre)
                1 -> FilaEleccion(t("Usage reading"), opciones(listOf("busy-flag", "process", "kernel")), uso,
                    { valor ->
                        uso = valor
                        editado = true
                    }, modificador, libre)
                else -> FilaEleccion(t("Temperature reading"), opciones(listOf("drm", "sysfs")), temperatura,
                    { valor ->
                        temperatura = valor
                        editado = true
                    }, modificador, libre && actual.logico("temp_read_supported", true))
            }
        }
        if (uso == "process") {
            Texto(avisoProcess(),
                tamano = 12, color = ColoresActuales.current.naranja)
        }
        Separador(clasica)
        FilaHerramientaGpuCu("", t("The BC-250 kernel already fixes this telemetry. Its recommended settings: kernel method, " +
            "kernel usage reading, sysfs temperature, both fixes off."), tamanoDetalle = 10) {
            Boton(t("Use the BC-250 kernel settings"), {
                metodo = "kernel"
                uso = "kernel"
                temperatura = "sysfs"
                metricas = false
                frecuencias = false
                editado = true
            }, Modifier.width(235.dp), activo = libre, alto = MedidasGpuCu.altoAccion, tamano = 12)
        }
        Separador(clasica)
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth < MedidasGpuCu.anchoMovil) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    MarcaGpu(datos.objeto("fix_labels").texto("metrics"), metricas, libre) {
                        metricas = !metricas
                        editado = true
                    }
                    MarcaGpu(datos.objeto("fix_labels").texto("frequency"), frecuencias, libre) {
                        frecuencias = !frecuencias
                        editado = true
                    }
                    BotonCompatibilidad(libre, Modifier.fillMaxWidth(), ::aplicar)
                }
            } else {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(16.dp), Alignment.CenterVertically) {
                    MarcaGpu(datos.objeto("fix_labels").texto("metrics"), metricas, libre) {
                        metricas = !metricas
                        editado = true
                    }
                    MarcaGpu(datos.objeto("fix_labels").texto("frequency"), frecuencias, libre) {
                        frecuencias = !frecuencias
                        editado = true
                    }
                    Spacer(Modifier.weight(1f))
                    BotonCompatibilidad(libre, Modifier.width(195.dp), ::aplicar)
                }
            }
        }
    }
    @Composable
    fun modo() {
        Texto(modoGpu(datos), tamano = 11, peso = 780, color = ColoresActuales.current.verde)
    }
    if (clasica) {
        SubPanel(margen = PaddingValues(14.dp, 12.dp), espacio = 9.dp) {
            Row(Modifier.fillMaxWidth().height(23.dp), verticalAlignment = Alignment.CenterVertically) {
                Texto(t("Cyan kernel compatibility"), 14, Modifier.weight(1f), peso = 780)
                modo()
            }
            Leyenda(t("Only touch this if the readings above look wrong."))
            Column { filas() }
        }
    } else {
        SeccionGpuCu(t("Cyan kernel compatibility"), alto = 23.dp, derecha = { modo() }) {
            SubPanel(margen = PaddingValues(18.dp, 14.dp), espacio = 0.dp) { filas() }
        }
    }
}

private fun modoGpu(datos: JsonObject): String {
    return when {
        datos.texto("service_active") != "active" -> t("Governor stopped — press Start governor")
        datos.objeto("high_frequency_points").logico("enabled") -> t("Extended range")
        else -> t("Safe mode")
    }
}

@Composable
private fun Separador(clasica: Boolean) {
    if (clasica) {
        Spacer(Modifier.height(9.dp))
    } else {
        SeparadorGpu()
    }
}

/** El hueco y la línea entre dos filas de un panel. */
@Composable
private fun SeparadorGpu() {
    LineaDivisoria(Modifier.padding(vertical = 11.dp))
}

/** Una corrección del kernel: su casilla y su nombre. */
@Composable
private fun MarcaGpu(nombre: String, marcada: Boolean, activa: Boolean, alCambiar: () -> Unit) {
    Row(Modifier.height(24.dp).pulsable(activa, alPulsar = alCambiar), Arrangement.spacedBy(9.dp), Alignment.CenterVertically) {
        CasillaChica(marcada, activa, alCambiar)
        Texto(nombre, tamano = 13)
    }
}

@Composable
private fun BotonCompatibilidad(activo: Boolean, modifier: Modifier, alPulsar: () -> Unit) {
    Boton(t("Apply compatibility"), alPulsar, modifier, activo = activo, alto = MedidasGpuCu.altoAccion, tamano = 12)
}

@Composable
internal fun HerramientasGpu(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean,
    alLaboratorio: () -> Unit, alConfiguracion: () -> Unit) {
    val funcionando = datos.texto("service_active") == "active"
    val oberon = datos.texto("governor_backend") == "oberon-governor"
    SubPanel(margen = PaddingValues(18.dp, 14.dp), espacio = 0.dp) {
        FilaHerramientaGpuCu(t("Governor service"),
            t("Start governor runs it now and saves it for startup (enables the service). Stop governor stops " +
            "it and removes it from startup (disables the service).")) {
            RejillaAccionesServicioGpu(aplicacion, datos, funcionando, libre)
        }
        SeparadorGpu()
        FilaHerramientaGpuCu(t(if (oberon) "YAML endpoint laboratory" else "Voltage laboratory"),
            t("Point-by-point conservative validation of the selected range.")) {
            AccionesGpuCu(2, 404.dp) { indice, caja ->
                if (indice == 0) Boton(t("Open laboratory"), alLaboratorio, caja, alto = MedidasGpuCu.altoAccion, tamano = 12)
                else Boton(t(if (oberon) "Open oberon-config.yaml" else "Open config.toml"), alConfiguracion, caja,
                    alto = MedidasGpuCu.altoAccion, tamano = 12)
            }
        }
    }
}

@Composable
internal fun RejillaAccionesServicioGpu(aplicacion: Aplicacion, datos: JsonObject, funcionando: Boolean, libre: Boolean,
    alto: androidx.compose.ui.unit.Dp = MedidasGpuCu.altoAccion, tamano: Int = 12) {
    AccionesGpuCu(3, 613.dp) { indice, caja ->
        if (indice == 0) {
            Boton(t("View status"), { aplicacion.ejecutar("gpu.status", t("View status")) }, caja, alto = alto, tamano = tamano)
        } else {
            val accion = if (indice == 1) "reiniciar" else if (funcionando) "desactivar" else "activar"
            val titulo = tituloServicioGpu(accion)
            Boton(titulo, {
                pedirServicioGpu(aplicacion, datos, accion)
            }, caja, clase = if (accion == "desactivar") ClaseBoton.PELIGRO else ClaseBoton.NORMAL,
                activo = libre && datos.objeto("availability").logico(
                    if (accion == "reiniciar") "restart" else if (accion == "activar") "start" else "stop",
                ), alto = alto, tamano = tamano)
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

/** Un punto elegido se lee entero; uno fuera del rango, apagado; uno bloqueado, en rojo apagado. */
private fun colorDelPunto(frecuencia: Int, minimo: Int, maximo: Int, techo: Int, paleta: Paleta): Color {
    return when {
        frecuencia > techo -> paleta.rojoBorde
        frecuencia in minimo..maximo -> paleta.texto
        else -> paleta.sutil
    }
}

private fun colorDeMarca(frecuencia: Int, minimo: Int, maximo: Int, techo: Int, paleta: Paleta): Color {
    return when {
        frecuencia > techo -> paleta.rojoBorde.copy(alpha = 0.55f)
        frecuencia in minimo..maximo -> paleta.acento
        else -> paleta.bordeFuerte
    }
}

/** Cada extremo del rango: una pastilla de 14 por 20. */
private fun DrawScope.dibujarTope(centro: Offset, fondo: Color, borde: Color) {
    val medida = Size(14.dp.toPx(), 20.dp.toPx())
    val esquina = Offset(centro.x - medida.width / 2, centro.y - medida.height / 2)
    val radio = CornerRadius(6.dp.toPx())
    drawRoundRect(fondo, esquina, medida, radio)
    drawRoundRect(borde, esquina, medida, radio, style = Stroke(1.dp.toPx()))
}

/** El mismo aviso del escritorio: editar el TOML no cambia el rango activo. */
internal fun avisoPuntosAltos(habilitar: Boolean): String {
    return if (habilitar) {
        t(
            "This edits only the TOML safe-point blocks above 2000 MHz and validates the complete " +
                "file. These frequencies are experimental, are not guaranteed stable, and can crash " +
                "the display or system. This does not reload Cyan or change the live GPU range; " +
                "use Apply active range explicitly after selecting a point.",
        )
    } else {
        t(
            "This comments the TOML safe-point blocks above 2000 MHz and validates the complete " +
                "file. Active 3D workloads must be stopped first. This does not reload Cyan or " +
                "change the live GPU range.",
        )
    }
}
