package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.shape.RoundedCornerShape
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

@Composable
internal fun SensoresRendimiento(
    aplicacion: Aplicacion, datos: JsonObject,
    buscar: String, alBuscar: (String) -> Unit, tipos: Set<Int>, alTipo: (Int) -> Unit,
    ocultar: Boolean, alOcultar: (Boolean) -> Unit,
    distribucion: String, alDistribucion: (String) -> Unit,
    ventana: Int, alVentana: (Int) -> Unit, alMarcar: (String) -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val movil = maxWidth < M.anchoMovil
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (movil) {
                CampoTexto(buscar, alBuscar, Modifier.fillMaxWidth(), ayuda = t("Filter by name"), alto = M.altoFiltro)
                ControlesSensores(aplicacion, ocultar, alOcultar, apilado = true)
            } else {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
                    CampoTexto(buscar, alBuscar, Modifier.weight(1f), ayuda = t("Filter by name"), alto = M.altoFiltro)
                    ControlesSensores(aplicacion, ocultar, alOcultar)
                }
            }
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(6.dp)) {
                for (opcion in datos.objetos("kinds")) {
                    val indice = opcion.entero("index")
                    val elegido = indice in tipos || (indice == 0 && tipos.isEmpty())
                    EtiquetaTipo(opcion.texto("title"), opcion.texto("tone"), elegido) { alTipo(indice) }
                }
            }
            if (distribucion == "split" && !movil) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
                    ListaSensores(datos, alMarcar, Modifier.weight(945f))
                    TrazasSensores(datos, ventana, Modifier.weight(631f))
                }
            } else {
                if (distribucion != "graphs") ListaSensores(datos, alMarcar, Modifier.fillMaxWidth())
                if (distribucion != "list") TrazasSensores(datos, ventana, Modifier.fillMaxWidth())
            }
            if (movil) {
                Leyenda(datos.texto("count"))
                Leyenda(datos.texto("footer"))
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Leyenda(datos.texto("count"))
                    Leyenda("·")
                    Leyenda(datos.texto("footer"))
                }
            }
        }
    }
}

@Composable
private fun ControlesSensores(aplicacion: Aplicacion, ocultar: Boolean, alOcultar: (Boolean) -> Unit, apilado: Boolean = false) {
    @Composable fun casilla() {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            CasillaSensor(ocultar) { alOcultar(!ocultar) }
            Texto(t("Hide unused channels"), tamano = 12)
        }
    }
    @Composable fun reiniciar() {
        Boton(t("Reset min/max"), {
            aplicacion.guardar("performance.reset", emptyMap(), "performance")
        }, alto = M.altoFiltro, tamano = 12, activo = aplicacion.puedeControlar)
    }
    if (apilado) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            casilla()
            reiniciar()
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            casilla()
            reiniciar()
        }
    }
}

/** Una clase de sensor: su cuadrito de color y su nombre. */
@Composable
private fun EtiquetaTipo(nombre: String, tono: String, elegido: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (elegido) paleta.acentoSuave else paleta.panel
    val borde = if (elegido) paleta.acentoBorde else paleta.bordeSuave
    Row(
        modifier = Modifier
            .height(M.altoTipo)
            .marco(fondo, borde, 4.dp)
            .pulsable(alPulsar = alPulsar)
            .padding(horizontal = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (tono.isNotEmpty()) {
            MarcaTipo(tono)
        }
        val color = if (elegido) paleta.texto else paleta.apagado
        Texto(nombre, tamano = 11, peso = 600, color = color)
    }
}

/** El cuadrito que dice de qué clase es un sensor. */
@Composable
private fun MarcaTipo(tono: String) {
    val color = ColoresActuales.current.color(tono)
    Box(Modifier.size(6.dp).background(color, RoundedCornerShape(1.5.dp)))
}

@Composable
private fun ListaSensores(datos: JsonObject, alMarcar: (String) -> Unit, modifier: Modifier) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(modifier.marco(paleta.panel, paleta.bordeSuave, 4.dp).padding(1.dp).height(M.altoListaSensores)) {
        val ancho = maxOf(maxWidth, M.anchoTabla)
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(ancho)) {
                CabeceraSensores()
                FilasSensores(datos, alMarcar, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun CabeceraSensores() {
    val paleta = ColoresActuales.current
    Row(
        Modifier.fillMaxWidth().height(M.altoCabeceraSensor - 1.dp).background(paleta.panelAlterno).padding(end = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Texto(t("Sensor"), 11, Modifier.weight(1f).padding(start = 8.dp), peso = 750, color = paleta.apagado)
        for (titulo in listOf("Value", "Min", "Avg", "Max")) {
            CeldaSensor(t(titulo), paleta.apagado, peso = 750, tamano = 11)
        }
    }
    LineaDivisoria(color = paleta.borde)
}

@Composable
private fun CeldaSensor(texto: String, color: Color, peso: Int = 400, tamano: Int = 12) {
    Texto(texto, tamano, Modifier.width(M.anchoValorSensor).padding(end = 8.dp), peso = peso, color = color, alineado = TextAlign.End)
}

@Composable
private fun FilasSensores(datos: JsonObject, alMarcar: (String) -> Unit, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val plegados = remember { mutableStateMapOf<String, Boolean>() }
    val filas = datos.objetos("rows")
    Column(modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
        var grupo = ""
        var numero = 0
        for (fila in filas) {
            val esGrupo = fila.containsKey("group")
            if (esGrupo) {
                grupo = fila.texto("group")
                numero = 0
                val nombre = grupo
                FilaGrupoSensor(nombre, plegados[nombre] == true) { plegados[nombre] = plegados[nombre] != true }
            } else if (plegados[grupo] != true) {
                val fondo = if (numero % 2 == 0) paleta.panelAlterno else paleta.panel
                numero += 1
                FilaSensor(fila, fondo, alMarcar)
            }
        }
        if (filas.isEmpty()) {
            Leyenda(datos.texto("count"), Modifier.padding(12.dp))
        }
    }
}

@Composable
private fun FilaGrupoSensor(nombre: String, plegado: Boolean, alPlegar: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(M.altoFilaSensor).pulsable(alPulsar = alPlegar).padding(start = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        FlechaPlegar(abierto = !plegado)
        Spacer(Modifier.width(7.dp))
        Texto(nombre, tamano = 12, peso = 700)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FilaSensor(fila: JsonObject, fondo: Color, alMarcar: (String) -> Unit) {
    val paleta = ColoresActuales.current
    val clave = fila.texto("key")
    fun marcar() {
        alMarcar(clave)
    }
    Row(
        Modifier.fillMaxWidth().height(M.altoFilaSensor).background(fondo)
            .combinedClickable(onClick = ::marcar, onDoubleClick = ::marcar).padding(start = 31.dp, end = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CasillaSensor(fila.logico("ticked"), ::marcar)
        Spacer(Modifier.width(9.dp))
        MarcaTipo(fila.texto("tone"))
        Spacer(Modifier.width(8.dp))
        Texto(fila.texto("label"), 12, Modifier.weight(1f), lineas = 1)
        CeldaSensor(fila.texto("value"), paleta.texto, peso = 600)
        CeldaSensor(fila.texto("min"), paleta.apagado)
        CeldaSensor(fila.texto("avg"), paleta.apagado)
        CeldaSensor(fila.texto("max"), paleta.apagado)
    }
}

/** La casilla de la tabla: un cuadro relleno, sin marca, de 14 px. */
@Composable
private fun CasillaSensor(marcada: Boolean, alCambiar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (marcada) paleta.acento else paleta.panelAlterno
    val borde = if (marcada) paleta.acento else paleta.bordeFuerte
    Box(Modifier.size(14.dp).marco(fondo, borde, 2.dp).pulsable(alPulsar = alCambiar))
}

// -- trazas -----------------------------------------------------------------------------------------------

@Composable
private fun TrazasSensores(datos: JsonObject, ventana: Int, modifier: Modifier) {
    Column(modifier.height(M.altoListaSensores).verticalScroll(rememberScrollState()).padding(end = 4.dp), Arrangement.spacedBy(8.dp)) {
        val trazas = datos.objetos("traces")
        val faltan = datos.objetos("missing_traces")
        if (trazas.isEmpty() && faltan.isEmpty()) {
            Leyenda(t("Tick a sensor in the list to draw its last two minutes here."), Modifier.padding(24.dp))
        }
        for (traza in trazas) {
            TrazaSensor(traza, ventana)
        }
        for (traza in faltan) {
            SubPanel {
                Texto(traza.texto("label"), tamano = 11, peso = 600)
                Leyenda(t("Waiting for first sample"))
            }
        }
    }
}

@Composable
private fun TrazaSensor(traza: JsonObject, ventana: Int) {
    val paleta = ColoresActuales.current
    Column(
        Modifier.fillMaxWidth().height(M.altoTraza).marco(paleta.color("chart_surface"), paleta.bordeSuave, 8.dp)
            .padding(start = 9.dp, top = 6.dp, end = 10.dp, bottom = 8.dp),
        Arrangement.spacedBy(6.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            MarcaTipo(traza.texto("tone"))
            Spacer(Modifier.width(6.dp))
            Texto(traza.texto("label"), tamano = 11, peso = 600)
            Spacer(Modifier.width(8.dp))
            val equipo = if (traza.logico("fresh")) traza.texto("device") else t("Waiting for sample")
            Texto(equipo, 11, Modifier.weight(1f), color = paleta.sutil, lineas = 1)
            Texto(traza.texto("value"), tamano = 11, peso = 600)
        }
        GraficaTraza(traza.objeto("chart"), ventana, paleta.color(traza.texto("tone")), Modifier.weight(1f))
    }
}

/** La línea de un sensor con sus marcas a la derecha, como la dibuja el escritorio. */
@Composable
private fun GraficaTraza(datos: JsonObject, ventana: Int, color: Color, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val esPorcentaje = datos.texto("unit") == "%"
    val minimo = if (esPorcentaje) 0.0 else datos.numero("min") ?: 0.0
    val maximo = if (esPorcentaje) 100.0 else (datos.numero("max") ?: 1.0).coerceAtLeast(minimo + 0.001)
    val marcas = if (esPorcentaje) listOf(0.0 to "0", 50.0 to "50", 100.0 to "100") else marcasDe(datos)
    val edades = numerosDe(datos, "ages")
    val valores = datos.objetos("series").firstOrNull()?.let { serie -> numerosDe(serie, "values") } ?: emptyList()
    var cursor by remember { mutableStateOf<Float?>(null) }
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val alto = maxHeight
        Canvas(
            Modifier.fillMaxSize().padding(end = 54.dp).pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val evento = awaitPointerEvent()
                        val punto = evento.changes.firstOrNull()?.position?.x
                        cursor = if (evento.type == PointerEventType.Exit) null else punto
                    }
                }
            },
        ) {
            dibujarTraza(marcas, edades, valores, minimo, maximo, ventana, color, paleta.color("chart_grid"), cursor, paleta.apagado)
        }
        for ((valor, nombre) in marcas) {
            val parte = ((maximo - valor) / (maximo - minimo)).toFloat().coerceIn(0f, 1f)
            Texto(nombre, 11, Modifier.align(Alignment.TopEnd).width(48.dp).offset(y = alto * parte - 8.dp), color = paleta.sutil)
        }
        LecturaCursor(cursor, edades, valores, ventana, datos.texto("unit"), maxWidth - 54.dp)
    }
}

@Composable
private fun LecturaCursor(cursor: Float?, edades: List<Double>, valores: List<Double>, ventana: Int, unidad: String, ancho: Dp) {
    if (cursor == null || edades.isEmpty()) {
        return
    }
    val paleta = ColoresActuales.current
    val x = with(LocalDensity.current) { cursor.toDp() }
    val edad = ventana * (1.0 - x / ancho)
    val indice = edades.indices.minByOrNull { item -> kotlin.math.abs(edades[item] - edad) } ?: return
    val valor = valores.getOrNull(indice) ?: return
    val redondeado = kotlin.math.round(valor * 10) / 10
    val texto = "$redondeado $unidad  -${edades[indice].toInt()} s"
    val lugar = (x - 50.dp).coerceIn(0.dp, (ancho - 100.dp).coerceAtLeast(0.dp))
    Box(Modifier.offset(x = lugar).marco(paleta.panelElevado, paleta.borde, 4.dp).padding(horizontal = 6.dp, vertical = 2.dp)) {
        Texto(texto, tamano = 11)
    }
}

private fun marcasDe(datos: JsonObject): List<Pair<Double, String>> {
    return datos.objetos("ticks").map { marca -> (marca.numero("value") ?: 0.0) to marca.texto("label") }
}

private fun numerosDe(datos: JsonObject, clave: String): List<Double> {
    return datos.lista(clave).map { valor -> (valor as? JsonPrimitive)?.doubleOrNull ?: 0.0 }
}

private fun DrawScope.dibujarTraza(
    marcas: List<Pair<Double, String>>,
    edades: List<Double>,
    valores: List<Double>,
    minimo: Double,
    maximo: Double,
    ventana: Int,
    color: Color,
    rejilla: Color,
    cursor: Float?,
    colorCursor: Color,
) {
    fun x(edad: Double): Float {
        return size.width * (1f - (edad / ventana).toFloat()).coerceIn(0f, 1f)
    }

    fun y(valor: Double): Float {
        val parte = ((valor - minimo) / (maximo - minimo)).coerceIn(0.0, 1.0)
        return size.height * (1f - parte.toFloat())
    }

    for ((valor, _) in marcas) {
        drawLine(rejilla, Offset(0f, y(valor)), Offset(size.width, y(valor)), 1.dp.toPx())
    }
    val linea = Path()
    val relleno = Path()
    var anterior: Double? = null
    var ultimaX = 0f
    for (indice in edades.indices) {
        val valor = valores.getOrNull(indice) ?: break
        val punto = Offset(x(edades[indice]), y(valor))
        val hueco = anterior == null || anterior - edades[indice] > 3.5
        if (hueco) {
            if (anterior != null) {
                relleno.lineTo(ultimaX, size.height)
                relleno.close()
            }
            linea.moveTo(punto.x, punto.y)
            relleno.moveTo(punto.x, size.height)
            relleno.lineTo(punto.x, punto.y)
        } else {
            linea.lineTo(punto.x, punto.y)
            relleno.lineTo(punto.x, punto.y)
        }
        anterior = edades[indice]
        ultimaX = punto.x
    }
    if (anterior != null) {
        relleno.lineTo(ultimaX, size.height)
        relleno.close()
    }
    drawPath(relleno, Brush.verticalGradient(listOf(color.copy(alpha = 0.23f), color.copy(alpha = 0.016f))))
    drawPath(linea, color, style = Stroke(2.dp.toPx()))
    if (cursor != null && cursor <= size.width) {
        drawLine(colorCursor, Offset(cursor, 0f), Offset(cursor, size.height), 1.dp.toPx())
    }
}
