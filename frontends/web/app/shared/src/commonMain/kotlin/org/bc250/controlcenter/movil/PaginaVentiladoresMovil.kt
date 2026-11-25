package org.bc250.controlcenter.movil

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.GuardarDocumentoSupervision
import org.bc250.controlcenter.componentes.Icono
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.numero
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.paginas.calibrarVentilador
import org.bc250.controlcenter.paginas.cambiarControlArranque
import org.bc250.controlcenter.paginas.herramientaVentilador
import org.bc250.controlcenter.paginas.puntosDe
import org.bc250.controlcenter.paginas.textoVentilador
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.chevron_right_gray
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

private const val LISTA = 0
private const val PERFILES = 1

/** Si ahora se pueden cambiar los ventiladores. */
fun ventiladoresLibres(aplicacion: Aplicacion, datos: JsonObject): Boolean {
    return aplicacion.puedeControlar && aplicacion.trabajo.terminado && !datos.logico("external")
}

@Composable
fun PaginaVentiladoresMovil(aplicacion: Aplicacion) {
    val movil = movil()
    val editor = remember { EdicionVentilador(aplicacion) }
    var perfil by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("fans")
            delay(2000)
        }
    }
    val datos = aplicacion.lectura("fans")
    val libre = ventiladoresLibres(aplicacion, datos)
    val perfiles = datos.objeto("profiles")
    val elegido = perfil.ifEmpty { perfiles.texto("active") }
    val enDetalle = movil.detalle.isNotEmpty()
    val canal = datos.objetos("channels").firstOrNull { opcion -> opcion.entero("pwm") == editor.numero }
    if (enDetalle && canal != null) {
        SeguirVentilador(aplicacion, editor, canal)
    }
    PaginaMovil(
        clave = "fans",
        pestanas = listOf(t("Fans"), t("Profiles"), t("Settings")),
        pie = when {
            enDetalle && canal != null -> { { BotonesVentilador(aplicacion, editor, canal, datos, libre) } }
            !enDetalle && movil.pestana("fans") == PERFILES -> {
                {
                    BotonMovil(t("Apply profile"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && elegido.isNotEmpty()) {
                        operarPerfil(aplicacion, "apply", "Apply profile", elegido, editor.numero)
                    }
                }
            }
            else -> null
        },
    ) {
        EstadoLecturaMovil(datos)
        when {
            enDetalle && canal != null -> DetalleVentilador(aplicacion, editor, canal, datos, libre)
            movil.pestana("fans") == LISTA -> ListaVentiladores(aplicacion, datos) { abierto ->
                editor.abrir(abierto)
                movil.abrirDetalle(nombreVentilador(abierto))
            }
            movil.pestana("fans") == PERFILES -> PerfilesVentilador(aplicacion, datos, elegido, editor, libre) { nuevo -> perfil = nuevo }
            else -> AjustesVentilador(aplicacion, datos, libre)
        }
    }
}

fun nombreVentilador(canal: JsonObject): String {
    return canal.texto("label").ifEmpty { canal.texto("short_header") }
}

private fun operarPerfil(aplicacion: Aplicacion, operacion: String, titulo: String, nombre: String, numero: Int) {
    val parametros = mutableMapOf("operation" to JsonPrimitive(operacion), "name" to JsonPrimitive(nombre))
    if (operacion == "apply") {
        parametros["selected"] = JsonPrimitive(numero)
    }
    aplicacion.preguntarYEjecutar("fan.profile", t(titulo), parametros = parametros)
}

// -- lista ---------------------------------------------------------------------------------------------

/** Un conector cuenta como ocupado si gira, si se controla o si tiene nombre. */
private fun estaOcupado(canal: JsonObject): Boolean {
    return (canal.numero("rpm") ?: 0.0) > 0 || canal.texto("mode", "firmware") != "firmware" || canal.texto("label").isNotEmpty()
}

@Composable
private fun ListaVentiladores(aplicacion: Aplicacion, datos: JsonObject, alAbrir: (JsonObject) -> Unit) {
    val movil = movil()
    val (ocupados, vacios) = datos.objetos("channels").partition(::estaOcupado)
    AvisosVentilador(aplicacion, datos)
    if (ocupados.isNotEmpty()) {
        GrupoMovil {
            for (canal in ocupados) {
                FilaVentilador(canal) { alAbrir(canal) }
            }
        }
    }
    GrupoMovil {
        val perfiles = datos.objeto("profiles")
        val activo = perfiles.texto("active").ifEmpty { if (perfiles.logico("custom")) "Custom" else "—" }
        FilaDato(t("Profile"), t(activo))
        val mayor = datos.objeto("temperatures").numero("hottest")
        FilaDato(t("Highest temperature"), mayor?.roundToInt()?.toString() ?: "--", "°C")
        FilaDato(t("Control from boot"), t(if (datos.objeto("service").logico("enabled")) "Enabled" else "Disabled"))
        FilaDato(t("Controller"), datos.texto("chip", "—"))
    }
    if (vacios.isNotEmpty()) {
        GrupoMovil {
            FilaAbrir(t("Headers without a fan"), valor = vacios.size.toString()) {
                val opciones = vacios.map { canal -> canal.texto("pwm") to nombreVentilador(canal) }
                movil.abrirLista(t("Headers without a fan"), opciones, "") { elegido ->
                    alAbrir(vacios.first { canal -> canal.texto("pwm") == elegido })
                }
            }
        }
    }
}

@Composable
private fun FilaVentilador(canal: JsonObject, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val sigue = if (canal.texto("mode") == "curve") " · " + textoVentilador(canal, "follows", "follows_values") else ""
    FilaLibre(altoMinimo = 76.dp, alPulsar = alPulsar) {
        Column(Modifier.weight(1f)) {
            TextoTitulo(nombreVentilador(canal), 19)
            val conector = canal.texto("short_header")
            val donde = if (conector == nombreVentilador(canal)) "" else "$conector · "
            Texto(donde + t(canal.texto("mode_label")) + sigue, tamano = 13, color = paleta.sutil)
        }
        Column(horizontalAlignment = Alignment.End) {
            ValorConUnidad(canal.texto("rpm", "—"), "RPM", tamano = 24)
            Texto(canal.texto("duty", "—") + " %", tamano = 12, color = paleta.apagado)
        }
        Icono(Res.drawable.chevron_right_gray, 14.dp)
    }
}

/** Lo que impide controlar los ventiladores o pide atención. */
@Composable
private fun AvisosVentilador(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val servicio = datos.objeto("service")
    if (datos.texto("driver").isNotEmpty()) {
        NotaMovil(t(datos.texto("driver")), paleta.naranja, tamano = 13)
        BotonMovil(t("Prepare PWM driver"), AnchoCompleto, ClaseBoton.ACENTO, libre) {
            herramientaVentilador(aplicacion, "prepare", "Prepare PWM driver")
        }
    }
    if (servicio.logico("out_of_date") || servicio.texto("state") == "override") {
        BotonMovil(t("Sync now"), AnchoCompleto, ClaseBoton.ACENTO, ventiladoresLibres(aplicacion, datos)) {
            val parametros = mapOf("operation" to JsonPrimitive("sync"))
            aplicacion.preguntarYEjecutar("fan.service", t("Control from boot"), parametros = parametros)
        }
    }
}

// -- perfiles --------------------------------------------------------------------------------------------

@Composable
private fun PerfilesVentilador(
    aplicacion: Aplicacion,
    datos: JsonObject,
    elegido: String,
    editor: EdicionVentilador,
    libre: Boolean,
    alElegir: (String) -> Unit,
) {
    val movil = movil()
    val perfiles = datos.objeto("profiles")
    val guardados = perfiles.textos("saved")
    SeccionMovil(t("Fan profiles")) {
        for (nombre in perfiles.textos("builtin") + guardados) {
            val curva = datos.objeto("builtin_curves")[nombre] as? JsonArray
            val puntos = if (curva == null) emptyList() else puntosDe(curva)
            TarjetaPerfilMovil(
                nombre = t(nombre),
                valor = "",
                detalle = if (puntos.isEmpty()) t("Saved profile") else resumenDe(puntos),
                elegido = nombre == elegido,
                activo = libre,
                adorno = { CurvaPequena(puntos) },
            ) {
                alElegir(nombre)
            }
        }
    }
    ParejaBotones {
        BotonMovil(t("Save as…"), Modifier.weight(1f), activo = libre) {
            movil.abrirHoja { HojaGuardarPerfil(aplicacion, editor, elegido, guardados) }
        }
        BotonMovil(t("Delete"), Modifier.weight(1f), ClaseBoton.PELIGRO_SUAVE, libre && elegido in guardados) {
            operarPerfil(aplicacion, "delete", "Delete profile", elegido, editor.numero)
        }
    }
}

private fun resumenDe(puntos: List<Pair<Int, Int>>): String {
    val (frio, lento) = puntos.first()
    val (caliente, rapido) = puntos.last()
    return t("{slow} % at {cold} °C · {fast} % at {hot} °C", "slow" to "$lento", "cold" to "$frio", "fast" to "$rapido", "hot" to "$caliente")
}

@Composable
private fun CurvaPequena(puntos: List<Pair<Int, Int>>) {
    if (puntos.isEmpty()) {
        return
    }
    val paleta = ColoresActuales.current
    Row {
        Canvas(Modifier.size(92.dp, 44.dp)) {
            fun lugar(temperatura: Int, velocidad: Int) = Offset((temperatura - 20) / 80f * size.width, size.height * (0.93f - velocidad / 100f * 0.86f))
            val linea = listOf(lugar(20, puntos.first().second)) + puntos.map { (temperatura, velocidad) -> lugar(temperatura, velocidad) } +
                lugar(100, puntos.last().second)
            val relleno = Path().apply {
                moveTo(0f, size.height)
                linea.forEach { punto -> lineTo(punto.x, punto.y) }
                lineTo(size.width, size.height)
                close()
            }
            drawPath(relleno, paleta.acento.copy(alpha = 0.14f))
            dibujarLinea(linea, paleta.acento)
        }
        Column(Modifier.size(12.dp)) {}
    }
}

@Composable
private fun HojaGuardarPerfil(aplicacion: Aplicacion, editor: EdicionVentilador, inicial: String, guardados: List<String>) {
    val movil = movil()
    var nombre by remember { mutableStateOf(if (inicial in guardados) inicial else "") }
    var reemplazar by remember { mutableStateOf(false) }
    TituloHoja(t("Save profile as…"))
    CampoMovil(nombre, AnchoCompleto, t("Profile name")) { nuevo -> nombre = nuevo.take(32) }
    GrupoMovil {
        FilaInterruptor(t("Replace fan profile?"), reemplazar) { valor -> reemplazar = valor }
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { movil.cerrarHoja() }
        BotonMovil(t("Save"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, nombre.isNotBlank()) {
            movil.cerrarHoja()
            editor.guardarPerfil(nombre, reemplazar)
        }
    }
}

// -- ajustes -----------------------------------------------------------------------------------------------

@Composable
private fun AjustesVentilador(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean) {
    val movil = movil()
    val servicio = datos.objeto("service")
    val encendido = servicio.logico("enabled")
    GrupoMovil {
        FilaInterruptor(
            titulo = t("Control from boot"),
            encendido = encendido,
            detalle = t("Follows the curve without signing in"),
            activa = libre && (servicio.logico("available") || encendido),
        ) { pedido ->
            cambiarControlArranque(aplicacion, pedido)
        }
    }
    GrupoMovil {
        FilaAbrir(t("Calibrate"), activa = libre) {
            movil.abrirHoja { HojaCalibrar(aplicacion, datos) }
        }
        FilaAbrir(t("Profiles in a file")) { movil.abrirHoja { HojaArchivos(aplicacion) } }
        FilaAbrir(t("Controller"), valor = datos.texto("chip", "—")) { movil.abrirHoja { HojaControlador(aplicacion, datos) } }
    }
}

@Composable
private fun HojaCalibrar(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    TituloHoja(t("Calibrate"))
    TextoHoja(t("Choose a fan. It takes one to two minutes and stops at once if the board reaches 80 °C."))
    GrupoMovil {
        for (canal in datos.objetos("channels").filter(::estaOcupado)) {
            val bomba = canal.objeto("entry").texto("role") == "pump"
            FilaAbrir(nombreVentilador(canal), canal.texto("short_header"), activa = canal.logico("writable") && !bomba) {
                movil.cerrarHoja()
                calibrarVentilador(aplicacion, canal.entero("pwm"))
            }
        }
    }
    CerrarHoja()
}

@Composable
private fun HojaArchivos(aplicacion: Aplicacion) {
    val movil = movil()
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    TituloHoja(t("Profiles in a file"))
    GrupoMovil {
        FilaAbrir(t("Import fan profiles"), activa = libre) { movil.abrirHoja { HojaImportar(aplicacion) } }
        FilaAbrir(t("Export fan profiles")) { movil.abrirDiagnostico(aplicacion, "export", "Export fan profiles") }
        FilaAbrir(t("Export to Decky"), activa = libre) {
            movil.cerrarHoja()
            herramientaVentilador(aplicacion, "decky", "Export to Decky")
        }
    }
    CerrarHoja()
}

@Composable
private fun HojaImportar(aplicacion: Aplicacion) {
    val movil = movil()
    var documento by remember { mutableStateOf("") }
    var reemplazar by remember { mutableStateOf(false) }
    TituloHoja(t("Import fan profiles"))
    AreaDeTexto(documento) { nuevo -> documento = nuevo }
    GrupoMovil {
        FilaInterruptor(t("Replace fan profile?"), reemplazar) { valor -> reemplazar = valor }
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { movil.cerrarHoja() }
        BotonMovil(t("Import"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, documento.isNotBlank()) {
            val parametros = mapOf("text" to JsonPrimitive(documento), "replace" to JsonPrimitive(reemplazar))
            aplicacion.guardar("fans.import", parametros, "fans")
            movil.cerrarHoja()
        }
    }
}

@Composable
private fun HojaControlador(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    fun usar(operacion: String, titulo: String) {
        movil.cerrarHoja()
        herramientaVentilador(aplicacion, operacion, titulo)
    }
    TituloHoja(t("Controller"))
    GrupoMovil {
        FilaDato(t("Chip"), datos.texto("chip", "—"))
        val cuentas = datos.objeto("counts")
        FilaDato(t("Fans"), t("{count} turning", "count" to cuentas.entero("turning").toString()))
    }
    GrupoMovil {
        FilaAbrir(t("PWM paths")) { movil.abrirDiagnostico(aplicacion, "paths", "PWM paths") }
        FilaAbrir(t("NCT fan controller status")) { movil.abrirDiagnostico(aplicacion, "status", "NCT fan controller status") }
    }
    GrupoMovil {
        for ((operacion, titulo) in listOf(
            "prepare" to "Prepare PWM driver",
            "readonly" to "Enable read-only NCT monitoring",
            "disable" to "Disable nct6687 PWM setup",
        )) {
            FilaAbrir(t(titulo), activa = libre) { usar(operacion, titulo) }
        }
        val externo = datos.logico("external")
        val titulo = if (externo) "Take control back" else "Hand off the fan"
        FilaAbrir(t(titulo), activa = libre) {
            movil.cerrarHoja()
            herramientaVentilador(aplicacion, "handoff", titulo, mapOf("enabled" to JsonPrimitive(!externo)))
        }
    }
    CerrarHoja()
}

/** Un texto de diagnóstico que prepara el equipo; las rutas llegan en varias partes. */
private fun EstadoMovil.abrirDiagnostico(aplicacion: Aplicacion, vista: String, titulo: String) {
    abrirHoja {
        var respuesta by remember { mutableStateOf(JsonObject(emptyMap())) }
        LaunchedEffect(Unit) {
            respuesta = aplicacion.consultar("fans.diagnostics", mapOf("view" to vista))
        }
        TituloHoja(t(titulo))
        val partes = respuesta.objetos("tabs")
        if (partes.isEmpty()) {
            DocumentoMovil(respuesta.texto("text", t("Loading")))
        }
        for (parte in partes) {
            TextoHoja(parte.texto("label"))
            DocumentoMovil(parte.texto("text"))
        }
        if (vista == "export" && respuesta.isNotEmpty()) {
            GuardarDocumentoSupervision(aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=fans")
        }
        CerrarHoja()
    }
}
