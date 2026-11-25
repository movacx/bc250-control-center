package org.bc250.controlcenter.movil

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.paginas.DiagnosticosGpu
import org.bc250.controlcenter.paginas.pedirPuntosAltos
import org.bc250.controlcenter.paginas.pedirVoltaje
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

private const val SIN_AUMENTO = 0
private const val PERSONALIZADO = -1
private const val PASO_MV = 5
private const val MENOR_MV = 600
private const val MAYOR_MV = 1200
private const val TECHO_SEGURO = 2000
private const val CABEN_TODOS = 9
private val AltoGrafica = 252.dp

/** Un punto de la curva: el voltaje que tiene y el que se propone. */
class PuntoVoltaje(val frecuencia: Int, val actual: Int, val propuesto: Int, val editable: Boolean) {
    val cambiado: Boolean get() = propuesto != actual
}

/** La curva que se está preparando. Nada llega a la placa hasta confirmarlo. */
class EleccionVoltaje {
    /** 0 la deja como está, 1 a 3 suman 10, 20 o 30 mV y -1 es punto por punto. */
    var nivel by mutableStateOf(SIN_AUMENTO)
        private set
    var valores by mutableStateOf<Map<Int, Int>>(emptyMap())
        private set
    var elegido by mutableStateOf(-1)

    /** Lo que respondió el servidor para el nivel y los valores elegidos. */
    var tabla by mutableStateOf(ObjetoVacio)

    val puntos: List<PuntoVoltaje>
        get() = tabla.objetos("rows").filter { fila -> fila.entero("current") > 0 }.map(::leerPunto)

    val cambiado: Boolean get() = puntos.any { punto -> punto.cambiado }
    val sePuedeAplicar: Boolean get() = cambiado && tabla.logico("available")

    private fun leerPunto(fila: JsonObject): PuntoVoltaje {
        val frecuencia = fila.entero("frequency")
        val actual = fila.entero("current")
        val propuesto = when (nivel) {
            SIN_AUMENTO -> actual
            PERSONALIZADO -> valores[frecuencia] ?: actual
            else -> fila.entero("proposed")
        }
        return PuntoVoltaje(frecuencia, actual, propuesto, fila.logico("custom_available"))
    }

    fun elegirNivel(nuevo: Int) {
        nivel = nuevo
        valores = emptyMap()
    }

    fun descartar() {
        elegirNivel(SIN_AUMENTO)
    }

    /** Mover un punto convierte la propuesta en personalizada, partiendo de la que se veía. */
    fun mover(frecuencia: Int, voltaje: Int, menor: Int, mayor: Int) {
        if (nivel != PERSONALIZADO) {
            valores = puntos.filter { punto -> punto.editable }.associate { punto -> punto.frecuencia to punto.propuesto }
            nivel = PERSONALIZADO
        }
        val redondo = (voltaje.toFloat() / PASO_MV).roundToInt() * PASO_MV
        valores = valores + (frecuencia to redondo.coerceIn(menor, mayor))
    }

    fun enJson(): JsonObject {
        val editables = puntos.filter { punto -> punto.editable }
        return JsonObject(editables.associate { punto -> punto.frecuencia.toString() to JsonPrimitive(punto.propuesto) })
    }

    suspend fun leer(aplicacion: Aplicacion) {
        val parametros = mutableMapOf("level" to (if (nivel == SIN_AUMENTO) PERSONALIZADO else nivel).toString())
        if (nivel == PERSONALIZADO && valores.isNotEmpty()) {
            parametros["values"] = enJson().toString()
        }
        val respuesta = aplicacion.consultar("gpu.laboratorio", parametros)
        if (respuesta.isNotEmpty()) {
            tabla = respuesta
        }
    }

    suspend fun aplicar(aplicacion: Aplicacion) {
        pedirVoltaje(aplicacion, nivel, enJson(), tabla)
    }
}

/** Vuelve a pedir la curva cada vez que cambia lo elegido o lo que hay en la placa. */
@Composable
fun LeerVoltajes(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionVoltaje) {
    LaunchedEffect(eleccion.nivel, eleccion.valores, datos.objeto("voltage_lab")) {
        if (datos.isNotEmpty() && datos.texto("error").isEmpty()) {
            delay(150)
            eleccion.leer(aplicacion)
        }
    }
}

@Composable
fun VoltajeGpu(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionVoltaje, libre: Boolean) {
    if (esOberon(datos)) {
        VoltajeOberon(aplicacion, datos)
        return
    }
    val puntos = eleccion.puntos
    if (puntos.isEmpty()) {
        NotaMovil(t(if (datos.isEmpty() || eleccion.tabla.isEmpty()) "Waiting for data…" else "Not detected"))
        return
    }
    val menor = datos.entero("minimum_mv", MENOR_MV)
    val mayor = datos.entero("maximum_mv", MAYOR_MV)
    val indice = if (eleccion.elegido in puntos.indices) eleccion.elegido else indiceInicial(puntos, datos)
    val punto = puntos[indice]
    FranjaVoltaje(datos, puntos.maxOf { it.propuesto }, datos.entero("ceiling", TECHO_SEGURO))
    GrupoMovil {
        CurvaVoltaje(puntos, indice, libre, { eleccion.elegido = it }) { frecuencia, voltaje ->
            eleccion.mover(frecuencia, voltaje, menor, mayor)
        }
        FilaPunto(punto, "${punto.frecuencia} MHz", detalleDe(punto), libre, menor, mayor, eleccion)
    }
    if (eleccion.tabla.texto("error").isNotEmpty()) {
        NotaMovil(eleccion.tabla.texto("error"), ColoresActuales.current.rojo)
    }
    OpcionesVoltaje(aplicacion, datos, eleccion, puntos, libre)
}

private fun indiceInicial(puntos: List<PuntoVoltaje>, datos: JsonObject): Int {
    val lugar = puntos.indexOfLast { punto -> punto.frecuencia <= datos.entero("current_max", TECHO_SEGURO) }
    return lugar.coerceAtLeast(0)
}

@Composable
private fun FranjaVoltaje(datos: JsonObject, mayor: Int, techo: Int) {
    val ahora = datos.entero("voltaje_actual")
    FranjaLecturas(
        LecturaFranja(t("Voltage now"), if (ahora > 0) ahora.toString() else "--", "mV"),
        LecturaFranja(t("Highest"), mayor.toString(), "mV"),
        LecturaFranja(t("Ceiling"), techo.toString(), "MHz"),
    )
}

private fun detalleDe(punto: PuntoVoltaje): String {
    if (!punto.cambiado) {
        return t("No changes")
    }
    val diferencia = punto.propuesto - punto.actual
    val signo = if (diferencia > 0) "+" else ""
    return t("Before {value} mV", "value" to punto.actual.toString()) + " · $signo$diferencia mV"
}

@Composable
private fun FilaPunto(
    punto: PuntoVoltaje,
    nombre: String,
    detalle: String,
    libre: Boolean,
    menor: Int,
    mayor: Int,
    eleccion: EleccionVoltaje,
) {
    FilaPaso(
        nombre = nombre,
        valor = punto.propuesto,
        unidad = "mV",
        minimo = menor,
        maximo = mayor,
        paso = PASO_MV,
        detalle = detalle,
        color = if (punto.cambiado) ColoresActuales.current.naranja else null,
        fuerte = true,
        activa = libre && punto.editable,
    ) { valor ->
        eleccion.mover(punto.frecuencia, valor, menor, mayor)
    }
}

// -- la gráfica ------------------------------------------------------------------------------------------

/** Convierte entre puntos de la curva y lugares del dibujo. */
private class EscalaVoltaje(private val medida: Size, private val cuantos: Int, private val densidad: Density) {
    val izquierda = with(densidad) { 44.dp.toPx() }
    val derecha = with(densidad) { 20.dp.toPx() }
    private val arriba = with(densidad) { 26.dp.toPx() }
    private val abajo = with(densidad) { 30.dp.toPx() }
    private val alto = medida.height - arriba - abajo

    fun y(voltaje: Int): Float {
        return arriba + alto * (MAYOR_MV - voltaje) / (MAYOR_MV - MENOR_MV)
    }

    fun x(indice: Int): Float {
        return izquierda + (medida.width - izquierda - derecha) * indice / (cuantos - 1).coerceAtLeast(1)
    }

    fun voltaje(y: Float): Int {
        return (MAYOR_MV - (y - arriba) / alto * (MAYOR_MV - MENOR_MV)).roundToInt()
    }

    fun lugar(indice: Int, voltaje: Int): Offset {
        return Offset(x(indice), y(voltaje))
    }
}

@Composable
private fun CurvaVoltaje(
    puntos: List<PuntoVoltaje>,
    elegido: Int,
    libre: Boolean,
    alElegir: (Int) -> Unit,
    alMover: (Int, Int) -> Unit,
) {
    val paleta = ColoresActuales.current
    val medidor = rememberTextMeasurer()
    val eje = estiloTexto(11, color = paleta.sutil)
    val ejeElegido = estiloTexto(11, 700)
    val ejeRiesgo = estiloTexto(11, color = paleta.rojo)
    val actuales by rememberUpdatedState(puntos)
    val mover by rememberUpdatedState(alMover)
    val elegir by rememberUpdatedState(alElegir)
    val gestos = Modifier.pointerInput(libre) {
        fun escala() = EscalaVoltaje(Size(size.width.toFloat(), size.height.toFloat()), actuales.size, this)
        moverPuntos(
            lugares = { actuales.mapIndexed { indice, punto -> escala().lugar(indice, punto.propuesto) } },
            alElegir = { indice -> elegir(indice) },
            alMover = { indice, lugar ->
                val punto = actuales.getOrNull(indice)
                if (libre && punto != null && punto.editable) {
                    mover(punto.frecuencia, escala().voltaje(lugar.y))
                }
            },
        )
    }
    Canvas(Modifier.fillMaxWidth().height(AltoGrafica).then(gestos)) {
        val escala = EscalaVoltaje(size, puntos.size, this)
        for (marca in MENOR_MV..MAYOR_MV step 100) {
            val y = escala.y(marca)
            drawLine(paleta.bordeSuave, Offset(36.dp.toPx(), y), Offset(size.width - 8.dp.toPx(), y), 1.dp.toPx())
            dibujarTexto(medidor, marca.toString(), eje, Offset(30.dp.toPx(), y), Lado.ANTES)
        }
        dibujarTexto(medidor, "mV", eje, Offset(size.width - 8.dp.toPx(), 12.dp.toPx()), Lado.ANTES)
        if (puntos.any { punto -> punto.cambiado }) {
            dibujarLinea(puntos.mapIndexed { indice, punto -> escala.lugar(indice, punto.actual) }, paleta.bordeFuerte, punteada = true)
        }
        dibujarLinea(puntos.mapIndexed { indice, punto -> escala.lugar(indice, punto.propuesto) }, paleta.acento)
        for ((indice, punto) in puntos.withIndex()) {
            val color = when {
                indice == elegido -> paleta.texto
                punto.cambiado -> paleta.naranja
                punto.frecuencia > TECHO_SEGURO -> paleta.rojo
                else -> paleta.acento
            }
            dibujarPunto(escala.lugar(indice, punto.propuesto), indice == elegido, color)
            val junto = indice == elegido - 1 || indice == elegido + 1
            if (puntos.size <= CABEN_TODOS || indice == elegido || (indice % 2 == 0 && !junto)) {
                val estilo = if (indice == elegido) ejeElegido else if (punto.frecuencia > TECHO_SEGURO) ejeRiesgo else eje
                val lugar = Offset(escala.x(indice), size.height - 12.dp.toPx())
                dibujarTexto(medidor, punto.frecuencia.toString(), estilo, lugar, Lado.CENTRO)
            }
        }
    }
}

// -- opciones --------------------------------------------------------------------------------------------

private fun aumentos(): List<Triple<Int, String, String>> {
    return listOf(
        Triple(SIN_AUMENTO, t("Current"), t("No changes")),
        Triple(1, "+10 mV", t("Gentle")),
        Triple(2, "+20 mV", t("Moderate")),
        Triple(3, "+30 mV", t("High")),
        Triple(PERSONALIZADO, t("Custom"), t("Move each point in the chart or in the list")),
    )
}

@Composable
private fun OpcionesVoltaje(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionVoltaje, puntos: List<PuntoVoltaje>, libre: Boolean) {
    val movil = movil()
    val paleta = ColoresActuales.current
    val tareas = rememberCoroutineScope()
    val cambios = puntos.count { punto -> punto.cambiado }
    GrupoMovil {
        val nombre = aumentos().first { (nivel) -> nivel == eleccion.nivel }.second
        FilaAbrir(t("Curve boost"), valor = nombre, activa = libre) { movil.abrirHoja { HojaAumento(eleccion) } }
        val resumen = if (cambios > 0) t("{count} changed", "count" to cambios.toString()) else puntos.size.toString()
        FilaAbrir(t("All points"), valor = resumen, colorValor = if (cambios > 0) paleta.naranja else null) {
            movil.abrirHoja { HojaPuntos(datos, eleccion, libre) }
        }
    }
    GrupoMovil {
        FilaAbrir("config.toml", t("View the file")) { movil.abrirArchivo(aplicacion) }
        FilaAbrir(t("Restore governor defaults"), activa = libre) {
            tareas.launch { pedirVoltaje(aplicacion, SIN_AUMENTO, ObjetoVacio, ObjetoVacio) }
        }
        val altos = datos.objeto("high_frequency_points").logico("enabled")
        FilaAbrir(
            titulo = t("Points above 2000 MHz"),
            valor = t(if (altos) "Enabled" else "Locked"),
            colorTitulo = paleta.rojo,
            colorValor = if (altos) paleta.rojo else null,
            activa = libre && datos.objeto("availability").logico("high_points"),
        ) {
            movil.abrirHoja { HojaPuntosAltos(aplicacion, altos) }
        }
        FilaAbrir(t("Advanced GPU diagnostics")) {
            movil.abrirHoja {
                TituloHoja(t("Advanced GPU diagnostics"))
                DiagnosticosGpu(datos, datos.entero("current_min"), datos.entero("current_max"))
                CerrarHoja()
            }
        }
    }
}

@Composable
private fun HojaAumento(eleccion: EleccionVoltaje) {
    TituloHoja(t("Curve boost"))
    GrupoMovil {
        for ((nivel, nombre, detalle) in aumentos()) {
            FilaRadio(nombre, nivel == eleccion.nivel, detalle) { eleccion.elegirNivel(nivel) }
        }
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

@Composable
private fun HojaPuntos(datos: JsonObject, eleccion: EleccionVoltaje, libre: Boolean) {
    val menor = datos.entero("minimum_mv", MENOR_MV)
    val mayor = datos.entero("maximum_mv", MAYOR_MV)
    TituloHoja(t("All points"))
    GrupoMovil {
        for (punto in eleccion.puntos) {
            val detalle = t("Current") + " ${punto.actual} mV"
            FilaPunto(punto, "${punto.frecuencia} MHz", detalle, libre, menor, mayor, eleccion)
        }
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

@Composable
private fun HojaPuntosAltos(aplicacion: Aplicacion, activos: Boolean) {
    val movil = movil()
    TituloHoja(t("Points above 2000 MHz"))
    TextoHoja(
        t(
            "Uncomment the {extra_low}–{extra_high} MHz safe-points in config.toml (up to {voltage} mV). It " +
                "can hang the board or corrupt the SMU state.",
            "extra_low" to "2050",
            "extra_high" to "2400",
            "voltage" to "1150",
        ),
    )
    val titulo = t(if (activos) "Re-comment the +2000 MHz points" else "Uncomment +2000 MHz points")
    BotonMovil(titulo, Modifier.fillMaxWidth(), ClaseBoton.PELIGRO) {
        movil.cerrarHoja()
        pedirPuntosAltos(aplicacion, !activos)
    }
    CerrarHoja()
}

/** Enseña el archivo de configuración del gobernador. */
private fun EstadoMovil.abrirArchivo(aplicacion: Aplicacion) {
    abrirHoja {
        var archivo by remember { mutableStateOf(ObjetoVacio) }
        LaunchedEffect(Unit) {
            archivo = aplicacion.consultar("gpu.config")
        }
        TituloHoja(archivo.texto("path", t("Loading")))
        TextoConsola(archivo.texto("text", archivo.texto("error")), Modifier.fillMaxWidth())
        CerrarHoja()
    }
}

// -- Oberon ----------------------------------------------------------------------------------------------

@Composable
private fun VoltajeOberon(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    val extremos = listOf(datos.entero("current_min", 1000), datos.entero("current_max", TECHO_SEGURO))
    val puntos = extremos.map { frecuencia -> PuntoVoltaje(frecuencia, VOLTAJE_OBERON, VOLTAJE_OBERON, editable = false) }
    FranjaVoltaje(datos, VOLTAJE_OBERON, TECHO_SEGURO)
    GrupoMovil {
        CurvaVoltaje(puntos, elegido = -1, libre = false, alElegir = {}, alMover = { _, _ -> })
        FilaLibre {
            TextosFila(t("Lower endpoint"), "${extremos[0]} MHz")
            ValorConUnidad(VOLTAJE_OBERON.toString(), "mV")
        }
        FilaLibre {
            TextosFila(t("Upper endpoint"), "${extremos[1]} MHz")
            ValorConUnidad(VOLTAJE_OBERON.toString(), "mV")
        }
    }
    NotaMovil(
        t("Oberon uses two YAML endpoints. They are shown below for reference; curve editing is unavailable for this governor."),
        ColoresActuales.current.apagado,
        tamano = 13,
    )
    GrupoMovil {
        FilaAbrir("oberon-config.yaml", t("View the file")) { movil.abrirArchivo(aplicacion) }
    }
}

private const val VOLTAJE_OBERON = 1000
