package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales

@Composable
fun PaginaVentiladores(aplicacion: Aplicacion) {
    var seleccionado by remember { mutableStateOf(0) }
    var perfil by remember { mutableStateOf("Balanced") }
    var mas by remember { mutableStateOf(false) }
    var borrador by remember { mutableStateOf(ObjetoVacio) }
    var nombreBorrador by remember { mutableStateOf("") }
    var pendiente by remember { mutableStateOf<Int?>(null) }
    var aplicandoCambio by remember { mutableStateOf(false) }
    var trabajoAnterior by remember { mutableStateOf(-1) }
    var cambiado by remember { mutableStateOf(false) }
    var primeraLectura by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("fans")
            primeraLectura = true
            delay(2000)
        }
    }
    val datos = aplicacion.lectura("fans")
    val canales = datos.objetos("channels")
    val canal = canales.firstOrNull { it.entero("pwm") == seleccionado } ?: canales.firstOrNull() ?: ObjetoVacio
    val numero = canal.entero("pwm")
    val servicio = datos.objeto("service")
    val disponible = aplicacion.puedeControlar && aplicacion.trabajo.terminado && !datos.logico("external")
    fun elegir(nuevo: Int) {
        if (nuevo == numero) return
        if (cambiado) pendiente = nuevo else seleccionado = nuevo
    }
    LaunchedEffect(aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (aplicandoCambio && aplicacion.trabajo.id > trabajoAnterior && aplicacion.trabajo.terminado) {
            aplicandoCambio = false
            if (aplicacion.trabajo.correcto) {
                seleccionado = pendiente ?: numero
                pendiente = null
                cambiado = false
            }
        }
    }
    LaunchedEffect(aplicacion.aviso) {
        if (aplicandoCambio && aplicacion.aviso?.error == true) aplicandoCambio = false
    }
    MarcoSupervision { alto ->
        FranjaSupervision(izquierda = {
            val opciones = datos.objeto("profiles").textos("builtin") + datos.objeto("profiles").textos("saved")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Texto(t("Profile"), 12, color = ColoresActuales.current.apagado)
                SelectorSupervision(opciones.map { Eleccion(it, t(it)) }, perfil, modifier = Modifier.width(120.dp)) { perfil = it }
            }
            AccionSupervision(t("Apply profile"), disponible && opciones.isNotEmpty(), primaria = true) {
                aplicacion.preguntarYEjecutar("fan.profile", t("Apply profile"), parametros = mapOf(
                    "operation" to JsonPrimitive("apply"), "name" to JsonPrimitive(perfil), "selected" to JsonPrimitive(numero)))
            }
            AccionSupervision(t("Delete profile"), disponible && perfil in datos.objeto("profiles").textos("saved")) {
                aplicacion.preguntarYEjecutar("fan.profile", t("Delete profile"), parametros = mapOf(
                    "operation" to JsonPrimitive("delete"), "name" to JsonPrimitive(perfil)))
            }
        }, derecha = {
            CasillaSupervision(t("Control from boot"), servicio.logico("enabled"), disponible && (servicio.logico("available") || servicio.logico("enabled")), interruptor = true) {
                aplicacion.preguntarYEjecutar("fan.service", t("Control from boot"), parametros = mapOf(
                    "operation" to JsonPrimitive(if (it) "enable" else "disable")))
            }
            AccionSupervision(t("More")) { mas = true }
        })
        LineaDivisoria()
        Texto(textoVentilador(servicio, "summary", "summary_values"), 12, color = ColoresActuales.current.apagado)
        if (servicio.logico("out_of_date") || servicio.texto("state") == "override") {
            AccionSupervision(t("Update fan helper"), disponible) {
                aplicacion.preguntarYEjecutar("fan.service", t("Control from boot"), parametros = mapOf("operation" to JsonPrimitive("sync")))
            }
        }
        if (datos.texto("driver").isNotEmpty()) {
            FranjaSupervision(izquierda = {
                Texto(t(datos.texto("driver")), 12, color = ColoresActuales.current.naranja)
            }, derecha = {
                AccionSupervision(t("Prepare PWM driver"), aplicacion.puedeControlar && aplicacion.trabajo.terminado) {
                    herramientaVentilador(aplicacion, "prepare", "Prepare PWM driver")
                }
            })
        }
        if (datos.isEmpty()) Texto(t(if (primeraLectura) "Not connected" else "Waiting for data…"), 12)
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val altoInterior = (alto - 192.dp).coerceAtLeast(480.dp)
            if (maxWidth < 1000.dp) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    TablaVentiladores(canales, numero, 280.dp, ::elegir)
                    EditorVentilador(aplicacion, canal, datos, disponible, altoInterior) { entrada, sucio, nombre ->
                        borrador = entrada
                        cambiado = sucio
                        nombreBorrador = nombre
                    }
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    Box(Modifier.weight(0.62f)) { TablaVentiladores(canales, numero, altoInterior, ::elegir) }
                    Box(Modifier.weight(0.38f)) {
                        EditorVentilador(aplicacion, canal, datos, disponible, altoInterior) { entrada, sucio, nombre ->
                            borrador = entrada
                            cambiado = sucio
                        nombreBorrador = nombre
                        }
                    }
                }
            }
        }
        val cuentas = datos.objeto("counts")
        Texto(t("{count} channels", "count" to cuentas.entero("channels").toString()) + " · " +
            t("{count} turning", "count" to cuentas.entero("turning").toString()) + " · " +
            t("{count} controlled", "count" to cuentas.entero("controlled").toString()) + " · " + datos.texto("chip"),
            11, color = ColoresActuales.current.apagado)
    }
    if (pendiente != null) {
        Dialogo({ if (!aplicandoCambio) pendiente = null }) {
            TituloPanel(t("Unapplied changes"))
            Texto(t("The changes to this fan were not applied."), 12)
            if (borrador.texto("mode") == "fixed" && borrador.entero("percent") < datos.entero("low_duty", 30)) {
                Texto(t("A fan this slow can let the board overheat under load."), 12, color = ColoresActuales.current.naranja)
            }
            HerramientasSupervision {
                AccionSupervision(t("Apply"), disponible && !aplicandoCambio, primaria = true) {
                    trabajoAnterior = aplicacion.trabajo.id
                    aplicandoCambio = true
                    aplicacion.ejecutar("fans.apply", t("Apply"), mapOf("pwm" to JsonPrimitive(numero),
                        "entry" to borrador, "label" to JsonPrimitive(nombreBorrador)), confirmada = true)
                }
                AccionSupervision(t("Discard"), !aplicandoCambio) {
                    seleccionado = pendiente ?: numero
                    pendiente = null
                    cambiado = false
                }
                AccionSupervision(t("Cancel"), !aplicandoCambio) { pendiente = null }
            }
        }
    }
    if (mas) MenuVentiladores(aplicacion, datos, numero, borrador, perfil) { mas = false }
}

internal fun textoVentilador(datos: JsonObject, clave: String, argumentos: String): String {
    val valores = datos.objeto(argumentos).map { it.key to (it.value as? JsonPrimitive)?.content.orEmpty() }.toTypedArray()
    return t(datos.texto(clave), *valores)
}

internal fun herramientaVentilador(aplicacion: Aplicacion, operacion: String, titulo: String, parametros: Map<String, JsonElement> = emptyMap()) {
    aplicacion.preguntarYEjecutar("fans.tools", t(titulo), parametros = parametros + ("operation" to JsonPrimitive(operacion)), peligro = true)
}

@Composable
private fun TablaVentiladores(canales: List<JsonObject>, elegido: Int, alto: Dp, alElegir: (Int) -> Unit) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val ancho = maxWidth.coerceAtLeast(860.dp)
        Column(Modifier.horizontalScroll(rememberScrollState()).width(ancho)) {
            Row(Modifier.height(35.dp).background(paleta.panelAlterno), verticalAlignment = Alignment.CenterVertically) {
                Texto(t("Fan").uppercase(), 10, Modifier.weight(1f), peso = 800, color = paleta.apagado)
                for (titulo in listOf("BIOS", "Mode", "Follows", "°C", "PWM %", "RPM", "State")) {
                    Texto(t(titulo).uppercase(), 10, Modifier.width(if (titulo == "Follows") 135.dp else if (titulo in listOf("BIOS", "°C")) 50.dp else 80.dp), peso = 800, color = paleta.apagado)
                }
            }
            LazyColumn(Modifier.height(alto - 35.dp)) {
                items(canales, key = { it.entero("pwm") }) { canal ->
                    Row(Modifier.fillMaxWidth().height(30.dp)
                        .background(if (canal.entero("pwm") == elegido) paleta.elegido else paleta.panel)
                        .pulsable { alElegir(canal.entero("pwm")) }, verticalAlignment = Alignment.CenterVertically) {
                        Texto(canal.texto("label").ifEmpty { canal.texto("short_header") }, 12, Modifier.weight(1f).padding(start = 8.dp))
                        Texto(canal.texto("bios", "—"), 12, Modifier.width(50.dp))
                        Texto(t(canal.texto("mode_label")), 12, Modifier.width(80.dp))
                        Texto(textoVentilador(canal, "follows", "follows_values"), 12, Modifier.width(135.dp))
                        Texto(canal.texto("temperature", "—"), 12, Modifier.width(50.dp))
                        Column(Modifier.width(80.dp)) {
                            Texto(canal.texto("duty", "—") + " %", 12)
                            BarraUso(canal.numero("duty"), Modifier.width(65.dp), 2.dp)
                        }
                        Texto(canal.texto("rpm", "—"), 12, Modifier.width(80.dp))
                        Texto(t(canal.texto("state")), 12, Modifier.width(80.dp), color = paleta.color(canal.texto("tone").ifEmpty { "muted" }))
                    }
                    LineaDivisoria()
                }
            }
        }
    }
}
