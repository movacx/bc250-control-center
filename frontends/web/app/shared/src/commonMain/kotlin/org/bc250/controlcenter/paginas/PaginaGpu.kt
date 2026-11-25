package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.AccionesGpuCu
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.BotonIcono
import org.bc250.controlcenter.componentes.CampoNumero
import org.bc250.controlcenter.componentes.CampoTexto
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Dialogo
import org.bc250.controlcenter.componentes.EstadoLecturaGpuCu
import org.bc250.controlcenter.componentes.FilaHerramientaGpuCu
import org.bc250.controlcenter.componentes.FlechaPlegar
import org.bc250.controlcenter.componentes.Leyenda
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.PaginaDesplazable
import org.bc250.controlcenter.componentes.RejillaGpuCu
import org.bc250.controlcenter.componentes.SeccionGpuCu
import org.bc250.controlcenter.componentes.SubPanel
import org.bc250.controlcenter.componentes.TarjetaPagina
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.edit_gray
import org.bc250.controlcenter.recursos.gamepad_menu
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasGpuCu

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
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado &&
        datos.isNotEmpty() && datos.texto("error").isEmpty() && !datos.logico("empty")
    val oberon = datos.texto("governor_backend") == "oberon-governor"
    val puedeAplicar = libre && datos.objeto("availability").logico("range")
    val techo = datos.entero("ceiling", 2000)

    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("gpu")
            aplicacion.pausar(3000)
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
        tareas.launch { revisarRangoGpu(aplicacion, minimo, maximo) }
    }
    fun guardarArranque() {
        guardarArranqueGpu(aplicacion, datos)
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
            val clasica = !oberon && aplicacion.preferencias.texto("gpu_interface") == "original"
            if (clasica) {
                GpuClasica(aplicacion, datos, libre, minimo, maximo, AccionesGpuClasica(
                    elegirRango = ::elegirRango,
                    editarPerfil = { perfil -> perfilEditado = perfil },
                    guardarArranque = ::guardarArranque,
                    aplicar = ::aplicar,
                    abrirLaboratorio = { laboratorio = true },
                    abrirConfiguracion = ::abrirConfiguracion,
                ))
            } else {
                TarjetaPagina(Modifier.fillMaxWidth(), espacio = MedidasGpuCu.espacio) {
                    if (datos.logico("dbus_responsive", true).not()) {
                        Texto(avisoSinRespuesta(datos), color = paleta.naranja, tamano = 13)
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
                            FilaHerramientaGpuCu("", t("Fine-tune over the TOML points · current ceiling {ceiling} MHz.",
                                "ceiling" to techo.toString()), tamanoDetalle = 10) {
                                AccionesGpuCu(2, 400.dp) { indice, caja ->
                                    if (indice == 0) Boton(t("Save for startup"), ::guardarArranque, caja,
                                        activo = libre && datos.objeto("availability").logico("save_boot"),
                                            alto = MedidasGpuCu.altoAccion, tamano = 12)
                                    else Boton(t("Review and apply range"), ::aplicar, caja, clase = ClaseBoton.PRINCIPAL,
                                        activo = puedeAplicar && minimo <= maximo && maximo <= techo,
                                            alto = MedidasGpuCu.altoAccion, tamano = 12)
                                }
                            }
                            val razon = datos.objeto("high_frequency_points").texto("ceiling_reason")
                            if (razon.isNotEmpty()) Texto(razon, tamano = 11, color = paleta.naranja)
                            CarrilGpu(datos.objetos("rail"), minimo, maximo, techo, libre, ::elegirRango)
                        }
                        }
                        CompatibilidadGpu(aplicacion, datos, libre)
                    } else {
                        Boton(t("Review and apply Oberon profile"), ::aplicar, clase = ClaseBoton.PRINCIPAL, activo = puedeAplicar)
                    }
                    HerramientasGpu(aplicacion, datos, libre, alLaboratorio = { laboratorio = true },
                        alConfiguracion = ::abrirConfiguracion)
                    if (!oberon) {
                        SeccionGpuCu(t("DANGER ZONE").lowercase().replaceFirstChar { letra -> letra.uppercase() }) {
                        val habilitados = datos.objeto("high_frequency_points").logico("enabled")
                        SubPanel(borde = paleta.bordeRiesgo, margen = PaddingValues(18.dp, 14.dp)) {
                            FilaHerramientaGpuCu(t("TOML points above 2000 MHz"),
                                t(("Uncomment the {extra_low}–{extra_high} MHz safe-points in config.toml (up to {voltage} mV). It " +
                                    "can hang the board or corrupt the SMU state."), "extra_low" to "2050",
                                        "extra_high" to "2400", "voltage" to "1150")) {
                                val titulo = t(if (habilitados) "Re-comment the +2000 MHz points" else "Uncomment +2000 MHz points")
                                Boton(titulo, {
                                    pedirPuntosAltos(aplicacion, !habilitados)
                                }, Modifier.width(236.dp), clase = ClaseBoton.PELIGRO,
                                    activo = libre && datos.objeto("availability").logico("high_points"),
                                        alto = MedidasGpuCu.altoAccion, tamano = 12)
                            }
                        }
                        }
                    }
                }
            }
            TarjetaPagina(Modifier.fillMaxWidth()) {
                FilaHerramientaGpuCu(t("Advanced GPU diagnostics"), tamanoTitulo = 14,
                    detalle = t("TOML safe-point controls, voltage validation and hardware details.")) {
                    EnlaceMostrar(avanzados) { avanzados = !avanzados }
                }
                LineaDivisoria()
                if (avanzados) DiagnosticosGpu(datos, minimo, maximo)
            }
            SelectorInterfazGpu(aplicacion)
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
internal fun TarjetaPerfilGpu(perfil: JsonObject, elegido: Boolean, activo: Boolean, modifier: Modifier,
    alElegir: () -> Unit, alEditar: (() -> Unit)?) {
    val paleta = ColoresActuales.current
    Column(modifier.height(MedidasGpuCu.altoPerfil)
        .marco(if (elegido) paleta.elegido else paleta.panelAlterno, if (elegido) paleta.acentoBorde else paleta.borde, Medidas.radioPanel)
        .pulsable(activo, alPulsar = alElegir).padding(horizontal = 12.dp, vertical = 11.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(Modifier.fillMaxWidth()) {
            Texto(t(perfil.texto("name")), tamano = 14, peso = 780, modifier = Modifier.weight(1f))
            if (alEditar != null) BotonIcono(Res.drawable.edit_gray, alEditar)
        }
        Texto("${perfil.entero("min")} – ${perfil.entero("max")} MHz", tamano = 16, peso = 820)
        Texto(perfil.texto("voltage"), tamano = 10, color = paleta.sutil)
    }
}

@Composable
private fun EditorPerfilGpu(aplicacion: Aplicacion, perfil: JsonObject, alCerrar: () -> Unit) {
    var nombre by remember(perfil) { mutableStateOf(t(perfil.texto("name"))) }
    var minimo by remember(perfil) { mutableStateOf(perfil.entero("min")) }
    var maximo by remember(perfil) { mutableStateOf(perfil.entero("max")) }
    fun restablecer() {
        val original = perfilGpuOriginal(perfil.texto("key"))
        nombre = t(original.nombre)
        minimo = original.minimo
        maximo = original.maximo
    }
    Dialogo(alCerrar) {
        Texto(t("EDITING PROFILE"), tamano = 15, peso = 700)
        CampoTexto(nombre, { nombre = it.take(28) }, ayuda = t("Profile name"))
        Texto(t("Min. MHz"), tamano = 13)
        CampoNumero(minimo, { minimo = it }, 500, 2400, paso = 25)
        Texto(t("Max. MHz"), tamano = 13)
        CampoNumero(maximo, { maximo = it }, 500, 2400, paso = 25)
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

/** «Mostrar ›» y «Ocultar», como el enlace del escritorio. */
@Composable
private fun EnlaceMostrar(abierto: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    Row(
        Modifier.height(26.dp).pulsable(alPulsar = alPulsar).padding(horizontal = 20.dp),
        Arrangement.spacedBy(4.dp),
        androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Texto(t(if (abierto) "Hide" else "Show"), tamano = 13, peso = 720, color = paleta.acento)
        FlechaPlegar(abierto = abierto)
    }
}

/** Los dos botones del pie: Moderno y Antiguo. */
@Composable
private fun SelectorInterfazGpu(aplicacion: Aplicacion) {
    val actual = aplicacion.preferencias.texto("gpu_interface", "modern")
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(6.dp, androidx.compose.ui.Alignment.End)) {
        for ((valor, nombre) in listOf("modern" to "Modern design", "original" to "Classic design")) {
            val clase = if (valor == actual) ClaseBoton.PRINCIPAL else ClaseBoton.NORMAL
            Boton(t(nombre), { aplicacion.guardarPreferencia("gpu_interface", JsonPrimitive(valor)) {} },
                clase = clase, activo = aplicacion.puedeControlar, alto = 31.dp, tamano = 12, peso = 650)
        }
    }
}
