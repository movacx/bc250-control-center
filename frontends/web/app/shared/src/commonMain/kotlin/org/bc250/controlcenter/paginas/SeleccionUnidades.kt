package org.bc250.controlcenter.paginas

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto

private const val WGP_POR_FILA = 5

/** El estado de un par de unidades: encendido o no, y si el controlador lo trae de fábrica. */
private fun celda(elegida: Boolean, delControlador: Boolean): JsonObject {
    val (token, nombre) = when {
        elegida && delControlador -> "D+" to "ROUTED"
        elegida -> "S+" to "ROUTED"
        delControlador -> "D!" to "BLOCKED"
        else -> "--" to "OFF"
    }
    return JsonObject(mapOf("token" to JsonPrimitive(token), "label" to JsonPrimitive(nombre)))
}

/**
 * La tabla para las máscaras que se ven en este momento, sin esperar al servidor. De él solo se conserva
 * lo que decide: qué se puede hacer, el equilibrio y los registros. La regla de las celdas es la suya.
 */
fun seleccionInmediata(estado: JsonObject, delServidor: JsonObject, mascaras: List<Int>): JsonObject {
    if (estado.isEmpty()) {
        return ObjetoVacio
    }
    val vivas = mascarasCu(estado, "masks")
    val drivers = mascarasCu(estado, "driver_masks")
    val originales = delServidor.objetos("rows")
    val filas = mascaras.mapIndexed { fila, mascara ->
        val celdas = List(WGP_POR_FILA) { wgp ->
            val bit = 1 shl wgp
            celda(mascara and bit != 0, drivers[fila] and bit != 0)
        }
        val cambios = mapOf(
            "name" to JsonPrimitive("SE${fila / 2}.SH${fila % 2}"),
            "cells" to JsonArray(celdas),
            "count" to JsonPrimitive("${mascara.countOneBits() * 2} / 10"),
            "target" to JsonPrimitive("0x" + mascara.toString(16).padStart(2, '0')),
        )
        JsonObject((originales.getOrNull(fila) ?: ObjetoVacio) + cambios)
    }
    val pendientes = mascaras.indices.sumOf { fila -> (mascaras[fila] xor vivas[fila]).countOneBits() }
    return JsonObject(
        delServidor + mapOf(
            "rows" to JsonArray(filas),
            "pending" to JsonPrimitive(pendientes),
            "target" to JsonPrimitive(mascaras.sumOf { mascara -> mascara.countOneBits() * 2 }),
        ),
    )
}

private const val ESPERA_CONSULTA = 60L

/**
 * Lo que se está eligiendo en la tabla. Mientras no haya un borrador se ve la tabla viva, así que una lectura
 * nueva cambia todo a la vez y nunca pasa por un estado intermedio.
 */
@Stable
class EleccionUnidades(private val aplicacion: Aplicacion) {
    private var borrador by mutableStateOf<List<Int>?>(null)
    /** Lo que opinó el servidor y de qué máscaras. */
    private var respuesta by mutableStateOf<Pair<List<Int>, JsonObject>?>(null)

    val datos: JsonObject get() = aplicacion.lectura("cu")
    val estado: JsonObject get() = datos.objeto("cu")
    val vivas: List<Int> by derivedStateOf { mascarasCu(estado, "masks") }
    val delKernel: Boolean get() = estado.logico("kernel_managed")
    val editada: Boolean get() = borrador != null
    val mascaras: List<Int> get() = borrador ?: vivas
    val libre: Boolean
        get() = aplicacion.puedeControlar && aplicacion.trabajo.terminado && datos.isNotEmpty() && datos.texto("error").isEmpty()

    val seleccion: JsonObject by derivedStateOf {
        val opinion = respuesta?.takeIf { (pedidas, _) -> pedidas == borrador }?.second ?: datos.objeto("selection")
        seleccionInmediata(estado, opinion, mascaras)
    }

    fun permite(accion: String): Boolean {
        if (accion == "discard") {
            return libre && editada
        }
        // Con un borrador solo se aplica lo que el servidor ya revisó: el mensaje describe esas mismas máscaras.
        val revisada = borrador == null || respuesta?.first == borrador
        return libre && revisada && seleccion.objeto("availability").logico(accion)
    }

    /** Si se puede escribir en la tabla: el kernel no la administra y no hay otra operación. */
    val editable: Boolean get() = libre && !delKernel

    fun elegir(nuevas: List<Int>) {
        borrador = if (nuevas == vivas) null else nuevas
    }

    fun alternar(fila: Int, wgp: Int) {
        if (editable) {
            elegir(mascaras.mapIndexed { indice, mascara -> if (indice == fila) mascara xor (1 shl wgp) else mascara })
        }
    }

    fun restablecer() {
        borrador = null
        respuesta = null
    }

    fun enJson(): JsonArray {
        return JsonArray(mascaras.map { mascara -> JsonPrimitive(mascara) })
    }

    /** Pregunta al servidor qué se puede hacer con el borrador; la tabla ya se ve como quedará. */
    suspend fun consultar() {
        delay(ESPERA_CONSULTA)
        val pedidas = mascaras
        val nueva = aplicacion.consultar("cu.selection", mapOf("masks" to enJson().toString()))
        if (nueva.isNotEmpty()) {
            respuesta = pedidas to nueva
        }
    }

    /** Pregunta con el texto del escritorio y, si se acepta, ejecuta. */
    fun operar(accion: String, clave: String, titulo: String, parametros: Map<String, JsonElement>, peligro: Boolean) {
        val texto = datos.objeto("confirmations").objeto(clave)
        val mensaje = texto.texto("message") + "\n" + seleccion.texto("summary")
        aplicacion.preguntarYEjecutar(accion, texto.texto("title", t(titulo)), mensaje, parametros, peligro)
    }

    fun operarTabla(guardar: Boolean) {
        val parametros = mapOf("masks" to enJson())
        if (guardar) {
            operar("cu.save", "save", "Save selection", parametros, peligro = true)
        } else {
            operar("cu.apply", "apply", "Apply now", parametros, peligro = true)
        }
    }

    fun operarServicio(nombre: String, titulo: String, peligro: Boolean = false) {
        operar("cu.action", nombre, titulo, mapOf("name" to JsonPrimitive(nombre)), peligro)
    }
}

/** La elección de la página, al día con las lecturas y con la operación que termina. */
@Composable
fun recordarEleccionUnidades(aplicacion: Aplicacion): EleccionUnidades {
    val eleccion = remember(aplicacion) { EleccionUnidades(aplicacion) }
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("cu")
            aplicacion.pausar(3000)
        }
    }
    LaunchedEffect(eleccion.mascaras, eleccion.vivas) {
        if (eleccion.editada) {
            eleccion.consultar()
        }
    }
    // La operación publica su final junto con la lectura nueva: el borrador se suelta cuando la tabla ya es otra.
    var visto by remember { mutableIntStateOf(aplicacion.trabajo.id) }
    LaunchedEffect(aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (aplicacion.trabajo.terminado && aplicacion.trabajo.id != visto) {
            visto = aplicacion.trabajo.id
            if (aplicacion.trabajo.correcto) {
                eleccion.restablecer()
            }
        }
    }
    return eleccion
}
