package org.bc250.controlcenter.movil

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.numero
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.paginas.aplicarVentilador
import org.bc250.controlcenter.paginas.cambiarModo
import org.bc250.controlcenter.paginas.conCampo
import org.bc250.controlcenter.paginas.curvaInicial
import org.bc250.controlcenter.paginas.datosDe
import org.bc250.controlcenter.paginas.entradaDelEditor
import org.bc250.controlcenter.paginas.puntosDe
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

private const val PUNTOS_MENOS = 2
private const val PUNTOS_MAS = 8
private const val MEZCLA_MENOS = 2
private const val MEZCLA_MAS = 4
private const val TEMPERATURA_MAYOR = 120

private typealias Punto = Pair<Int, Int>

/** Los cambios de un ventilador que todavía no se aplicaron. */
class EdicionVentilador(private val aplicacion: Aplicacion) {
    var numero by mutableStateOf(0)
        private set
    var entrada by mutableStateOf(ObjetoVacio)
    var nombre by mutableStateOf("")
    var punto by mutableStateOf(0)
    var curva by mutableStateOf(0)
    var validacion by mutableStateOf(ObjetoVacio)
    var intento by mutableStateOf(-1)
    var reintentar by mutableStateOf(false)

    val modo: String get() = entrada.texto("mode", "firmware")
    val enviada: JsonObject get() = entradaDelEditor(entrada)
    private val normalizada: JsonObject get() = validacion.objeto("entry").ifEmpty { enviada }.let { JsonObject(it) }

    fun abrir(canal: JsonObject) {
        numero = canal.entero("pwm")
        validacion = ObjetoVacio
        intento = -1
        reintentar = false
        volver(canal)
    }

    /** Deja todo como está guardado. */
    fun volver(canal: JsonObject) {
        val guardada = canal.objeto("entry")
        entrada = cambiarModo(guardada, guardada.texto("mode", "firmware"))
        nombre = canal.texto("label")
        punto = 0
        curva = 0
    }

    fun cambiado(canal: JsonObject): Boolean {
        return normalizada != canal.objeto("entry") || nombre != canal.texto("label")
    }

    fun cambiar(clave: String, valor: JsonElement) {
        entrada = entrada.conCampo(clave, valor)
    }

    fun elegirModo(nuevo: String) {
        entrada = cambiarModo(entrada, nuevo)
        punto = 0
    }

    // La curva que se ve: la única en modo Curva o la elegida en modo Mezcla.

    private val mezcla: List<JsonObject> get() = entrada.objetos("mix")
    private val curvaActual: JsonObject
        get() = if (modo == "mix") mezcla.getOrNull(curva) ?: ObjetoVacio else entrada

    val fuente: String get() = curvaActual.texto("source", "hottest")
    val puntos: List<Punto> get() = puntosDe(curvaActual["points"] as? JsonArray ?: curvaInicial())
    val nombresDeMezcla: List<String> get() = mezcla.mapIndexed { indice, parte -> "${indice + 1} · " + nombreDeFuente(parte.texto("source")) }

    private fun cambiarCurva(clave: String, valor: JsonElement) {
        if (modo != "mix") {
            cambiar(clave, valor)
            return
        }
        val nueva = mezcla.mapIndexed { indice, parte -> if (indice == curva) parte.conCampo(clave, valor) else parte }
        cambiar("mix", JsonArray(nueva))
    }

    fun elegirFuente(nueva: String) {
        cambiarCurva("source", JsonPrimitive(nueva))
    }

    fun agregarCurva() {
        val nueva = buildJsonObject {
            put("source", "cpu")
            put("points", curvaInicial())
        }
        cambiar("mix", JsonArray(mezcla + nueva))
        curva = mezcla.lastIndex
        punto = 0
    }

    fun quitarCurva() {
        cambiar("mix", JsonArray(mezcla.filterIndexed { indice, _ -> indice != curva }))
        curva = 0
        punto = 0
    }

    fun moverPunto(indice: Int, temperatura: Int, velocidad: Int) {
        val lista = puntos
        val menor = if (indice == 0) 0 else lista[indice - 1].first + 1
        val mayor = if (indice == lista.lastIndex) TEMPERATURA_MAYOR else lista[indice + 1].first - 1
        if (menor > mayor) {
            return
        }
        val nuevo = temperatura.coerceIn(menor, mayor) to velocidad.coerceIn(0, 100)
        cambiarCurva("points", datosDe(lista.mapIndexed { lugar, punto -> if (lugar == indice) nuevo else punto }))
    }

    fun quitarPunto() {
        cambiarCurva("points", datosDe(puntos.filterIndexed { indice, _ -> indice != punto }))
        punto = punto.coerceAtMost(puntos.lastIndex)
    }

    /** Añade un punto en medio del hueco más ancho. */
    fun agregarPunto() {
        val lista = puntos
        val antes = (0 until lista.lastIndex).maxByOrNull { indice -> lista[indice + 1].first - lista[indice].first } ?: return
        val medio = (lista[antes].first + lista[antes + 1].first) / 2
        if (lista.any { (temperatura, _) -> temperatura == medio }) {
            return
        }
        cambiarCurva("points", datosDe(lista + (medio to (lista[antes].second + lista[antes + 1].second) / 2)))
        punto = antes + 1
    }

    fun guardarPerfil(nombre: String, reemplazar: Boolean) {
        val parametros = mutableMapOf<String, JsonElement>(
            "operation" to JsonPrimitive("save"),
            "name" to JsonPrimitive(nombre),
            "replace" to JsonPrimitive(reemplazar),
        )
        if (entrada.isNotEmpty() && numero > 0) {
            parametros["draft"] = JsonObject(mapOf("pwm" to JsonPrimitive(numero), "entry" to enviada))
        }
        aplicacion.preguntarYEjecutar("fan.profile", t("Save profile as…"), parametros = parametros)
    }
}

/** Comprueba en el equipo lo que se va cambiando y recoge lo que se aplica desde otro sitio. */
@Composable
fun SeguirVentilador(aplicacion: Aplicacion, editor: EdicionVentilador, canal: JsonObject) {
    val enviada = editor.enviada
    LaunchedEffect(editor.numero, enviada) {
        editor.validacion = ObjetoVacio
        delay(180)
        val respuesta = aplicacion.consultar("fans.validate", mapOf("entry" to enviada.toString()))
        editor.validacion = respuesta.ifEmpty { mapOf("error" to JsonPrimitive(t("Not connected"))) }.let { JsonObject(it) }
    }
    val trabajo = aplicacion.trabajo
    LaunchedEffect(trabajo.id, trabajo.terminado, canal.objeto("entry")) {
        if (editor.intento >= 0 && trabajo.id > editor.intento && trabajo.terminado) {
            editor.reintentar = !trabajo.correcto
            if (trabajo.correcto) {
                editor.intento = -1
                editor.volver(canal)
            }
        }
    }
}

@Composable
fun RowScope.BotonesVentilador(aplicacion: Aplicacion, editor: EdicionVentilador, canal: JsonObject, datos: JsonObject, libre: Boolean) {
    val cambiado = editor.cambiado(canal)
    val reanudar = canal.logico("resume") && !cambiado
    val texto = t(if (reanudar) "Resume" else if (editor.reintentar && !cambiado) "Retry" else "Apply")
    BotonMovil(t("Revert"), Modifier.weight(1f), activo = cambiado) { editor.volver(canal) }
    val puede = libre && (cambiado || editor.reintentar || reanudar) && editor.validacion.logico("valid")
    BotonMovil(texto, Modifier.weight(1f), ClaseBoton.PRINCIPAL, puede) {
        editor.intento = aplicacion.trabajo.id
        val forzar = editor.reintentar || reanudar
        aplicarVentilador(aplicacion, editor.numero, editor.enviada, editor.nombre, texto, forzar, datos.entero("low_duty", 30))
    }
}

// -- detalle ---------------------------------------------------------------------------------------------

@Composable
fun DetalleVentilador(aplicacion: Aplicacion, editor: EdicionVentilador, canal: JsonObject, datos: JsonObject, libre: Boolean) {
    val paleta = ColoresActuales.current
    val conCurva = editor.modo == "curve" || editor.modo == "mix"
    val temperatura = datos.objeto("temperatures").numero(if (conCurva) editor.fuente else "hottest")
    FranjaLecturas(
        LecturaFranja(t("Speed"), canal.texto("rpm", "—"), "RPM"),
        LecturaFranja(t("Output"), canal.texto("duty", "—"), "%"),
        LecturaFranja(t("Temperature"), temperatura?.roundToInt()?.toString() ?: "--", "°C"),
    )
    val modos = listOf("firmware" to "BIOS", "fixed" to t("Fixed"), "curve" to t("Curve"), "mix" to t("Mix"))
    SegmentadoMovil(modos, editor.modo, libre) { modo -> editor.elegirModo(modo) }
    when (editor.modo) {
        "firmware" -> NotaMovil(
            t("The BIOS fan curve drives this header. BC250 Control Center does not write to it."),
            paleta.apagado,
            tamano = 13,
        )
        "fixed" -> VelocidadFija(editor, datos, libre)
        else -> CurvaDelVentilador(editor, canal, temperatura, libre)
    }
    Calibracion(editor, datos, libre)
    for ((texto, color) in listOf(editor.validacion.texto("error") to paleta.rojo, canal.texto("fault") to paleta.naranja)) {
        if (texto.isNotEmpty()) {
            NotaMovil(texto, color)
        }
    }
    OpcionesVentilador(editor, canal, libre, conCurva)
}

@Composable
private fun VelocidadFija(editor: EdicionVentilador, datos: JsonObject, libre: Boolean) {
    val velocidad = editor.entrada.entero("percent", 60)
    fun elegir(nueva: Int) {
        editor.cambiar("percent", JsonPrimitive(nueva))
    }
    GrupoMovil {
        Box(Modifier.fillMaxWidth().padding(14.dp)) {
            DeslizadorMovil(t("Speed"), velocidad, "%", 0, 100, libre, ::elegir)
        }
        val rapidas = datos.objetos("speed_profiles").map { perfil -> perfil.entero("percent") }
        if (rapidas.isNotEmpty()) {
            val acciones = rapidas.map { valor -> AccionTira("$valor %", libre) { elegir(valor) } }
            TiraAcciones(*acciones.toTypedArray())
        }
    }
    if (velocidad < datos.entero("low_duty", 30)) {
        NotaMovil(t("A fan this slow can let the board overheat under load."), ColoresActuales.current.naranja)
    }
}

@Composable
private fun CurvaDelVentilador(editor: EdicionVentilador, canal: JsonObject, temperatura: Double?, libre: Boolean) {
    val paleta = ColoresActuales.current
    if (editor.modo == "mix") {
        val movil = movil()
        val nombres = editor.nombresDeMezcla
        GrupoMovil {
            FilaAbrir(t("Curve"), valor = nombres.getOrElse(editor.curva) { "" }) {
                movil.abrirLista(t("Curve"), nombres.mapIndexed { indice, nombre -> "$indice" to nombre }, "${editor.curva}") { elegida ->
                    editor.curva = elegida.toInt()
                    editor.punto = 0
                }
            }
            TiraAcciones(
                AccionTira(t("Remove curve"), libre && nombres.size > MEZCLA_MENOS) { editor.quitarCurva() },
                AccionTira(t("Add curve"), libre && nombres.size < MEZCLA_MAS) { editor.agregarCurva() },
            )
        }
    }
    val puntos = editor.puntos
    val indice = editor.punto.coerceIn(0, puntos.lastIndex.coerceAtLeast(0))
    val (grados, velocidad) = puntos.getOrElse(indice) { 0 to 0 }
    GrupoMovil {
        GraficaCurva(puntos, indice, temperatura, canal.numero("duty"), libre, { editor.punto = it }) { lugar, nuevo ->
            editor.moverPunto(lugar, nuevo.first, nuevo.second)
        }
        FilaLibre {
            val texto = t("Point {number} of {total}", "number" to "${indice + 1}", "total" to "${puntos.size}")
            Texto(texto, tamano = 13, color = paleta.apagado, modifier = Modifier.weight(1f))
            EnlaceMovil(t("Remove"), libre && puntos.size > PUNTOS_MENOS) { editor.quitarPunto() }
            EnlaceMovil(t("Add"), libre && puntos.size < PUNTOS_MAS) { editor.agregarPunto() }
        }
        FilaPaso(t("Temperature"), grados, "°C", 0, TEMPERATURA_MAYOR, activa = libre) { valor ->
            editor.moverPunto(indice, valor, velocidad)
        }
        FilaPaso(t("Speed"), velocidad, "%", 0, 100, activa = libre) { valor -> editor.moverPunto(indice, grados, valor) }
    }
}

// -- la gráfica de la curva ----------------------------------------------------------------------------------

/** Convierte entre grados y velocidad y lugares del dibujo. */
private class EscalaCurva(private val medida: Size, val menor: Int, val mayor: Int, densidad: Density) {
    private val izquierda = with(densidad) { 34.dp.toPx() }
    private val derecha = with(densidad) { 14.dp.toPx() }
    private val arriba = with(densidad) { 24.dp.toPx() }
    private val abajo = with(densidad) { 30.dp.toPx() }
    private val ancho = medida.width - izquierda - derecha
    private val alto = medida.height - arriba - abajo

    fun x(temperatura: Number): Float = izquierda + ancho * (temperatura.toFloat() - menor) / (mayor - menor)

    fun y(velocidad: Number): Float = arriba + alto * (1f - velocidad.toFloat() / 100f)

    fun lugar(punto: Punto): Offset = Offset(x(punto.first), y(punto.second))

    fun punto(lugar: Offset): Punto {
        val grados = menor + (lugar.x - izquierda) / ancho * (mayor - menor)
        val velocidad = (1f - (lugar.y - arriba) / alto) * 100
        return grados.roundToInt() to velocidad.roundToInt()
    }
}

/** De 20 a 100 °C; si algún punto queda fuera, la escala completa. */
private fun escalaPara(puntos: List<Punto>, medida: Size, densidad: Density): EscalaCurva {
    val fuera = puntos.any { (temperatura, _) -> temperatura < 20 || temperatura > 100 }
    return if (fuera) EscalaCurva(medida, 0, TEMPERATURA_MAYOR, densidad) else EscalaCurva(medida, 20, 100, densidad)
}

@Composable
private fun GraficaCurva(
    puntos: List<Punto>,
    elegido: Int,
    temperatura: Double?,
    salida: Double?,
    libre: Boolean,
    alElegir: (Int) -> Unit,
    alMover: (Int, Punto) -> Unit,
) {
    val paleta = ColoresActuales.current
    val medidor = rememberTextMeasurer()
    val eje = estiloTexto(11, color = paleta.sutil)
    val ahora = estiloTexto(11, color = paleta.apagado)
    val ahoraTexto = t("now")
    val actuales by rememberUpdatedState(puntos)
    val elegir by rememberUpdatedState(alElegir)
    val mover by rememberUpdatedState(alMover)
    val gestos = Modifier.pointerInput(libre) {
        fun escala() = escalaPara(actuales, Size(size.width.toFloat(), size.height.toFloat()), this)
        moverPuntos(
            lugares = { actuales.map { punto -> escala().lugar(punto) } },
            alElegir = { indice -> elegir(indice) },
            alMover = { indice, lugar -> if (libre) mover(indice, escala().punto(lugar)) },
        )
    }
    Canvas(Modifier.fillMaxWidth().height(230.dp).then(gestos)) {
        val escala = escalaPara(puntos, size, this)
        for (marca in 0..100 step 25) {
            val y = escala.y(marca)
            drawLine(paleta.bordeSuave, Offset(escala.x(escala.menor), y), Offset(escala.x(escala.mayor), y), 1.dp.toPx())
            dibujarTexto(medidor, "$marca", eje, Offset(26.dp.toPx(), y), Lado.ANTES)
        }
        for (marca in escala.menor..escala.mayor step 20) {
            val lado = if (marca == escala.mayor) Lado.ANTES else Lado.CENTRO
            dibujarTexto(medidor, "$marca °C", eje, Offset(escala.x(marca), size.height - 12.dp.toPx()), lado)
        }
        if (temperatura != null) {
            val x = escala.x(temperatura.coerceIn(escala.menor.toDouble(), escala.mayor.toDouble()))
            drawLine(paleta.bordeFuerte, Offset(x, escala.y(100)), Offset(x, escala.y(0)), 1.dp.toPx())
            val texto = ahoraTexto + " ${temperatura.roundToInt()} °C" + if (salida == null) "" else " · ${salida.roundToInt()} %"
            // A la izquierda de la línea, donde la curva todavía va baja; si no cabe, a la derecha.
            val cabe = x > size.width / 2
            val margen = if (cabe) -6.dp.toPx() else 6.dp.toPx()
            dibujarTexto(medidor, texto, ahora, Offset(x + margen, escala.y(100) + 8.dp.toPx()), if (cabe) Lado.ANTES else Lado.DESPUES)
        }
        if (puntos.isNotEmpty()) {
            val linea = listOf(Offset(escala.x(escala.menor), escala.y(puntos.first().second))) + puntos.map { punto -> escala.lugar(punto) } +
                Offset(escala.x(escala.mayor), escala.y(puntos.last().second))
            dibujarLinea(linea, paleta.acento)
        }
        for ((indice, punto) in puntos.withIndex()) {
            dibujarPunto(escala.lugar(punto), indice == elegido, if (indice == elegido) paleta.texto else paleta.acento)
        }
    }
}

// -- opciones de un ventilador ---------------------------------------------------------------------------------

/** Los valores de la respuesta, del más lento al más rápido. */
private class Respuesta(val nombre: String, val detalle: String, val histeresis: Double, val retardo: Double, val sube: Int, val baja: Int)

private fun respuestas(): List<Respuesta> {
    return listOf(
        Respuesta(t("Smooth"), t("Changes slowly and makes less noise"), 5.0, 4.0, 5, 2),
        Respuesta(t("Normal"), t("Balance between noise and temperature"), 1.0, 0.0, 100, 10),
        Respuesta(t("Fast"), t("Reacts to heat at once"), 1.0, 0.0, 100, 30),
    )
}

private fun JsonObject.esRespuesta(respuesta: Respuesta): Boolean {
    return (numero("hysteresis_c") ?: 1.0) == respuesta.histeresis &&
        (numero("response_delay_seconds") ?: 0.0) == respuesta.retardo &&
        entero("max_up_step_percent", 100) == respuesta.sube &&
        entero("max_down_step_percent", 10) == respuesta.baja
}

private fun nombreRespuesta(entrada: JsonObject): String {
    return respuestas().firstOrNull { respuesta -> entrada.esRespuesta(respuesta) }?.nombre ?: t("Custom")
}

private fun fuentes(): List<Pair<String, String>> {
    return listOf("hottest", "cpu", "gpu", "vrm", "board").map { fuente -> fuente to nombreDeFuente(fuente) }
}

fun nombreDeFuente(fuente: String): String {
    return when (fuente) {
        "hottest" -> t("Hottest chip")
        "board" -> t("Board")
        else -> fuente.uppercase()
    }
}

@Composable
private fun OpcionesVentilador(editor: EdicionVentilador, canal: JsonObject, libre: Boolean, conCurva: Boolean) {
    val movil = movil()
    val entrada = editor.entrada
    GrupoMovil {
        if (conCurva) {
            FilaAbrir(t("Follows"), valor = nombreDeFuente(editor.fuente), activa = libre) {
                movil.abrirLista(t("Follows"), fuentes(), editor.fuente) { fuente -> editor.elegirFuente(fuente) }
            }
            FilaAbrir(t("Response"), valor = nombreRespuesta(entrada), activa = libre) { movil.abrirHoja { HojaRespuesta(editor) } }
            val limites = "${entrada.entero("min_percent")} – ${entrada.entero("max_percent", 100)} %"
            FilaAbrir(t("Limits"), valor = limites, activa = libre) { movil.abrirHoja { HojaLimites(editor) } }
        }
        FilaAbrir(t("Name and role"), valor = editor.nombre.ifEmpty { canal.texto("short_header") }, activa = libre) {
            movil.abrirHoja { HojaNombre(editor) }
        }
        if (editor.modo != "firmware") {
            FilaInterruptor(t("Warn when the fan stops while it should turn"), entrada.logico("stall_detect", true), activa = libre) { valor ->
                editor.cambiar("stall_detect", JsonPrimitive(valor))
            }
        }
    }
}

@Composable
private fun HojaRespuesta(editor: EdicionVentilador) {
    val elegida = respuestas().firstOrNull { respuesta -> editor.entrada.esRespuesta(respuesta) }
    var exacta by remember { mutableStateOf(elegida == null) }
    TituloHoja(t("Response"))
    GrupoMovil {
        for (respuesta in respuestas()) {
            FilaRadio(respuesta.nombre, !exacta && elegida?.nombre == respuesta.nombre, respuesta.detalle) {
                exacta = false
                editor.cambiar("hysteresis_c", JsonPrimitive(respuesta.histeresis))
                editor.cambiar("response_delay_seconds", JsonPrimitive(respuesta.retardo))
                editor.cambiar("max_up_step_percent", JsonPrimitive(respuesta.sube))
                editor.cambiar("max_down_step_percent", JsonPrimitive(respuesta.baja))
            }
        }
        FilaRadio(t("Custom"), exacta, t("Exact values")) { exacta = true }
    }
    if (exacta) {
        GrupoMovil {
            PasoDecimal(editor, "Hysteresis", "hysteresis_c", "°C", 1.0, 10)
            PasoDecimal(editor, "Response delay", "response_delay_seconds", "s", 0.0, 30)
            PasoPorcentaje(editor, "Largest step up", "max_up_step_percent", 100, minimo = 1)
            PasoPorcentaje(editor, "Largest step down", "max_down_step_percent", 10, minimo = 1)
        }
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

@Composable
private fun HojaLimites(editor: EdicionVentilador) {
    TituloHoja(t("Limits"))
    GrupoMovil {
        PasoPorcentaje(editor, "Minimum PWM", "min_percent", 0, paso = 5)
        PasoPorcentaje(editor, "Maximum PWM", "max_percent", 100, paso = 5)
        PasoPorcentaje(editor, "Spin-up kick", "start_percent", 0, paso = 5)
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

@Composable
private fun PasoPorcentaje(editor: EdicionVentilador, titulo: String, clave: String, defecto: Int, minimo: Int = 0, paso: Int = 1) {
    FilaPaso(t(titulo), editor.entrada.entero(clave, defecto), "%", minimo, 100, paso) { valor ->
        editor.cambiar(clave, JsonPrimitive(valor))
    }
}

@Composable
private fun PasoDecimal(editor: EdicionVentilador, titulo: String, clave: String, unidad: String, defecto: Double, mayor: Int) {
    val valor = (editor.entrada.numero(clave) ?: defecto).roundToInt()
    FilaPaso(t(titulo), valor, unidad, 0, mayor) { nuevo -> editor.cambiar(clave, JsonPrimitive(nuevo.toDouble())) }
}

@Composable
private fun HojaNombre(editor: EdicionVentilador) {
    val rol = editor.entrada.texto("role", "fan")
    TituloHoja(t("Name and role"))
    CampoMovil(editor.nombre, AnchoCompleto, t("Name this fan")) { nuevo -> editor.nombre = nuevo.take(40) }
    if (editor.modo != "firmware") {
        GrupoMovil {
            FilaRadio(t("Fan"), rol == "fan") { editor.cambiar("role", JsonPrimitive("fan")) }
            FilaRadio(t("Pump"), rol == "pump") {
                editor.cambiar("role", JsonPrimitive("pump"))
                editor.cambiar("min_percent", JsonPrimitive(50))
            }
        }
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

/** Lo que encontró la calibración, para usarlo si se quiere. */
@Composable
private fun Calibracion(editor: EdicionVentilador, datos: JsonObject, libre: Boolean) {
    val calibracion = datos.objeto("calibration")
    if (calibracion.isEmpty() || calibracion.entero("pwm") != editor.numero || calibracion.texto("aborted").isNotEmpty()) {
        return
    }
    BotonMovil(t("Calibration finished"), AnchoCompleto, ClaseBoton.ACENTO, libre) {
        editor.elegirModo("curve")
        editor.cambiar("min_percent", JsonPrimitive(calibracion.entero("proposed_min")))
        editor.cambiar("start_percent", JsonPrimitive(calibracion.entero("proposed_start")))
    }
}
