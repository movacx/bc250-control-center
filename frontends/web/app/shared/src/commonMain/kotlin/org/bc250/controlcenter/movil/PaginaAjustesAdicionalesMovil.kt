package org.bc250.controlcenter.movil

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.paginas.EstadoExtras
import org.bc250.controlcenter.paginas.EstadoMando
import org.bc250.controlcenter.paginas.cambiarAutomatizacionTv
import org.bc250.controlcenter.paginas.colorExtras
import org.bc250.controlcenter.paginas.guardarHelix
import org.bc250.controlcenter.tema.ColoresActuales

private val PestanasAdicionales = listOf(
    "compatibility" to "Compatibility", "upscaling" to "Upscaling", "memory" to "Memory & Swap", "drivers" to "Drivers",
)

@Composable
fun PaginaAjustesAdicionalesMovil(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val estado = remember(aplicacion) { EstadoExtras(aplicacion, tareas) }
    val telefono = movil()
    LaunchedEffect(aplicacion.partePedida) {
        val indice = PestanasAdicionales.indexOfFirst { it.first == aplicacion.partePedida }
        if (indice >= 0 && aplicacion.pagina == "extras") {
            telefono.elegirPestana("extras", indice)
            aplicacion.partePedida = ""
        }
    }
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("extras")
            delay(6000)
        }
    }
    val datos = aplicacion.lectura("extras")
    val pestana = PestanasAdicionales[telefono.pestana("extras").coerceIn(PestanasAdicionales.indices)].first
    PaginaMovil("extras") {
        FilaOpciones(PestanasAdicionales.map { (clave, nombre) -> clave to t(nombre) }, setOf(pestana)) { elegida ->
            telefono.elegirPestana("extras", PestanasAdicionales.indexOfFirst { it.first == elegida })
        }
        EstadoLecturaMovil(datos)
        if (datos.isEmpty()) {
            BotonMovil(t("Retry"), Modifier.fillMaxWidth()) { tareas.launch { aplicacion.leerPagina("extras") } }
        } else {
            val paneles = datos.objeto("tabs").objeto(pestana).objetos("panels")
            if (pestana == "memory") {
                MemoriaMovil(estado, datos, paneles)
            } else {
                for (panel in paneles) PanelAdicionalMovil(estado, pestana, panel)
            }
            NotaMovil(t("Detected system: {distribution}", "distribution" to datos.texto("system", t("Not detected"))))
        }
    }
}

@Composable
private fun PanelAdicionalMovil(estado: EstadoExtras, pestana: String, panel: JsonObject) {
    val telefono = movil()
    SeccionMovil(panel.texto("title")) {
        if (panel.texto("detail").isNotEmpty()) NotaMovil(panel.texto("detail"))
        if (panel.texto("value").isNotEmpty()) NotaMovil(panel.texto("value"))
        GrupoMovil {
            for (lectura in panel.objetos("readings")) {
                FilaDato(lectura.texto("label"), lectura.texto("value"), color = colorExtras(lectura.texto("tone")))
            }
            for (fila in panel.objetos("rows")) {
                FilaAbrir(fila.texto("title"), fila.texto("scope").ifEmpty { fila.texto("detail") }, fila.texto("value"),
                    colorValor = colorExtras(fila.texto("tone"))) {
                    telefono.abrirHoja { DetalleAdicionalMovil(estado, pestana, fila.texto("id")) }
                }
            }
        }
    }
}

@Composable
private fun DetalleAdicionalMovil(estado: EstadoExtras, pestana: String, id: String) {
    val datos = estado.aplicacion.lectura("extras")
    val fila = datos.objeto("tabs").objeto(pestana).objetos("panels")
        .flatMap { it.objetos("rows") }.firstOrNull { it.texto("id") == id } ?: ObjetoVacio
    val telefono = movil()
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado
    TituloHoja(fila.texto("title"))
    TextoHoja(fila.texto("detail"))
    GrupoMovil {
        FilaDato(t("Status"), fila.texto("value"), color = colorExtras(fila.texto("tone")))
        if (fila.texto("scope").isNotEmpty()) FilaDato(t("Scope"), fila.texto("scope"))
    }
    for ((clave, titulo) in listOf("risk" to "DANGER ZONE", "undo" to "Restore", "blocked" to "Unavailable")) {
        if (fila.texto(clave).isNotEmpty()) {
            SeccionMovil(t(titulo)) { TextoHoja(fila.texto(clave)) }
        }
    }
    for (enlace in fila.objetos("links")) {
        BotonMovil(enlace.texto("label"), Modifier.fillMaxWidth()) {
            estado.aplicacion.abrirEnlace(enlace.texto("url"))
        }
    }
    for ((indice, operacion) in fila.objetos("actions").withIndex()) {
        val clase = when {
            operacion.logico("danger") -> ClaseBoton.PELIGRO
            indice == 0 && fila.texto("tone") != "ok" && !operacion.logico("removal") -> ClaseBoton.PRINCIPAL
            else -> ClaseBoton.NORMAL
        }
        BotonMovil(operacion.texto("label"), Modifier.fillMaxWidth(), clase,
            libre && operacion.logico("enabled", true)) {
            estado.pulsar(pestana, fila, operacion)
            if (estado.mandoTv) {
                telefono.abrirHoja { MandoTvMovil(estado.aplicacion) }
                estado.mandoTv = false
            } else {
                telefono.abrirHoja { PasoAdicionalMovil(estado) }
            }
        }
    }
    if (pestana == "upscaling" && fila.texto("title").startsWith("HelixSR") &&
        datos.objetos("helixsr_settings").isNotEmpty()) {
        BotonMovil(t("Settings"), Modifier.fillMaxWidth(), activo = libre) {
            telefono.abrirHoja { HelixMovil(estado) }
        }
    }
    CerrarHoja()
}

@Composable
private fun PasoAdicionalMovil(estado: EstadoExtras) {
    val telefono = movil()
    val paso = estado.dialogo ?: return
    TituloHoja(t(paso.texto("title", t("Additional settings"))))
    when (paso.texto("kind")) {
        "loading" -> TextoHoja(t("Loading"))
        "choice" -> GrupoMovil {
            for (opcion in paso.objetos("options")) {
                FilaAbrir(opcion.texto("label")) { opcion["value"]?.let(estado::elegir) }
            }
        }
        "error" -> NotaMovil(paso.texto("error"), ColoresActuales.current.naranja)
        else -> TextoHoja(paso.texto("detail"))
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) {
            estado.dialogo = null
            telefono.cerrarHoja()
        }
        if (paso.texto("kind") == "confirm") {
            BotonMovil(t("Continue"), Modifier.weight(1f),
                if (paso.logico("danger")) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL,
                estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado) {
                estado.ejecutarConfirmado()
                telefono.cerrarHoja()
            }
        }
    }
}

@Composable
private fun MemoriaMovil(estado: EstadoExtras, datos: JsonObject, paneles: List<JsonObject>) {
    val filas = paneles.getOrNull(1)?.objetos("rows").orEmpty()
    val swap = filas.getOrNull(0) ?: ObjetoVacio
    val ttm = filas.getOrNull(1) ?: ObjetoVacio
    val vram = filas.getOrNull(2) ?: ObjetoVacio
    val telefono = movil()
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado
    var limite by remember { mutableStateOf<JsonElement?>(null) }
    val opciones = ttm.objeto("form").objetos("options").filter { it.texto("value") != "-1" }
    val actual = datos.texto("keep_policy", "preserve")
    var politica by remember { mutableStateOf(actual) }
    SeccionMovil(t("Dynamic GPU Memory Limit (TTM)")) {
        GrupoMovil {
            Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                TextoHoja(ttm.texto("value"))
                SegmentadoMovil(opciones.map { it.texto("value") to it.texto("label") },
                    (limite as? JsonPrimitive)?.content.orEmpty(), libre) { valor ->
                    limite = opciones.firstOrNull { it.texto("value") == valor }?.get("value")
                }
            }
            TiraAcciones(
                AccionTira(t("Apply TTM"), libre && limite != null) {
                    limite?.let { estado.abrirConRespuesta("memory", ttm, it) }
                    telefono.abrirHoja { PasoAdicionalMovil(estado) }
                },
                AccionTira(t("More")) { telefono.abrirHoja { LimiteMemoriaMovil(estado, false) } },
            )
        }
    }
    SeccionMovil(t("Swap and compression")) {
        for (opcion in datos.objetos("swap_policies")) {
            TarjetaPerfilMovil(opcion.texto("title"), "", "", politica == opcion.texto("value")) {
                politica = opcion.texto("value")
            }
        }
        BotonMovil(t("Apply Swap"), Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL, libre && politica != actual) {
            estado.abrirConRespuesta("memory", swap, JsonPrimitive(politica))
            telefono.abrirHoja { PasoAdicionalMovil(estado) }
        }
    }
    GrupoMovil {
        FilaAbrir(t("VRAM size (UMA_SIZE)"), vram.texto("value")) {
            telefono.abrirHoja { LimiteMemoriaMovil(estado, true) }
        }
        FilaAbrir(t("View detailed status")) {
            telefono.abrirHoja {
                TituloHoja(t("View detailed status"))
                GrupoMovil {
                    for (lectura in paneles.firstOrNull()?.objetos("readings").orEmpty()) {
                        FilaDato(lectura.texto("label"), lectura.texto("value"), color = colorExtras(lectura.texto("tone")))
                    }
                }
                for (opcion in datos.objetos("swap_policies")) {
                    SeccionMovil(opcion.texto("title")) { TextoHoja(opcion.texto("detail")) }
                }
                CerrarHoja()
            }
        }
    }
}

@Composable
private fun LimiteMemoriaMovil(estado: EstadoExtras, vram: Boolean) {
    val datos = estado.aplicacion.lectura("extras")
    val fila = datos.objeto("tabs").objeto("memory").objetos("panels").getOrNull(1)
        ?.objetos("rows")?.getOrNull(if (vram) 2 else 1) ?: ObjetoVacio
    var elegido by remember { mutableStateOf<JsonElement?>(null) }
    val telefono = movil()
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado
    TituloHoja(t(if (vram) "VRAM size (UMA_SIZE)" else "Dynamic GPU Memory Limit (TTM)"))
    TextoHoja(fila.texto("value"))
    if (vram) NotaMovil(t("A reboot may be required."))
    GrupoMovil {
        FilaRadio(t(if (vram) "Keep current VRAM size" else "Keep current TTM limit"), elegido == null) { elegido = null }
        for (opcion in fila.objeto("form").objetos("options")) {
            FilaRadio(opcion.texto("label"), elegido == opcion["value"], activa = libre) { elegido = opcion["value"] }
        }
    }
    BotonMovil(t(if (vram) "Apply VRAM" else "Apply TTM"), Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL,
        libre && elegido != null) {
        elegido?.let { estado.abrirConRespuesta("memory", fila, it) }
        telefono.abrirHoja { PasoAdicionalMovil(estado) }
    }
    CerrarHoja()
}

@Composable
private fun HelixMovil(estado: EstadoExtras) {
    val cambios = remember { mutableStateMapOf<String, JsonElement>() }
    val ajustes = estado.aplicacion.lectura("extras").objetos("helixsr_settings")
    val telefono = movil()
    val libre = estado.aplicacion.puedeControlar && estado.aplicacion.trabajo.terminado
    TituloHoja(t("HelixSR settings"))
    GrupoMovil {
        for (ajuste in ajustes) {
            val clave = ajuste.texto("id")
            val actual = cambios[clave] ?: ajuste["value"]
            val opciones = (ajuste["choices"] as? JsonArray).orEmpty()
            when {
                ajuste.texto("kind") == "bool" -> {
                    FilaInterruptor(ajuste.texto("label"), (actual as? JsonPrimitive)?.content == "true", activa = libre) {
                        cambios[clave] = JsonPrimitive(it)
                    }
                }
                opciones.isNotEmpty() -> {
                    FilaLibre { TextosFila(ajuste.texto("label")) }
                    for (opcion in opciones) {
                        FilaRadio((opcion as JsonPrimitive).content, actual == opcion, activa = libre) {
                            cambios[clave] = opcion
                        }
                    }
                }
                else -> {
                    var escrito by remember(clave) { mutableStateOf((actual as? JsonPrimitive)?.content.orEmpty()) }
                    Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                        TextoHoja(ajuste.texto("label"))
                        CampoMovil(escrito, Modifier.fillMaxWidth(), numerico = true, activo = libre) { valor ->
                            escrito = valor
                            val numero = valor.replace(',', '.').toDoubleOrNull()
                            if (numero != null && numero in (ajuste.numero("min") ?: 0.0)..(ajuste.numero("max") ?: 1.0)) {
                                cambios[clave] = JsonPrimitive(numero)
                            }
                        }
                    }
                }
            }
        }
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { telefono.cerrarHoja() }
        BotonMovil(t("Save"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && cambios.isNotEmpty()) {
            guardarHelix(estado, cambios.toMap())
            telefono.cerrarHoja()
        }
    }
}

@Composable
private fun MandoTvMovil(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val estado = remember { EstadoMando(aplicacion, tareas) }
    val telefono = movil()
    val paleta = ColoresActuales.current
    LaunchedEffect(estado) { estado.leer() }
    TituloHoja(t("TV control"), t(if (estado.enAjustes) "Back" else "Settings")) { estado.enAjustes = !estado.enAjustes }
    if (estado.enAjustes) {
        TextoHoja(estado.datos.texto("through"))
        GrupoMovil {
            for ((clave, titulo) in listOf("tv" to "TV", "receiver" to "Receiver", "address" to "This computer")) {
                FilaDato(t(titulo), estado.datos.texto(clave))
            }
        }
        SeccionMovil(t("Automatic")) {
            for (fila in estado.datos.objetos("automation")) {
                GrupoMovil {
                    FilaLibre { TextosFila(fila.texto("title"), fila.texto("detail")) }
                    if (fila.texto("note").isNotEmpty()) NotaMovil(fila.texto("note"), paleta.naranja)
                    Column(Modifier.padding(14.dp)) {
                        BotonMovil(t(if (fila.logico("installed")) "Remove" else "Install"), Modifier.fillMaxWidth(),
                            activo = aplicacion.puedeControlar && aplicacion.trabajo.terminado && !fila.logico("foreign")) {
                            telefono.cerrarHoja()
                            cambiarAutomatizacionTv(aplicacion, fila)
                        }
                    }
                }
            }
        }
        BotonMovil(t("Check"), Modifier.fillMaxWidth(), activo = !estado.ocupado) { estado.comprobar() }
    } else {
        Box(Modifier.fillMaxWidth(), Alignment.Center) {
            Column(Modifier.width(220.dp).marco(paleta.panelElevado, paleta.bordeFuerte, 40.dp).padding(26.dp),
                Arrangement.spacedBy(12.dp), Alignment.CenterHorizontally) {
                TextoHoja(t("TV"))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TeclaTvMovil(estado, "tv-on", "Turn the TV on", "⏻", Modifier.size(54.dp))
                    TeclaTvMovil(estado, "tv-off", "Turn the TV off", "⏻", Modifier.size(54.dp))
                }
                TeclaTvMovil(estado, "switch", "Use this input", t("Use this input"), Modifier.fillMaxWidth())
                TextoHoja(t("Receiver"))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TeclaTvMovil(estado, "volume-up", "Volume up", "+", Modifier.size(54.dp))
                    TeclaTvMovil(estado, "volume-down", "Volume down", "−", Modifier.size(54.dp))
                }
            }
        }
        GrupoMovil {
            FilaDato(t("TV"), estado.datos.texto("tv", "--"))
            FilaDato(t("Receiver"), estado.datos.texto("receiver", "--"))
        }
        ParejaBotones {
            TeclaTvMovil(estado, "amp-on", "Wake the receiver", t("Wake the receiver"), Modifier.weight(1f))
            TeclaTvMovil(estado, "amp-off", "Receiver standby", t("Receiver standby"), Modifier.weight(1f))
        }
        TeclaTvMovil(estado, "mute", "Mute", t("Mute"), Modifier.fillMaxWidth())
        NotaMovil(estado.mensaje)
    }
    CerrarHoja()
}

@Composable
private fun TeclaTvMovil(estado: EstadoMando, orden: String, nombre: String, texto: String, modifier: Modifier) {
    val activo = estado.datos.logico("ready") && !estado.ocupado && estado.aplicacion.puedeControlar
    val etiqueta = t(nombre)
    val tactil = modifier.semantics { contentDescription = etiqueta }
    if (orden in listOf("tv-on", "tv-off", "volume-up", "volume-down")) {
        val paleta = ColoresActuales.current
        val color = when {
            !activo -> paleta.textoInactivo
            orden == "tv-on" -> paleta.verde
            orden == "tv-off" -> paleta.rojo
            else -> paleta.texto
        }
        Box(tactil.marco(paleta.control, paleta.bordeFuerte, if (orden.startsWith("tv-")) 27.dp else 14.dp)
            .pulsable(activo) { estado.enviar(orden) }, Alignment.Center) {
            Texto(texto, tamano = 24, color = color)
        }
    } else {
        BotonMovil(texto, tactil, activo = activo) { estado.enviar(orden) }
    }
}
