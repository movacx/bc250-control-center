package org.bc250.controlcenter.movil

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.BarraUso
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.*
import org.bc250.controlcenter.recursos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.jetbrains.compose.resources.painterResource

@Composable
fun PaginaPanelMovil(aplicacion: Aplicacion) {
    var dialogo by remember { mutableStateOf("") }
    var novedades by remember { mutableStateOf(ObjetoVacio) }
    LaunchedEffect(Unit) {
        while (true) {
            novedades = aplicacion.consultar("panel.update")
            if (novedades.logico("available")) dialogo = "update"
            delay(900000)
        }
    }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("dashboard")
            aplicacion.pausar(3000)
        }
    }
    val datos = JsonObject(aplicacion.lectura("dashboard") + ("update" to novedades))
    val movil = movil()
    Box(Modifier.fillMaxSize()) {
        PaginaMovil("dashboard") {
            CabeceraPanelMovil(datos)
            EstadoLecturaMovil(datos)
            if (datos.objetos("cards").isEmpty() || datos.logico("waiting")) NotaMovil(t("Checking…"))
            for (tarjeta in datos.objetos("cards")) {
                InstrumentoMovil(aplicacion, datos, tarjeta) { dialogo = it }
            }
            GrupoMovil {
                MemoriaMovil(aplicacion, datos.objeto("gddr6"))
                FilaAbrir(t("Power delivery"), valor = datos.objetos("rails").size.toString()) {
                    movil.abrirHoja {
                        TituloHoja(t("Power delivery"))
                        AlimentacionMovil(aplicacion, aplicacion.lectura("dashboard")) {
                            movil.cerrarHoja()
                            dialogo = "vrm"
                        }
                        CerrarHoja()
                    }
                }
            }
            PreparacionMovil(aplicacion, datos) { dialogo = it }
        }
        DialogosPanel(aplicacion, datos, dialogo) { dialogo = "" }
    }
}

@Composable
private fun CabeceraPanelMovil(datos: JsonObject) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), Arrangement.spacedBy(16.dp), Alignment.CenterVertically) {
        val dibujo = if (paleta.esClaro) Res.drawable.bc250_board_light else Res.drawable.bc250_board_dark
        Image(painterResource(dibujo), "AMD BC-250", Modifier.size(108.dp, 74.dp))
        Column(Modifier.weight(1f)) {
            TextoTitulo(datos.texto("title", "AMD BC-250"), 22)
            Texto(datos.texto("specification"), tamano = 13, color = paleta.apagado)
        }
    }
}

@Composable
private fun InstrumentoMovil(aplicacion: Aplicacion, datos: JsonObject, tarjeta: JsonObject, alDialogo: (String) -> Unit) {
    val paleta = ColoresActuales.current
    val clave = tarjeta.texto("key")
    val movil = movil()
    val grupos = tarjeta.objetos("groups")
    GrupoMovil {
        TituloLectura(tarjeta.texto("title"), tarjeta.texto("value", "--"), tarjeta.texto("unit"))
        LecturasInstrumento(clave, grupos)
        if (clave == "cpu") {
            SubtituloMovil(t("Live core monitor"))
            for (nucleo in datos.objetos("cores")) {
                FilaNucleoPanel(nucleo)
            }
        }
        val telemetria = datos.objeto("telemetry")
        if (clave == "gpu" && telemetria.logico("visible")) {
            FilaAbrir(telemetria.texto("label"),
                activa = !telemetria.logico("pending") && aplicacion.puedeControlar && aplicacion.trabajo.terminado) {
                repararTelemetriaPanel(aplicacion, telemetria) { alDialogo("telemetry") }
            }
        }
        if (clave != "cpu") {
            FilaAbrir(t("All readings")) {
                movil.abrirHoja { TodasLasLecturas(aplicacion, clave) }
            }
        }
        val paginas = when (clave) {
            "cpu" -> listOf("Configure CPU" to "cpu")
            "gpu" -> listOf("Configure Governor" to "gpu", "Configure CUs" to "cu")
            else -> listOf("Fan Control" to "fans")
        }
        for ((nombre, destino) in paginas) {
            FilaAbrir(t(nombre), colorTitulo = paleta.acento) { aplicacion.irA(destino) }
        }
    }
}

@Composable
private fun FilaNucleoPanel(nucleo: JsonObject) {
    val paleta = ColoresActuales.current
    val oculto = nucleo.texto("detail").isEmpty()
    FilaLibre(altoMinimo = 40.dp) {
        Texto(nucleo.texto("label"), tamano = 13, peso = 700, color = paleta.apagado, modifier = Modifier.width(30.dp))
        Texto(
            texto = nucleo.texto("value"),
            tamano = if (oculto) 12 else 14,
            peso = if (oculto) 400 else 700,
            color = if (oculto) paleta.apagado else paleta.texto,
            alineado = TextAlign.End,
            lineas = 1,
            modifier = Modifier.width(84.dp),
        )
        BarraUso(nucleo.numero("usage"), Modifier.weight(1f), alto = 5.dp)
        Texto(nucleo.texto("detail"), tamano = 13, color = paleta.apagado, alineado = TextAlign.End, modifier = Modifier.width(44.dp))
    }
}

@Composable
private fun TodasLasLecturas(aplicacion: Aplicacion, clave: String) {
    val tarjeta = aplicacion.lectura("dashboard").objetos("cards").firstOrNull { it.texto("key") == clave } ?: ObjetoVacio
    TituloHoja(tarjeta.texto("title"))
    for (grupo in tarjeta.objetos("groups")) {
        SeccionMovil(t(grupo.texto("title"))) {
            GrupoMovil { for (fila in grupo.objetos("rows")) LecturaPanelMovil(fila) }
        }
    }
    CerrarHoja()
}

@Composable
private fun GrupoInstrumento(grupo: JsonObject) {
    val movil = movil()
    if (grupo.logico("collapsed")) {
        FilaAbrir(t(grupo.texto("title"))) {
            movil.abrirHoja {
                TituloHoja(t(grupo.texto("title")))
                GrupoMovil { for (fila in grupo.objetos("rows")) LecturaPanelMovil(fila) }
                CerrarHoja()
            }
        }
    } else {
        SubtituloMovil(t(grupo.texto("title")))
        for (fila in grupo.objetos("rows")) LecturaPanelMovil(fila)
    }
}

@Composable
private fun LecturaPanelMovil(fila: JsonObject) {
    val paleta = ColoresActuales.current
    val color = when (fila.texto("tone")) {
        "danger" -> paleta.rojo
        "warning" -> paleta.naranja
        else -> paleta.texto
    }
    val detalle = t(fila.texto("detail"))
    val enLinea = detalle.startsWith("/")
    val unidad = if (enLinea) fila.texto("unit") + " " + detalle else fila.texto("unit")
    FilaDato(t(fila.texto("label")), t(fila.texto("value", "Not detected")), unidad, color, if (enLinea) "" else detalle)
}

@Composable
private fun PreparacionMovil(aplicacion: Aplicacion, datos: JsonObject, alDialogo: (String) -> Unit) {
    var seleccion by remember { mutableStateOf<Set<String>?>(null) }
    val componentes = datos.objetos("components")
    val elegidos = seleccion ?: seleccionInicialPanel(componentes)
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val movil = movil()
    GrupoMovil {
        FilaLibre {
            TextosFila(t("Prepare BC250 system"),
                t("Detected system: {distribution}", "distribution" to t(datos.texto("system", "Not detected"))))
        }
        for (componente in componentes) {
            val clave = componente.texto("key")
            val activa = libre && componente.logico("available") && clave != "runtime"
            FilaLibre(alPulsar = { seleccion = marcarComponentePanel(elegidos, clave) }, activa = activa) {
                CasillaMovil(clave in elegidos, activa || clave == "runtime")
                TextosFila(componente.texto("title"))
                FlechaDetalle { alDialogo("component:$clave") }
            }
        }
        Box(Modifier.padding(16.dp)) {
            BotonMovil(t("Prepare selected ({count})", "count" to elegidos.size.toString()),
                Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL, libre && "runtime" in elegidos) {
                prepararPanel(aplicacion, datos, elegidos)
            }
        }
        FilaAbrir("Decky · " + t("Official repositories")) {
            movil.abrirHoja {
                TituloHoja(t("Prepare BC250 system"))
                EnlacesPanelMovil(aplicacion, datos) {
                    movil.cerrarHoja()
                    alDialogo(it)
                }
                CerrarHoja()
            }
        }
    }
}

@Composable
private fun MemoriaMovil(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    val activo = datos.logico("active")
    val externo = datos.logico("kernel_driver") || datos.objeto("external").texto("state") == "active"
    val listo = datos.logico("repository_ready") || activo || datos.logico("kernel_driver")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val muestra = datos.objeto("sample")
    val valor = muestra.numero("average_c")?.takeIf { muestra.objetos("chips").isNotEmpty() }?.let { "$it °C" }
        ?: t(if (activo) "Waiting for sample" else "Off")
    fun detalle() {
        movil.abrirHoja {
            TituloHoja(t("GDDR6 memory temperature"))
            DetalleMemoriaMovil(aplicacion.lectura("dashboard").objeto("gddr6"))
            CerrarHoja()
        }
    }
    FilaLibre(alPulsar = ::detalle) {
        TextosFila(t("GDDR6 memory temperature"), valor)
        when {
            externo -> EnlaceMovil(t("Details"), alPulsar = ::detalle)
            !listo -> BotonMovil(t("Prepare readings"), activo = libre) { prepararMemoriaPanel(aplicacion) }
            activo -> BotonMovil(t("Stop"), activo = aplicacion.puedeControlar && !aplicacion.trabajo.terminado &&
                aplicacion.trabajo.titulo == t("GDDR6 memory temperature")) { aplicacion.interrumpirTrabajo() }
            else -> BotonMovil(t("Monitor live"), activo = libre && datos.logico("can_monitor")) {
                monitorizarMemoriaPanel(aplicacion, datos)
            }
        }
    }
}

@Composable
private fun DetalleMemoriaMovil(datos: JsonObject) {
    val muestra = datos.objeto("sample")
    GrupoMovil {
        muestra.numero("average_c")?.let { FilaDato(t("Avg"), it.toString(), "°C") }
        muestra.numero("hotspot_c")?.let { FilaDato(t("Hotspot {value}", "value" to "$it °C"), "") }
        for (chip in muestra.objetos("chips")) {
            FilaDato(t("Chip {chip}", "chip" to chip.entero("chip", chip.entero("index")).toString()),
                chip.numero("temperature_c")?.toString() ?: "--", "°C")
        }
    }
    if (datos.logico("kernel_driver") || datos.objeto("external").texto("state") == "active") {
        TextoHoja(t(if (datos.logico("kernel_driver")) "Read by the kernel driver (bc250_memory)" else "Read by BC250-Telemetry"))
    }
    if (datos.texto("blocker").isNotEmpty()) TextoHoja(datos.texto("blocker"))
    if (muestra.texto("error").isNotEmpty()) TextoHoja(muestra.texto("error"))
}

@Composable
private fun AlimentacionMovil(aplicacion: Aplicacion, datos: JsonObject, alAyuda: () -> Unit) {
    if (datos.logico("vrm_present") || aplicacion.preferencias.logico("vrm_manual")) {
        GrupoMovil { for (fila in datos.objetos("rails")) LecturaPanelMovil(fila) }
    }
    if (!datos.logico("vrm_present")) {
        BotonMovil(t("How to enable"), Modifier.fillMaxWidth(), alPulsar = alAyuda)
        if (datos.logico("vrm_repair")) {
            BotonMovil(t("Repair sensor"), Modifier.fillMaxWidth(),
                activo = aplicacion.puedeControlar && aplicacion.trabajo.terminado) { repararAlimentacionPanel(aplicacion) }
        }
    }
}

@Composable
private fun EnlacesPanelMovil(aplicacion: Aplicacion, datos: JsonObject, alDialogo: (String) -> Unit) {
    val quick = datos.objeto("quick_access")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    GrupoMovil {
        FilaLibre { TextosFila(quick.texto("title"), quick.texto("detail")) }
        if (!quick.logico("supported")) FilaDato(t("Unavailable"), "")
        FilaAbrir(quick.texto("label"), activa = libre && quick.logico("supported") &&
            quick.logico("decky_plugin_root_safe", true)) { prepararDeckyPanel(aplicacion, quick) }
        FilaAbrir(t("Preview")) { alDialogo("decky") }
    }
    GrupoMovil {
        for (enlace in datos.objetos("links")) {
            val titulo = enlace.texto("key")
            FilaAbrir(t(titulo)) {
                if (titulo == "Official repositories" || titulo == t("Official repositories")) alDialogo("repositories")
                else aplicacion.abrirEnlace(enlace.texto("url"))
            }
        }
        FilaAbrir(t("Support")) { aplicacion.irA("settings", "support") }
        FilaAbrir(t("A note from the developer")) { alDialogo("note") }
        if (datos.objeto("update").logico("available")) {
            FilaAbrir(t("New update available")) { alDialogo("update") }
        }
    }
}

@Composable
private fun LecturasInstrumento(clave: String, grupos: List<JsonObject>) {
    when (clave) {
        "cpu" -> for (grupo in grupos) GrupoInstrumento(grupo)
        "gpu" -> {
            val filas = grupos.getOrNull(0)?.objetos("rows")?.take(1).orEmpty() +
                grupos.getOrNull(1)?.objetos("rows").orEmpty() +
                grupos.getOrNull(3)?.objetos("rows")?.take(2).orEmpty() +
                grupos.getOrNull(4)?.objetos("rows")?.take(4).orEmpty()
            for (fila in filas) LecturaPanelMovil(fila)
        }
        else -> {
            for (fila in grupos.firstOrNull()?.objetos("rows").orEmpty()) LecturaPanelMovil(fila)
            val disco = grupos.getOrNull(1)?.objetos("rows").orEmpty()
            disco.firstOrNull()?.let { FilaDato(t("M.2 drive"), it.texto("value"), it.texto("unit")) }
            disco.getOrNull(3)?.let { LecturaPanelMovil(it) }
            grupos.lastOrNull()?.objetos("rows")?.firstOrNull()?.let { FilaDato(t("BIOS"), it.texto("value")) }
        }
    }
}
