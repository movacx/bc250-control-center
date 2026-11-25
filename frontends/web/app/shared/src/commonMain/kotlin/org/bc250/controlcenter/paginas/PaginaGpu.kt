package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.edit_gray
import org.bc250.controlcenter.recursos.gamepad_menu
import org.bc250.controlcenter.tema.*

/** Gobernador: el servidor obtiene los datos y realiza todas las operaciones. */
@Composable
fun PaginaGpu(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val datos = aplicacion.lectura("gpu")
    val paleta = ColoresActuales.current
    var minimo by remember { mutableStateOf(500) }
    var maximo by remember { mutableStateOf(1500) }
    var editado by remember { mutableStateOf(false) }
    var perfilEditado by remember { mutableStateOf<JsonObject?>(null) }
    var laboratorio by remember { mutableStateOf(false) }
    var borradorVoltajes by remember { mutableStateOf<Map<String, JsonElement>>(emptyMap()) }
    var configuracion by remember { mutableStateOf<JsonObject?>(null) }
    var avanzados by remember { mutableStateOf(false) }
    var trabajoAnterior by remember { mutableStateOf(aplicacion.trabajo.id) }
    LaunchedEffect(aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (aplicacion.trabajo.id != trabajoAnterior && aplicacion.trabajo.terminado) {
            editado = false
            borradorVoltajes = emptyMap()
            trabajoAnterior = aplicacion.trabajo.id
        }
    }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && datos.isNotEmpty() && datos.texto("error").isEmpty() && !datos.logico("empty")
    val oberon = datos.texto("governor_backend") == "oberon-governor"
    val techo = datos.entero("ceiling", 2000)

    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("gpu")
            delay(3000)
        }
    }
    LaunchedEffect(datos.entero("current_min"), datos.entero("current_max"), editado) {
        if (!editado) {
            minimo = datos.entero("current_min", 500)
            maximo = datos.entero("current_max", 1500)
        }
    }
    fun elegirRango(bajo: Int, alto: Int) {
        minimo = bajo
        maximo = alto
        editado = true
    }
    fun aplicar() {
        val bajo = minimo
        val alto = maximo
        tareas.launch {
            val revision = aplicacion.consultar("gpu.range", mapOf("min" to bajo.toString(), "max" to alto.toString()))
            if (revision.isEmpty()) {
                aplicacion.avisar(t("Frequency range"), error = true)
                return@launch
            }
            aplicacion.preguntarYEjecutar("gpu.profile", revision.texto("title"), revision.texto("message"),
                mapOf("min" to JsonPrimitive(bajo), "max" to JsonPrimitive(alto)), peligro = revision.logico("risk"))
        }
    }
    fun guardarArranque() {
        aplicacion.preguntarYEjecutar("gpu.save_boot", t("Save for startup"),
            t("Save active range for startup") + "\n${datos.entero("current_min")} – ${datos.entero("current_max")} MHz")
    }
    fun abrirConfiguracion() {
        tareas.launch { configuracion = aplicacion.consultar("gpu.config") }
    }

    Box(Modifier.fillMaxSize()) {
        PaginaDesplazable {
            EstadoLecturaGpuCu(aplicacion, datos.texto("error"), datos.isEmpty()) {
                tareas.launch { aplicacion.leerPagina("gpu") }
            }
            if (datos.logico("empty")) Texto(t("Not detected"), color = paleta.apagado, tamano = 13)
            TarjetaPagina(Modifier.fillMaxWidth(), espacio = MedidasGpuCu.espacio) {
                if (datos.logico("dbus_responsive", true).not()) {
                    Texto(t(if (datos.objeto("cyan_telemetry").texto("method") == "process")
                        "Cyan is running but not answering. Its usage reading is set to process, which reads every open file of every program; a Proton game keeps tens of thousands open. Choose busy-flag in Cyan kernel compatibility and apply."
                        else "Cyan is running but not answering on D-Bus, so its range cannot be read or changed right now. Restart the governor if it does not recover."), color = paleta.naranja, tamano = 13)
                }
                SeccionGpuCu(t("Operating profile"), alto = 33.dp, derecha = {
                        Boton(t("Export to Decky"), {
                            aplicacion.preguntarYEjecutar("gpu.export_decky", t("Export to Decky"))
                        }, activo = libre, alto = MedidasGpuCu.altoAccion, icono = Res.drawable.gamepad_menu, tamano = 12)
                }) {
                    Leyenda(t("One click sets the range. The pencil changes name and frequencies."), Modifier.height(16.dp))
                    val perfiles = datos.objetos("profiles")
                    RejillaGpuCu(perfiles.size, 3) { indice, modificador ->
                        val perfil = perfiles[indice]
                        TarjetaPerfilGpu(perfil, minimo == perfil.entero("min") && maximo == perfil.entero("max"),
                            libre && (oberon || perfil.entero("max") <= techo), modificador,
                            alElegir = { elegirRango(perfil.entero("min"), perfil.entero("max")) },
                            alEditar = if (oberon || !aplicacion.puedeControlar) null else { { perfilEditado = perfil } })
                    }
                }
                if (!oberon) {
                    SeccionGpuCu(t("Frequency range"), derecha = {
                        if (!datos.objeto("high_frequency_points").logico("enabled")) {
                            Texto(t("{minimum}–{maximum} MHz COMMENTED IN THE TOML", "minimum" to "2050", "maximum" to "2400"),
                                tamano = 11, peso = 800, color = paleta.rojo)
                        }
                    }) {
                    SubPanel(margen = PaddingValues(18.dp, 14.dp), espacio = 9.dp) {
                        FilaHerramientaGpuCu("", t("Fine-tune over the TOML points · current ceiling {ceiling} MHz.", "ceiling" to techo.toString()), tamanoDetalle = 10) {
                            AccionesGpuCu(2, 400.dp) { indice, caja ->
                                if (indice == 0) Boton(t("Save for startup"), ::guardarArranque, caja, activo = libre, alto = MedidasGpuCu.altoAccion, tamano = 12)
                                else Boton(t("Review and apply range"), ::aplicar, caja, clase = ClaseBoton.PRINCIPAL,
                                    activo = libre && minimo <= maximo && maximo <= techo, alto = MedidasGpuCu.altoAccion, tamano = 12)
                            }
                        }
                        val razon = datos.objeto("high_frequency_points").texto("ceiling_reason")
                        if (razon.isNotEmpty()) Texto(razon, tamano = 11, color = paleta.naranja)
                        CarrilGpu(datos.objetos("rail"), minimo, maximo, techo, libre, ::elegirRango)
                    }
                    }
                    CompatibilidadGpu(aplicacion, datos, libre)
                } else {
                    Boton(t("Review and apply Oberon profile"), ::aplicar, clase = ClaseBoton.PRINCIPAL, activo = libre)
                }
                HerramientasGpu(aplicacion, datos, libre, alLaboratorio = { laboratorio = true }, alConfiguracion = ::abrirConfiguracion)
                if (!oberon) {
                    SeccionGpuCu(t("DANGER ZONE").lowercase().replaceFirstChar { letra -> letra.uppercase() }) {
                    val habilitados = datos.objeto("high_frequency_points").logico("enabled")
                    SubPanel(borde = paleta.bordeRiesgo, margen = PaddingValues(18.dp, 14.dp)) {
                        FilaHerramientaGpuCu(t("TOML points above 2000 MHz"),
                            t("Uncomment the {extra_low}–{extra_high} MHz safe-points in config.toml (up to {voltage} mV). It can hang the board or corrupt the SMU state.", "extra_low" to "2050", "extra_high" to "2400", "voltage" to "1150")) {
                            val titulo = t(if (habilitados) "Re-comment the +2000 MHz points" else "Uncomment +2000 MHz points")
                            Boton(titulo, {
                                aplicacion.preguntarYEjecutar("gpu.high_points", titulo, titulo,
                                    mapOf("enable" to JsonPrimitive(!habilitados)), peligro = true)
                            }, Modifier.width(236.dp), clase = ClaseBoton.PELIGRO, activo = libre, alto = MedidasGpuCu.altoAccion, tamano = 12)
                        }
                    }
                    }
                }
            }
            TarjetaPagina(Modifier.fillMaxWidth()) {
                FilaHerramientaGpuCu(t("Advanced GPU diagnostics"), tamanoTitulo = 14, detalle = t("TOML safe-point controls, voltage validation and hardware details.")) {
                    Boton(t(if (avanzados) "Hide" else "Show"), { avanzados = !avanzados })
                }
                if (avanzados) DiagnosticosGpu(datos, minimo, maximo)
            }
        }
        if (perfilEditado != null) {
            EditorPerfilGpu(aplicacion, perfilEditado!!, alCerrar = { perfilEditado = null })
        }
        if (laboratorio) LaboratorioGpu(aplicacion, datos, libre, borradorVoltajes,
            alCambiarValores = { borradorVoltajes = it }, alCerrar = { laboratorio = false })
        if (configuracion != null) {
            val archivo = configuracion!!
            Dialogo({ configuracion = null }, ancho = 900.dp) {
                Texto(archivo.texto("path"), peso = 700, tamano = 13)
                TextoConsola(archivo.texto("text", archivo.texto("error")))
                Boton(t("Close"), { configuracion = null })
            }
        }
    }
}

@Composable
private fun TarjetaPerfilGpu(perfil: JsonObject, elegido: Boolean, activo: Boolean, modifier: Modifier,
    alElegir: () -> Unit, alEditar: (() -> Unit)?) {
    val paleta = ColoresActuales.current
    Column(modifier.height(MedidasGpuCu.altoPerfil)
        .marco(if (elegido) paleta.elegido else paleta.panelAlterno, if (elegido) paleta.acentoBorde else paleta.borde, Medidas.radioPanel)
        .pulsable(activo, alPulsar = alElegir).padding(horizontal = 12.dp, vertical = 11.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(Modifier.fillMaxWidth()) {
            Texto(perfil.texto("name"), tamano = 14, peso = 780, modifier = Modifier.weight(1f))
            if (alEditar != null) BotonIcono(Res.drawable.edit_gray, alEditar)
        }
        Texto("${perfil.entero("min")} – ${perfil.entero("max")} MHz", tamano = 16, peso = 820)
        Texto(perfil.texto("voltage"), tamano = 10, color = paleta.sutil)
    }
}

@Composable
private fun EditorPerfilGpu(aplicacion: Aplicacion, perfil: JsonObject, alCerrar: () -> Unit) {
    var nombre by remember(perfil) { mutableStateOf(perfil.texto("name")) }
    var minimo by remember(perfil) { mutableStateOf(perfil.entero("min")) }
    var maximo by remember(perfil) { mutableStateOf(perfil.entero("max")) }
    fun restablecer() {
        val clave = perfil.texto("key")
        nombre = when (clave) { "balanced" -> t("Balanced"); "gaming" -> t("Gaming"); else -> t("Benchmark") }
        minimo = if (clave == "balanced") 500 else 1000
        maximo = when (clave) { "balanced" -> 1500; "gaming" -> 1850; else -> 2000 }
    }
    Dialogo(alCerrar) {
        Texto(t("EDITING PROFILE"), tamano = 15, peso = 700)
        CampoTexto(nombre, { nombre = it.take(28) }, ayuda = t("Profile name"))
        Texto(t("Min. MHz"), tamano = 13); CampoNumero(minimo, { minimo = it }, 500, 2400, paso = 25)
        Texto(t("Max. MHz"), tamano = 13); CampoNumero(maximo, { maximo = it }, 500, 2400, paso = 25)
        Boton(t("Reset"), ::restablecer)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Boton(t("Cancel"), alCerrar)
            Boton(t("Save profile"), {
                aplicacion.guardar("gpu.profile", mapOf("key" to JsonPrimitive(perfil.texto("key")),
                    "name" to JsonPrimitive(nombre), "min" to JsonPrimitive(minimo), "max" to JsonPrimitive(maximo)), "gpu")
                alCerrar()
            }, clase = ClaseBoton.PRINCIPAL, activo = nombre.isNotBlank() && minimo <= maximo)
        }
    }
}
