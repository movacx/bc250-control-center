package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.CampoNumero
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Desplegable
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.Eleccion
import org.bc250.controlcenter.componentes.Interruptor
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.PaginaDesplazable
import org.bc250.controlcenter.componentes.TarjetaPagina
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoMono
import org.bc250.controlcenter.componentes.TituloPanel
import org.bc250.controlcenter.componentes.TresPuntos
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.abrirDireccion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

private val LadoQr = 224.dp
private const val HORA = 60
private const val DIA = 24 * HORA

/** Acceso remoto: la conexión, el código para emparejar y los dispositivos. */
@Composable
fun PaginaAccesoRemoto(aplicacion: Aplicacion) {
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("remote")
            aplicacion.pausar(4000)
        }
    }
    val datos = aplicacion.lectura("remote")
    val web = datos.objeto("web")
    PaginaDesplazable(PaddingValues(start = 16.dp, top = 8.dp, end = 18.dp, bottom = 20.dp)) {
        TarjetaPagina(Modifier.fillMaxWidth().padding(start = 2.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                TituloPanel(t("Remote access"))
                Texto(t("Control and monitor this board from a browser on your home network."), 12, color = ColoresActuales.current.apagado)
            }
            LineaDivisoria(Modifier.padding(vertical = 2.dp))
            BarraEstado(aplicacion, datos, web)
            PanelEmparejar(aplicacion, datos, web)
            PanelDispositivos(aplicacion, datos)
            PanelPermisos(aplicacion, datos)
            PanelSsh(aplicacion, datos.objeto("ssh"))
        }
    }
}

@Composable
private fun PanelRemoto(contenido: @Composable () -> Unit) {
    val paleta = ColoresActuales.current
    Column(
        modifier = Modifier.fillMaxWidth().marco(paleta.panel, paleta.bordeSuave, 6.dp).padding(horizontal = 17.dp, vertical = 15.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        contenido()
    }
}

private fun libre(aplicacion: Aplicacion): Boolean {
    return aplicacion.puedeControlar && aplicacion.trabajo.terminado
}

// -- estado -------------------------------------------------------------------------------------------

internal fun avisoDeEstado(web: JsonObject): String {
    val firewall = web.objeto("firewall").texto("state")
    return when {
        !web.logico("running") -> "Start web access to pair a phone."
        !web.logico("lan") -> "Turn on local network access below so phones can connect."
        firewall in listOf("blocked", "needs_check", "update_helper") ->
            "The firewall may be blocking other devices. Use Configure LAN firewall."
        firewall == "no_network" ->
            "No connected private network was detected. Connect this board to your Wi-Fi or cable."
        else -> ""
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BarraEstado(aplicacion: Aplicacion, datos: JsonObject, web: JsonObject) {
    PanelRemoto {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth >= 1300.dp) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp), Alignment.CenterVertically) {
                    SituacionAcceso(web)
                    ClaveAcceso(aplicacion, web)
                    Spacer(Modifier.weight(1f))
                    BotonesAcceso(aplicacion, datos, web)
                }
            } else {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    itemVerticalAlignment = Alignment.CenterVertically,
                ) {
                    SituacionAcceso(web)
                    ClaveAcceso(aplicacion, web)
                    BotonesAcceso(aplicacion, datos, web)
                }
            }
        }
    }
}

@Composable
private fun SituacionAcceso(web: JsonObject) {
    val paleta = ColoresActuales.current
    val activo = web.logico("running")
    val fondo = if (activo) paleta.color("green_soft") else paleta.color("neutral_soft")
    val color = if (activo) paleta.verde else paleta.apagado
    Box(Modifier.background(fondo, RoundedCornerShape(6.dp)).padding(horizontal = 18.dp, vertical = 5.dp)) {
        Texto(t(if (activo) "Web access is active" else "Web access is stopped"), 13, peso = 700, color = color)
    }
    val aviso = avisoDeEstado(web)
    if (aviso.isNotEmpty()) {
        Texto(t(aviso), tamano = 12, color = paleta.apagado)
    }
}

@Composable
private fun ClaveAcceso(aplicacion: Aplicacion, web: JsonObject) {
    val paleta = ColoresActuales.current
    val portapapeles = LocalClipboardManager.current
    val clave = web.texto("key")
    if (!web.logico("running") || clave.isEmpty()) {
        return
    }
    Texto(t("Remote access key"), tamano = 12, color = paleta.apagado)
    TextoMono(clave, tamano = 13, color = paleta.texto)
    BotonRemoto(t("Copy"), { portapapeles.setText(AnnotatedString(clave)) })
    BotonRemoto(t("New access key"), { renovarClave(aplicacion) }, activo = libre(aplicacion))
}

@Composable
private fun BotonesAcceso(aplicacion: Aplicacion, datos: JsonObject, web: JsonObject) {
    val activo = web.logico("running")
    val falta = datos.logico("prepare")
    if (falta) {
        BotonRemoto(t("Prepare the connection"), { prepararConexion(aplicacion, datos) },
            activo = libre(aplicacion), clase = ClaseBoton.PRINCIPAL)
    }
    BotonRemoto(t("Open in browser"), { abrirDireccion(web.texto("local_url")) }, activo = activo)
    BotonRemoto(t(if (activo) "Stop web access" else "Start web access"), { cambiarAcceso(aplicacion, activo) }, activo = libre(aplicacion))
}

@Composable
private fun BotonRemoto(
    texto: String,
    alPulsar: () -> Unit,
    activo: Boolean = true,
    clase: ClaseBoton = ClaseBoton.CONTORNO,
) {
    Boton(texto, alPulsar, clase = clase, activo = activo, alto = 33.dp, tamano = 12, peso = 650)
}

internal fun renovarClave(aplicacion: Aplicacion) {
    aplicacion.preguntarYEjecutar("remote.key", t("New access key"),
        t("A paired device keeps hardware control until you disconnect it or create a new access key."), peligro = true)
}

internal fun prepararConexion(aplicacion: Aplicacion, datos: JsonObject) {
    aplicacion.preguntarYEjecutar("remote.prepare", t("Prepare the connection"), datos.texto("prepare_message"))
}

internal fun cambiarAcceso(aplicacion: Aplicacion, activo: Boolean) {
    if (activo) {
        val aviso = t("This page stops working until web access is started again on the board.")
        aplicacion.preguntarYEjecutar("remote.stop", t("Stop web access"), aviso, peligro = true)
    } else {
        aplicacion.preguntarYEjecutar("remote.start", t("Start web access"))
    }
}

// -- emparejar ----------------------------------------------------------------------------------------------

@Composable
private fun PanelEmparejar(aplicacion: Aplicacion, datos: JsonObject, web: JsonObject) {
    val direcciones = web.textos("urls").ifEmpty { listOf(web.texto("local_url")).filter { it.isNotEmpty() } }
    var elegida by remember { mutableStateOf("") }
    val direccion = if (elegida in direcciones) elegida else direcciones.firstOrNull() ?: ""
    var matriz by remember { mutableStateOf<List<List<Boolean>>>(emptyList()) }
    LaunchedEffect(direccion, web.logico("running"), web.logico("lan")) {
        while (true) {
            matriz = leerMatriz(aplicacion.consultar("remote.qr", mapOf("address" to direccion)))
            delay(30000)
        }
    }
    PanelRemoto {
        Texto(t("Pair a device"), tamano = 12, peso = 500, color = ColoresActuales.current.apagado)
        BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 2.dp)) {
            if (maxWidth >= 740.dp) {
                Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(24.dp)) {
                    ColumnaConexion(aplicacion, datos, web, direcciones, direccion, Modifier.weight(1f)) { valor -> elegida = valor }
                    ColumnaQr(matriz)
                }
            } else {
                Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(16.dp), Alignment.CenterHorizontally) {
                    ColumnaQr(matriz)
                    ColumnaConexion(aplicacion, datos, web, direcciones, direccion, Modifier.fillMaxWidth()) { valor -> elegida = valor }
                }
            }
        }
    }
}

internal fun leerMatriz(datos: JsonObject): List<List<Boolean>> {
    val filas = datos["matrix"] as? JsonArray ?: return emptyList()
    return filas.filterIsInstance<JsonArray>().map { fila -> fila.map(::esOscuro) }
}

private fun esOscuro(punto: JsonElement): Boolean {
    return punto is JsonPrimitive && punto.content == "true"
}

@Composable
private fun ColumnaQr(matriz: List<List<Boolean>>) {
    val paleta = ColoresActuales.current
    Column(Modifier.width(LadoQr), Arrangement.spacedBy(6.dp)) {
        if (matriz.isEmpty()) {
            Box(Modifier.size(LadoQr), Alignment.Center) {
                Texto(t("Start web access and enable the local network to display your QR here."), 13, alineado = TextAlign.Center)
            }
        } else {
            CodigoQr(matriz)
        }
        val nota = t("Scan to pair. The code works once and renews by itself.")
        Texto(nota, 12, Modifier.fillMaxWidth(), color = paleta.apagado, alineado = TextAlign.Center)
    }
}

/** El código, con su margen blanco, en puntos enteros para que se lea bien. */
@Composable
private fun CodigoQr(matriz: List<List<Boolean>>) {
    Canvas(Modifier.size(LadoQr).background(Color.White, RoundedCornerShape(4.dp))) {
        val puntos = matriz.size + 8
        val lado = kotlin.math.floor(size.width / puntos)
        val margen = (size.width - lado * puntos) / 2 + lado * 4
        for ((fila, celdas) in matriz.withIndex()) {
            for ((columna, oscura) in celdas.withIndex()) {
                if (oscura) {
                    drawRect(Color.Black, Offset(margen + columna * lado, margen + fila * lado), Size(lado, lado))
                }
            }
        }
    }
}

@Composable
private fun ColumnaConexion(
    aplicacion: Aplicacion,
    datos: JsonObject,
    web: JsonObject,
    direcciones: List<String>,
    direccion: String,
    modifier: Modifier,
    alElegir: (String) -> Unit,
) {
    val portapapeles = LocalClipboardManager.current
    Column(modifier, Arrangement.spacedBy(6.dp)) {
        val explicacion = "Connect your phone to the same Wi-Fi and scan the code. " +
            "It pairs right away with full hardware control, with no key to type."
        Texto(t(explicacion), tamano = 12, color = ColoresActuales.current.apagado)
        Desplegable(direcciones.map { valor -> Eleccion(valor, valor) }, direccion, alElegir, Modifier.fillMaxWidth())
        Boton(t("Copy address"), { portapapeles.setText(AnnotatedString(direccion)) }, Modifier.fillMaxWidth(),
            activo = direccion.isNotEmpty(), clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
        ReparacionNombre(aplicacion, datos, web)
        ReparacionFirewall(aplicacion, datos, web)
        LineaDivisoria(Modifier.padding(vertical = 8.dp))
        OpcionesConexion(aplicacion, web)
        Boton(t("Download certificate"), { abrirDireccion(aplicacion.conexion.direccion + "/api/query?name=remote.certificate") },
            Modifier.fillMaxWidth(), activo = web.texto("trust_fingerprint").isNotEmpty(),
            clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
        PuertoConexion(aplicacion, web)
    }
}

@Composable
private fun ReparacionNombre(aplicacion: Aplicacion, datos: JsonObject, web: JsonObject) {
    val estado = web.objeto("name_health")
    val conProblema = estado.texto("status") in listOf("resolver_failed", "publication_failed", "conflict", "unavailable")
    if (!web.logico("lan")) {
        return
    }
    if (conProblema) {
        Texto(datos.texto("name_message"), tamano = 12, color = ColoresActuales.current.naranja)
    }
    if (estado.logico("repairable") || (web.logico("running") && estado.texto("status") == "ready")) {
        Boton(t("Repair local address"), {
            repararNombreRemoto(aplicacion, datos)
        }, Modifier.fillMaxWidth(), activo = libre(aplicacion), clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
    }
}

@Composable
private fun ReparacionFirewall(aplicacion: Aplicacion, datos: JsonObject, web: JsonObject) {
    val firewall = web.objeto("firewall")
    val conProblema = firewall.texto("state") in listOf("blocked", "needs_check", "inactive", "unknown", "unsupported", "update_helper")
    if (!web.logico("lan") || !conProblema) {
        return
    }
    Texto(datos.texto("firewall_message"), tamano = 12, color = ColoresActuales.current.naranja)
    if (firewall.logico("repairable")) {
        Boton(t("Configure LAN firewall"), {
            repararFirewallRemoto(aplicacion, datos)
        }, Modifier.fillMaxWidth(), activo = libre(aplicacion), clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
    }
}

@Composable
private fun OpcionesConexion(aplicacion: Aplicacion, web: JsonObject) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= 560.dp) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(28.dp)) {
                OpcionRedLocal(aplicacion, web, Modifier.weight(1f))
                OpcionArranque(aplicacion, web, Modifier.weight(1f))
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OpcionRedLocal(aplicacion, web, Modifier.fillMaxWidth())
                OpcionArranque(aplicacion, web, Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun OpcionRedLocal(aplicacion: Aplicacion, web: JsonObject, modifier: Modifier) {
    val texto = t("Reachable from the local network")
    OpcionConexion(texto, web.logico("lan"), libre(aplicacion), modifier) { nuevo ->
        cambiarOpcion(aplicacion, "lan", JsonPrimitive(nuevo), texto)
    }
}

@Composable
private fun OpcionArranque(aplicacion: Aplicacion, web: JsonObject, modifier: Modifier) {
    val texto = t("Start with the session")
    val arranque = web.objeto("autostart")
    val puede = libre(aplicacion) && arranque.logico("supported") && !arranque.logico("foreign")
    OpcionConexion(texto, arranque.logico("enabled"), puede, modifier) { nuevo ->
        cambiarOpcion(aplicacion, "autostart", JsonPrimitive(nuevo), texto)
    }
}

internal fun cambiarOpcion(aplicacion: Aplicacion, campo: String, valor: JsonElement, aviso: String) {
    val parametros = mapOf("field" to JsonPrimitive(campo), "value" to valor)
    aplicacion.preguntarYEjecutar("remote.configure", t("Remote access"), aviso, parametros)
}

@Composable
private fun OpcionConexion(
    texto: String,
    activa: Boolean,
    libre: Boolean,
    modifier: Modifier = Modifier,
    alCambiar: (Boolean) -> Unit,
) {
    Row(modifier.heightIn(min = 26.dp), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
        Interruptor(activa, alCambiar, activo = libre)
        Texto(texto, tamano = 12, color = ColoresActuales.current.apagado)
    }
}

@Composable
private fun PuertoConexion(aplicacion: Aplicacion, web: JsonObject) {
    val actual = web.entero("port", 8250)
    var puerto by remember(actual) { mutableIntStateOf(actual) }
    fun aplicar() {
        cambiarPuertoRemoto(aplicacion, puerto)
    }
    Row(Modifier.padding(top = 6.dp), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
        Texto("TCP", tamano = 12, color = ColoresActuales.current.apagado)
        CampoNumero(puerto, { valor -> puerto = valor }, 1024, 65535, Modifier.width(120.dp))
        Boton(t("Apply"), ::aplicar, activo = libre(aplicacion) && puerto != actual,
            clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
    }
}

// -- dispositivos ---------------------------------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PanelDispositivos(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val dispositivos = datos.objetos("devices")
    var elegido by remember { mutableStateOf("") }
    var editando by remember { mutableStateOf(false) }
    val dispositivo = dispositivos.firstOrNull { item -> item.texto("id") == elegido }
    PanelRemoto {
        Texto(t("Paired devices"), tamano = 12, peso = 500, color = paleta.apagado)
        Texto(t("A paired device keeps hardware control until you disconnect it or create a new access key."), 12, color = paleta.apagado)
        TablaDispositivos(dispositivos, elegido) { id -> elegido = id }
        Box(Modifier.fillMaxWidth(), Alignment.Center) {
            TresPuntos()
        }
        if (dispositivos.isEmpty()) {
            Texto(t("No connected browsers."), tamano = 12, color = paleta.apagado)
        }
        FlowRow(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Arrangement.spacedBy(8.dp)) {
            val puede = libre(aplicacion) && dispositivo != null
            val aprobado = dispositivo?.logico("approved") == true
            BotonDispositivo(t(if (aprobado) "Approved" else "Approve device"), puede && !aprobado) {
                aprobarDispositivoRemoto(aplicacion, elegido)
            }
            BotonDispositivo(t("Session"), puede) { editando = true }
            BotonDispositivo(t("Disconnect"), puede) { desconectarDispositivoRemoto(aplicacion, elegido) }
            Spacer(Modifier.weight(1f))
            BotonDispositivo(t("Disconnect all devices"), libre(aplicacion) && dispositivos.isNotEmpty()) {
                desconectarTodosRemoto(aplicacion)
            }
        }
    }
    if (editando && dispositivo != null) {
        DialogoDispositivo(aplicacion, dispositivo) { editando = false }
    }
}

@Composable
private fun BotonDispositivo(texto: String, activo: Boolean, alPulsar: () -> Unit) {
    Boton(texto, alPulsar, activo = activo, clase = ClaseBoton.CONTORNO, alto = 33.dp, tamano = 12, peso = 650)
}

private fun operar(
    aplicacion: Aplicacion,
    identificador: String,
    operacion: String,
    titulo: String,
    extra: Map<String, JsonElement> = emptyMap(),
    peligro: Boolean = false,
) {
    val parametros = mapOf("operation" to JsonPrimitive(operacion), "id" to JsonPrimitive(identificador)) + extra
    aplicacion.preguntarYEjecutar("remote.device", titulo, titulo, parametros, peligro)
}

@Composable
private fun TablaDispositivos(dispositivos: List<JsonObject>, elegido: String, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val ancho = maxWidth.coerceAtLeast(900.dp)
        Column(Modifier.horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(ancho).heightIn(min = 90.dp).marco(paleta.panel, paleta.borde, 4.dp).padding(1.dp)) {
                val nombres = listOf("Device", "IP address", "Device code", "Permissions", "Status", "Last activity", "Session")
                FilaDispositivo(nombres.map { nombre -> t(nombre) }, paleta.panelAlterno, peso = 700) {}
                for (dispositivo in dispositivos) {
                    val id = dispositivo.texto("id")
                    val fondo = if (id == elegido) paleta.acentoSuave else paleta.panel
                    LineaDivisoria(color = paleta.borde)
                    FilaDispositivo(celdasDe(dispositivo), fondo, peso = 400) { alElegir(id) }
                }
            }
        }
    }
}

internal fun celdasDe(dispositivo: JsonObject): List<String> {
    val permiso = if (dispositivo.logico("control")) "Hardware control" else "Monitoring only"
    return listOf(
        dispositivo.texto("name"), dispositivo.texto("address"), dispositivo.texto("id").take(8), t(permiso),
        t(dispositivo.texto("label")), dispositivo.texto("seen_text"), dispositivo.texto("expiry_text"),
    )
}

private val AnchosDispositivo = listOf(0, 110, 150, 130, 80, 140, 100)

@Composable
private fun FilaDispositivo(celdas: List<String>, fondo: Color, peso: Int, alPulsar: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().height(40.dp).background(fondo).pulsable(alPulsar = alPulsar),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        for ((indice, celda) in celdas.withIndex()) {
            val ancho = AnchosDispositivo[indice]
            val modificador = if (ancho == 0) Modifier.weight(1f) else Modifier.width(ancho.dp)
            Texto(celda, 12, modificador.padding(horizontal = 8.dp), peso = peso, lineas = 1)
        }
    }
}

/** Los permisos y la duración de la sesión de un dispositivo. */
@Composable
private fun DialogoDispositivo(aplicacion: Aplicacion, dispositivo: JsonObject, alCerrar: () -> Unit) {
    val id = dispositivo.texto("id")
    val control = dispositivo.logico("control")
    fun cambiarPermiso() {
        alCerrar()
        cambiarPermisoRemoto(aplicacion, id, control)
    }
    fun cambiarDuracion(minutos: Int, titulo: String) {
        alCerrar()
        cambiarDuracionRemoto(aplicacion, id, minutos, titulo)
    }
    val duraciones = DuracionesRemotas.map { (minutos, clave) -> minutos to t(clave) }
    Dialogo(alCerrar) {
        Texto(dispositivo.texto("name"), tamano = 17, peso = 800)
        Texto(dispositivo.texto("address") + " · " + dispositivo.texto("expiry_text"), 13, color = ColoresActuales.current.apagado)
        Boton(t(if (control) "Monitoring only" else "Hardware control"), ::cambiarPermiso, Modifier.fillMaxWidth())
        for ((minutos, nombre) in duraciones) {
            Boton(nombre, { cambiarDuracion(minutos, nombre) }, Modifier.fillMaxWidth())
        }
        Boton(t("Close"), alCerrar, Modifier.fillMaxWidth())
    }
}

// -- permisos -----------------------------------------------------------------------------------------------------

@Composable
private fun PanelPermisos(aplicacion: Aplicacion, datos: JsonObject) {
    val permiso = datos.objeto("quick_auth")
    if (permiso.isEmpty()) {
        return
    }
    val paleta = ColoresActuales.current
    PanelRemoto {
        Texto(t("Permissions"), tamano = 12, peso = 500, color = paleta.apagado)
        OpcionConexion(t("Actions without password"), permiso.logico("enabled"), libre(aplicacion)) { nuevo ->
            cambiarAccionesSinClave(aplicacion, permiso, nuevo)
        }
        Texto(t("CPU, compute units, GPU and fans stop asking for the Linux password. Everything else keeps asking."), 12, color = paleta.apagado)
    }
}

internal fun cambiarAccionesSinClave(aplicacion: Aplicacion, permiso: JsonObject, activar: Boolean) {
    val titulo = t("Actions without password")
    val mensaje = if (activar) permiso.texto("warning") else titulo
    aplicacion.preguntarYEjecutar("settings.quick_auth", titulo, mensaje, mapOf("enable" to JsonPrimitive(activar)), peligro = activar)
}

// -- SSH ----------------------------------------------------------------------------------------------------------

@Composable
private fun PanelSsh(aplicacion: Aplicacion, ssh: JsonObject) {
    if (ssh.isEmpty()) {
        return
    }
    val paleta = ColoresActuales.current
    PanelRemoto {
        Texto("SSH", tamano = 12, peso = 500, color = paleta.apagado)
        val equipo = ssh.textos("addresses").firstOrNull() ?: ""
        val direccion = if (equipo.isEmpty()) "" else "ssh -p ${ssh.entero("port", 22)} ${ssh.texto("user")}@$equipo"
        if (direccion.isNotEmpty()) {
            TextoMono(direccion, tamano = 12, color = paleta.texto)
        }
        val puede = libre(aplicacion) && ssh.logico("supported")
        Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
            OpcionConexion(t("Active"), ssh.logico("active"), puede) { nuevo -> cambiarSsh(aplicacion, "active", nuevo) }
            OpcionConexion(t("Start with the session"), ssh.logico("enabled"), puede) { nuevo -> cambiarSsh(aplicacion, "boot", nuevo) }
        }
    }
}

internal fun cambiarSsh(aplicacion: Aplicacion, campo: String, valor: Boolean) {
    val parametros = mapOf("field" to JsonPrimitive(campo), "value" to JsonPrimitive(valor))
    aplicacion.preguntarYEjecutar("remote.ssh", "SSH", "SSH", parametros)
}

internal fun repararNombreRemoto(aplicacion: Aplicacion, datos: JsonObject) {
    aplicacion.preguntarYEjecutar("remote.name", t("Repair local address"), datos.texto("name_warning"))
}

internal fun repararFirewallRemoto(aplicacion: Aplicacion, datos: JsonObject) {
    aplicacion.preguntarYEjecutar("remote.firewall", t("Configure LAN firewall"), datos.texto("firewall_warning"))
}

internal fun desconectarTodosRemoto(aplicacion: Aplicacion) {
    aplicacion.preguntarYEjecutar("remote.revoke_all", t("Disconnect all devices"), peligro = true)
}

internal val DuracionesRemotas = listOf(
    0 to "Permanent", HORA to "1 hour", 8 * HORA to "8 hours", 7 * DIA to "7 days", 30 * DIA to "30 days",
)

internal fun aprobarDispositivoRemoto(aplicacion: Aplicacion, id: String) {
    operar(aplicacion, id, "approve", t("Approve device"))
}

internal fun desconectarDispositivoRemoto(aplicacion: Aplicacion, id: String) {
    operar(aplicacion, id, "revoke", t("Disconnect"), peligro = true)
}

internal fun cambiarPermisoRemoto(aplicacion: Aplicacion, id: String, control: Boolean) {
    val titulo = t(if (control) "Monitoring only" else "Hardware control")
    operar(aplicacion, id, "control", titulo, mapOf("value" to JsonPrimitive(!control)), peligro = !control)
}

internal fun cambiarDuracionRemoto(aplicacion: Aplicacion, id: String, minutos: Int, titulo: String) {
    operar(aplicacion, id, "lifetime", titulo, mapOf("minutes" to JsonPrimitive(minutos)))
}

internal fun cambiarPuertoRemoto(aplicacion: Aplicacion, puerto: Int) {
    val aviso = t("This page stops working until web access is started again on the board.")
    cambiarOpcion(aplicacion, "port", JsonPrimitive(puerto), aviso)
}
