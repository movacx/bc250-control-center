package org.bc250.controlcenter.movil

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.*
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.floor

@Composable
fun PaginaAccesoRemotoMovil(aplicacion: Aplicacion) {
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("remote")
            aplicacion.pausar(4000)
        }
    }
    val datos = aplicacion.lectura("remote")
    val web = datos.objeto("web")
    val estado = movil()
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val portapapeles = LocalClipboardManager.current
    val activo = web.logico("running")
    PaginaMovil("remote") {
        EstadoLecturaMovil(datos)
        GrupoMovil {
            FilaLibre {
                TextosFila(t("Web access"))
                Pildora(t(if (activo) "Active" else "Stopped"), activo)
            }
            if (activo && web.texto("key").isNotEmpty()) {
                FilaLibre {
                    TextosFila(t("Remote access key"))
                    ValorConUnidad(web.texto("key"))
                    EnlaceMovil(t("Copy")) { portapapeles.setText(AnnotatedString(web.texto("key"))) }
                }
            }
            Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                ParejaBotones {
                    BotonMovil(t("New access key"), Modifier.weight(1f), activo = libre && activo) {
                        renovarClave(aplicacion)
                    }
                    BotonMovil(t(if (activo) "Stop web access" else "Start web access"), Modifier.weight(1f),
                        if (activo) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL, libre) { cambiarAcceso(aplicacion, activo) }
                }
                if (datos.logico("prepare")) {
                    BotonMovil(t("Prepare the connection"), Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL, libre) {
                        prepararConexion(aplicacion, datos)
                    }
                }
            }
        }
        val aviso = avisoDeEstado(web)
        if (aviso.isNotEmpty()) NotaMovil(t(aviso))
        EmparejarMovil(aplicacion)
        SeccionMovil(t("Paired devices")) {
            val dispositivos = datos.objetos("devices")
            GrupoMovil {
                for (dispositivo in dispositivos) {
                    val permiso = t(if (dispositivo.logico("control")) "Hardware control" else "Monitoring only")
                    FilaAbrir(dispositivo.texto("name"), dispositivo.texto("address") + " · " + permiso) {
                        estado.abrirHoja { DispositivoMovil(aplicacion, dispositivo.texto("id")) }
                    }
                }
                if (dispositivos.isEmpty()) FilaLibre { TextosFila(t("No connected browsers.")) }
                if (dispositivos.isNotEmpty()) {
                    Column(Modifier.padding(14.dp)) {
                        BotonMovil(t("Disconnect all devices"), Modifier.fillMaxWidth(), ClaseBoton.PELIGRO, libre) {
                            desconectarTodosRemoto(aplicacion)
                        }
                    }
                }
            }
        }
        SshMovil(aplicacion)
    }
}

@Composable
private fun EmparejarMovil(aplicacion: Aplicacion) {
    val datos = aplicacion.lectura("remote")
    val web = datos.objeto("web")
    val direcciones = web.textos("urls").ifEmpty { listOf(web.texto("local_url")).filter { it.isNotEmpty() } }
    var elegida by remember { mutableStateOf("") }
    val direccion = if (elegida in direcciones) elegida else direcciones.firstOrNull().orEmpty()
    var matriz by remember { mutableStateOf<List<List<Boolean>>>(emptyList()) }
    LaunchedEffect(direccion, web.logico("running"), web.logico("lan")) {
        while (true) {
            matriz = leerMatriz(aplicacion.consultar("remote.qr", mapOf("address" to direccion)))
            delay(30000)
        }
    }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val portapapeles = LocalClipboardManager.current
    val estado = movil()
    SeccionMovil(t("Pair a device")) {
        GrupoMovil {
            Column(Modifier.fillMaxWidth().padding(14.dp), Arrangement.spacedBy(10.dp), Alignment.CenterHorizontally) {
                if (matriz.isEmpty()) {
                    TextoHoja(t("Start web access and enable the local network to display your QR here."))
                } else {
                    QrMovil(matriz)
                }
            }
            FilaInterruptor(t("Reachable from the local network"), web.logico("lan"), activa = libre) {
                cambiarOpcion(aplicacion, "lan", JsonPrimitive(it), t("Reachable from the local network"))
            }
            val inicio = web.objeto("autostart")
            FilaInterruptor(t("Start with the session"), inicio.logico("enabled"),
                activa = libre && inicio.logico("supported") && !inicio.logico("foreign")) {
                cambiarOpcion(aplicacion, "autostart", JsonPrimitive(it), t("Start with the session"))
            }
            Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                ParejaBotones {
                    BotonMovil(t("Copy address"), Modifier.weight(1f), activo = direccion.isNotEmpty()) {
                        portapapeles.setText(AnnotatedString(direccion))
                    }
                    BotonMovil(t("Download certificate"), Modifier.weight(1f),
                        activo = web.texto("trust_fingerprint").isNotEmpty()) {
                        abrirDireccion(aplicacion.conexion.direccion + "/api/query?name=remote.certificate")
                    }
                }
            }
            FilaAbrir(t("Connection"), direccion) {
                estado.abrirHoja {
                    ConexionMovil(aplicacion, direccion, direcciones) { elegida = it }
                }
            }
        }
    }
}

@Composable
private fun QrMovil(matriz: List<List<Boolean>>) {
    val paleta = ColoresActuales.current
    val claro = if (paleta.esClaro) paleta.panel else paleta.texto
    val oscuro = if (paleta.esClaro) paleta.texto else paleta.ventana
    Canvas(Modifier.size(200.dp).background(claro)) {
        val lado = floor(size.width / (matriz.size + 8))
        val margen = (size.width - lado * matriz.size) / 2
        for ((y, fila) in matriz.withIndex()) {
            for ((x, lleno) in fila.withIndex()) {
                if (lleno) drawRect(oscuro, Offset(margen + x * lado, margen + y * lado), Size(lado, lado))
            }
        }
    }
}

@Composable
private fun ConexionMovil(aplicacion: Aplicacion, direccion: String, direcciones: List<String>, alElegir: (String) -> Unit) {
    val datos = aplicacion.lectura("remote")
    val web = datos.objeto("web")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val actual = web.entero("port", 8250)
    var puerto by remember(actual) { mutableStateOf(actual.toString()) }
    var seleccion by remember { mutableStateOf(direccion) }
    TituloHoja(t("Connection"))
    TextoHoja(t("Connect your phone to the same Wi-Fi and scan the code. " +
        "It pairs right away with full hardware control, with no key to type."))
    GrupoMovil {
        for (opcion in direcciones) {
            FilaRadio(opcion, seleccion == opcion) {
                seleccion = opcion
                alElegir(opcion)
            }
        }
    }
    BotonMovil(t("Open in browser"), Modifier.fillMaxWidth(), activo = web.logico("running")) {
        abrirDireccion(web.texto("local_url"))
    }
    if (web.logico("lan")) {
        val nombre = web.objeto("name_health")
        if (nombre.texto("status") in listOf("resolver_failed", "publication_failed", "conflict", "unavailable")) {
            NotaMovil(datos.texto("name_message"), ColoresActuales.current.naranja)
        }
        if (nombre.logico("repairable") || (web.logico("running") && nombre.texto("status") == "ready")) {
            BotonMovil(t("Repair local address"), Modifier.fillMaxWidth(), activo = libre) {
                repararNombreRemoto(aplicacion, datos)
            }
        }
        val firewall = web.objeto("firewall")
        if (firewall.texto("state") in listOf("blocked", "needs_check", "inactive", "unknown", "unsupported", "update_helper")) {
            NotaMovil(datos.texto("firewall_message"), ColoresActuales.current.naranja)
            if (firewall.logico("repairable")) {
                BotonMovil(t("Configure LAN firewall"), Modifier.fillMaxWidth(), activo = libre) {
                    repararFirewallRemoto(aplicacion, datos)
                }
            }
        }
    }
    CampoConNombreMovil("TCP", puerto, numerico = true) { puerto = it }
    val numero = puerto.toIntOrNull()
    BotonMovil(t("Apply"), Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL,
        libre && numero != null && numero in 1024..65535 && numero != actual) {
        if (numero != null) cambiarPuertoRemoto(aplicacion, numero)
    }
    CerrarHoja()
}

@Composable
private fun DispositivoMovil(aplicacion: Aplicacion, id: String) {
    val dispositivo = aplicacion.lectura("remote").objetos("devices").firstOrNull { it.texto("id") == id }
    if (dispositivo == null) {
        TextoHoja(t("No connected browsers."))
        CerrarHoja()
        return
    }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val estado = movil()
    val control = dispositivo.logico("control")
    val tituloPermiso = t(if (control) "Monitoring only" else "Hardware control")
    TituloHoja(dispositivo.texto("name"))
    val nombres = listOf("Device", "IP address", "Device code", "Permissions", "Status", "Last activity", "Session")
    GrupoMovil {
        for ((indice, valor) in celdasDe(dispositivo).withIndex()) FilaDato(t(nombres[indice]), valor)
    }
    TextoHoja(t("A paired device keeps hardware control until you disconnect it or create a new access key."))
    BotonMovil(t(if (dispositivo.logico("approved")) "Approved" else "Approve device"), Modifier.fillMaxWidth(),
        activo = libre && !dispositivo.logico("approved")) { aprobarDispositivoRemoto(aplicacion, id) }
    BotonMovil(tituloPermiso, Modifier.fillMaxWidth(), activo = libre) {
        estado.cerrarHoja()
        cambiarPermisoRemoto(aplicacion, id, control)
    }
    SeccionMovil(t("Session")) {
        GrupoMovil {
            for ((minutos, clave) in DuracionesRemotas) {
                FilaAbrir(t(clave), activa = libre) {
                    estado.cerrarHoja()
                    cambiarDuracionRemoto(aplicacion, id, minutos, t(clave))
                }
            }
        }
    }
    BotonMovil(t("Disconnect"), Modifier.fillMaxWidth(), ClaseBoton.PELIGRO, libre) {
        estado.cerrarHoja()
        desconectarDispositivoRemoto(aplicacion, id)
    }
    CerrarHoja()
}

@Composable
private fun SshMovil(aplicacion: Aplicacion) {
    val ssh = aplicacion.lectura("remote").objeto("ssh")
    if (ssh.isEmpty()) return
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && ssh.logico("supported")
    SeccionMovil("SSH") {
        GrupoMovil {
            FilaInterruptor(t("Active"), ssh.logico("active"), activa = libre) { cambiarSsh(aplicacion, "active", it) }
            FilaInterruptor(t("Start with the session"), ssh.logico("enabled"), activa = libre) {
                cambiarSsh(aplicacion, "boot", it)
            }
            val equipo = ssh.textos("addresses").firstOrNull().orEmpty()
            if (equipo.isNotEmpty()) FilaDato("SSH", "ssh -p ${ssh.entero("port", 22)} ${ssh.texto("user")}@$equipo")
        }
    }
}
