package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.BarraUso
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.BotonIcono
import org.bc250.controlcenter.componentes.CampoNumero
import org.bc250.controlcenter.componentes.CampoTexto
import org.bc250.controlcenter.componentes.Casilla
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Eleccion
import org.bc250.controlcenter.componentes.FilaEleccion
import org.bc250.controlcenter.componentes.Leyenda
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Opcion
import org.bc250.controlcenter.componentes.PaginaDesplazable
import org.bc250.controlcenter.componentes.SubPanel
import org.bc250.controlcenter.componentes.TarjetaLectura
import org.bc250.controlcenter.componentes.TarjetaPagina
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.TituloPanel
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.numero
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.edit_gray
import org.bc250.controlcenter.recursos.gamepad_menu
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import kotlin.math.roundToInt

private const val NUCLEOS_EN_LA_PLACA = 8
private const val MASCARA_NORMAL = 0x77

/** Un perfil de funcionamiento de la CPU. */
data class PerfilCpu(
    val clave: String,
    val nombre: String,
    val frecuencia: Int,
    val voltaje: Int,
    val temperatura: Int,
)

/** Los valores menor y mayor que acepta un campo. */
class Limites(val menor: Int, val mayor: Int)

private fun leerPerfil(datos: JsonObject): PerfilCpu {
    return PerfilCpu(
        clave = datos.texto("key"),
        nombre = datos.texto("name"),
        frecuencia = datos.entero("frequency"),
        voltaje = datos.entero("vid"),
        temperatura = datos.entero("temperature"),
    )
}

private fun leerLimites(datos: JsonObject, nombre: String): Limites {
    val limites = datos.objeto("limits").objeto(nombre)
    return Limites(limites.entero("min"), limites.entero("max"))
}

@Composable
fun PaginaCpu(aplicacion: Aplicacion) {
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("cpu")
            delay(3000)
        }
    }
    val datos = aplicacion.lectura("cpu")
    PaginaDesplazable {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth >= 900.dp) {
                DosColumnas(aplicacion, datos)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(Medidas.espacio)) {
                    ColumnaIzquierda(aplicacion, datos, Modifier.fillMaxWidth())
                    TarjetaEstado(aplicacion, datos, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun DosColumnas(aplicacion: Aplicacion, datos: JsonObject) {
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), Arrangement.spacedBy(Medidas.espacio)) {
        ColumnaIzquierda(aplicacion, datos, Modifier.weight(965f))
        TarjetaEstado(aplicacion, datos, Modifier.weight(643f).fillMaxHeight())
    }
}

@Composable
private fun ColumnaIzquierda(aplicacion: Aplicacion, datos: JsonObject, modifier: Modifier) {
    Column(modifier, Arrangement.spacedBy(Medidas.espacio)) {
        TarjetaConfiguracion(aplicacion, datos)
        TarjetaConsola(aplicacion, datos)
    }
}

// -- configuración: perfil, escala y aplicar -------------------------------------------------

@Composable
private fun TarjetaConfiguracion(aplicacion: Aplicacion, datos: JsonObject) {
    val perfiles = datos.objetos("profiles").map(::leerPerfil)
    var elegido by remember { mutableStateOf("board_average") }
    var escalaManual by remember { mutableStateOf(false) }
    var escala by remember { mutableIntStateOf(-34) }
    val perfil = perfiles.firstOrNull { it.clave == elegido }

    fun aplicar() {
        if (perfil != null) {
            pedirAplicacion(aplicacion, perfil, escalaManual, escala)
        }
    }

    TarjetaPagina(Modifier.fillMaxWidth()) {
        PanelPerfiles(aplicacion, datos, perfiles, elegido) { clave -> elegido = clave }
        PanelEscala(escalaManual, escala, { valor -> escalaManual = valor }, { valor -> escala = valor })
        val nombre = if (escalaManual) "Apply temporary OC + manual scale" else "Apply configuration + automatic scale"
        Boton(
            texto = t(nombre),
            alPulsar = ::aplicar,
            clase = ClaseBoton.PRINCIPAL,
            activo = perfil != null && aplicacion.trabajo.terminado,
            alto = 44.dp,
            tamano = 13,
            peso = 780,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

private fun pedirAplicacion(aplicacion: Aplicacion, perfil: PerfilCpu, escalaManual: Boolean, escala: Int) {
    val parametros = mutableMapOf<String, JsonElement>(
        "frequency" to JsonPrimitive(perfil.frecuencia),
        "temperature" to JsonPrimitive(perfil.temperatura),
        "manual" to JsonPrimitive(escalaManual),
    )
    val detalle: String
    if (escalaManual) {
        parametros["scale"] = JsonPrimitive(escala)
        detalle = "${perfil.frecuencia} MHz · ${perfil.temperatura} °C · $escala"
    } else {
        parametros["vid"] = JsonPrimitive(perfil.voltaje)
        detalle = "${perfil.frecuencia} MHz · ${perfil.voltaje} mV · ${perfil.temperatura} °C"
    }
    val titulo = if (escalaManual) "Apply temporary OC + manual scale" else "Apply configuration + automatic scale"
    aplicacion.preguntarYEjecutar("cpu.apply", t(titulo), detalle, parametros, peligro = true)
}

@Composable
private fun PanelPerfiles(
    aplicacion: Aplicacion,
    datos: JsonObject,
    perfiles: List<PerfilCpu>,
    elegido: String,
    alElegir: (String) -> Unit,
) {
    SubPanel {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            TituloPanel(t("Operating profile"), Modifier.weight(1f))
            Boton(
                texto = t("Export to Decky"),
                alPulsar = { exportarADecky(aplicacion) },
                clase = ClaseBoton.COMPACTO,
                alto = 35.dp,
                tamano = 12,
                peso = 700,
                icono = Res.drawable.gamepad_menu,
            )
        }
        Leyenda(t("One click sets the range. The pencil changes name and frequencies."))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(Medidas.espacioCorto)) {
            for (perfil in perfiles) {
                TarjetaPerfil(
                    aplicacion = aplicacion,
                    datos = datos,
                    perfil = perfil,
                    elegida = perfil.clave == elegido,
                    modifier = Modifier.weight(1f),
                    alElegir = { alElegir(perfil.clave) },
                )
            }
        }
    }
}

private fun exportarADecky(aplicacion: Aplicacion) {
    aplicacion.preguntarYEjecutar("cpu.export_decky", t("Export to Decky"))
}

@Composable
private fun TarjetaPerfil(
    aplicacion: Aplicacion,
    datos: JsonObject,
    perfil: PerfilCpu,
    elegida: Boolean,
    modifier: Modifier,
    alElegir: () -> Unit,
) {
    val paleta = ColoresActuales.current
    var editando by remember { mutableStateOf(false) }
    val fondo = if (elegida) paleta.elegido else paleta.panelAlterno
    val borde = if (elegida) paleta.acentoBorde else paleta.borde
    Column(
        modifier
            .marco(fondo, borde, Medidas.radioPanel)
            .pulsable(activo = !editando, alPulsar = alElegir)
            .padding(start = 12.dp, top = 11.dp, end = 12.dp, bottom = 12.dp),
    ) {
        if (editando) {
            EditorPerfil(aplicacion, datos, perfil, alTerminar = { editando = false }, alGuardar = alElegir)
        } else {
            VistaPerfil(perfil, alEditar = { editando = true })
        }
    }
}

@Composable
private fun VistaPerfil(perfil: PerfilCpu, alEditar: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Texto(t(perfil.nombre), tamano = 14, peso = 780, lineas = 1, modifier = Modifier.weight(1f))
            BotonIcono(Res.drawable.edit_gray, alEditar)
        }
        Texto("${perfil.frecuencia} MHz", tamano = 16, peso = 820)
        Leyenda("${perfil.voltaje} mV · ${perfil.temperatura} °C")
    }
}

@Composable
private fun EditorPerfil(
    aplicacion: Aplicacion,
    datos: JsonObject,
    perfil: PerfilCpu,
    alTerminar: () -> Unit,
    alGuardar: () -> Unit,
) {
    var nombre by remember { mutableStateOf(t(perfil.nombre)) }
    var frecuencia by remember { mutableIntStateOf(perfil.frecuencia) }
    var voltaje by remember { mutableIntStateOf(perfil.voltaje) }
    var temperatura by remember { mutableIntStateOf(perfil.temperatura) }
    val limitesFrecuencia = leerLimites(datos, "frequency")
    val limitesVoltaje = leerLimites(datos, "vid")
    val limitesTemperatura = leerLimites(datos, "temperature")

    fun volverAlOriginal() {
        val original = datos.objetos("default_profiles").map(::leerPerfil).firstOrNull { it.clave == perfil.clave }
        if (original != null) {
            nombre = t(original.nombre)
            frecuencia = original.frecuencia
            voltaje = original.voltaje
            temperatura = original.temperatura
        }
    }

    fun guardar() {
        val parametros = mapOf<String, JsonElement>(
            "key" to JsonPrimitive(perfil.clave),
            "name" to JsonPrimitive(nombre),
            "frequency" to JsonPrimitive(frecuencia),
            "vid" to JsonPrimitive(voltaje),
            "temperature" to JsonPrimitive(temperatura),
        )
        aplicacion.guardar("cpu.profile", parametros, "cpu")
        alTerminar()
        alGuardar()
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            val acento = ColoresActuales.current.acento
            Texto(t("EDITING PROFILE"), tamano = 11, peso = 800, color = acento, modifier = Modifier.weight(1f))
            Boton(t("Reset"), ::volverAlOriginal, alto = 30.dp, tamano = 12)
        }
        CampoTexto(nombre, { nuevo -> nombre = nuevo.take(28) }, Modifier.fillMaxWidth(), ayuda = t("Profile name"))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
            CampoConNombre(t("CPU frequency"), Modifier.weight(1f)) {
                CampoNumero(frecuencia, { valor -> frecuencia = valor }, limitesFrecuencia.menor, limitesFrecuencia.mayor, paso = 50)
            }
            CampoConNombre(t("VID limit"), Modifier.weight(1f)) {
                CampoNumero(voltaje, { valor -> voltaje = valor }, limitesVoltaje.menor, limitesVoltaje.mayor, paso = 5)
            }
        }
        CampoConNombre(t("Temperature cap"), Modifier.fillMaxWidth()) {
            CampoNumero(temperatura, { valor -> temperatura = valor }, limitesTemperatura.menor, limitesTemperatura.mayor)
        }
        Leyenda(
            t(
                "Enter a value between {minimum} and {maximum} MHz.",
                "minimum" to limitesFrecuencia.menor.toString(),
                "maximum" to limitesFrecuencia.mayor.toString(),
            ),
        )
        Boton(t("Save profile"), ::guardar, modifier = Modifier.fillMaxWidth(), alto = 40.dp)
    }
}

@Composable
private fun CampoConNombre(nombre: String, modifier: Modifier, campo: @Composable () -> Unit) {
    Column(modifier, Arrangement.spacedBy(3.dp)) {
        Texto(nombre, tamano = 11, peso = 700, color = ColoresActuales.current.apagado)
        campo()
    }
}

@Composable
private fun PanelEscala(
    manual: Boolean,
    escala: Int,
    alCambiarManual: (Boolean) -> Unit,
    alCambiarEscala: (Int) -> Unit,
) {
    val paleta = ColoresActuales.current
    SubPanel {
        TituloPanel(t("Live scale test"))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .marco(paleta.grupo, paleta.borde, Medidas.radioPanel)
                .padding(start = 14.dp, top = 11.dp, end = 14.dp, bottom = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Casilla(manual, alCambiarManual)
            Column(Modifier.weight(1f).padding(start = 16.dp, end = 10.dp)) {
                Texto(t("Use manual scale"), tamano = 11, peso = 760, color = paleta.apagado)
                Leyenda(
                    t(
                        "Enter the exact scale you want. It is stress-tested in 100 MHz steps before it stays applied, " +
                            "the way automatic detection tests its own.",
                    ),
                    Modifier.padding(top = 2.dp),
                )
            }
            CampoNumero(
                valor = escala,
                alCambiar = alCambiarEscala,
                minimo = -50,
                maximo = 0,
                sufijo = "scale",
                activo = manual,
                modifier = Modifier.width(143.dp),
            )
        }
    }
}

/** Los tres puntos bajo la consola. */
@Composable
private fun AgarreHorizontal() {
    Row(
        modifier = Modifier.fillMaxWidth().height(32.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(3) {
            Box(Modifier.size(4.dp).background(ColoresActuales.current.apagado, RoundedCornerShape(2.dp)))
        }
    }
}

// -- consola y resumen del procesador --------------------------------------------------------

private val DatosProcesador = listOf(
    "model_name" to "Processor",
    "architecture" to "Architecture",
    "topology" to "Topology",
    "platform_process" to "Platform / process",
    "microcode" to "Microcode",
    "cache" to "Cache hierarchy",
    "features" to "Instruction features",
    "total_usage_percent" to "Total CPU load",
)

@Composable
private fun TarjetaConsola(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val trabajo = aplicacion.trabajo
    val inicial = t("CPU / SMU session console ready. No hardware command has been executed.")
    val contenido = if (trabajo.texto.isEmpty()) inicial else trabajo.texto
    TarjetaPagina(Modifier.fillMaxWidth(), margen = PaddingValues(14.dp), espacio = 0.dp) {
        TextoConsola(contenido, Modifier.fillMaxWidth().height(219.dp), paleta.color("console_text"))
        AgarreHorizontal()
        TituloPanel(t("Processor overview"))
        Spacer(Modifier.height(8.dp))
        val procesador = datos.objeto("unlock").objeto("processor")
        for (indice in DatosProcesador.indices step 2) {
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), Arrangement.spacedBy(16.dp)) {
                DatoProcesador(DatosProcesador[indice], procesador, indice == 0, Modifier.weight(1f).fillMaxHeight())
                DatoProcesador(DatosProcesador[indice + 1], procesador, indice == 0, Modifier.weight(1f).fillMaxHeight())
            }
        }
    }
}

@Composable
private fun DatoProcesador(dato: Pair<String, String>, procesador: JsonObject, primero: Boolean, modifier: Modifier) {
    val (clave, nombre) = dato
    val valor = if (clave == "total_usage_percent") {
        porcentaje(procesador.numero(clave))
    } else {
        procesador.texto(clave, "--")
    }
    Column(modifier) {
        if (!primero) {
            LineaDivisoria()
        }
        Row(
            modifier = Modifier.weight(1f).padding(vertical = 5.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Texto(t(nombre), tamano = 13, color = ColoresActuales.current.apagado, modifier = Modifier.weight(1f))
            Texto(valor, tamano = 13, peso = 700, alineado = TextAlign.End, modifier = Modifier.weight(2f))
        }
    }
}

private fun porcentaje(valor: Double?): String {
    return if (valor == null) "--" else "${valor.roundToInt()} %"
}

// -- estado, núcleos, arranque y desbloqueo ----------------------------------------------------

@Composable
private fun TarjetaEstado(aplicacion: Aplicacion, datos: JsonObject, modifier: Modifier) {
    TarjetaPagina(modifier) {
        PanelEjecucion(aplicacion, datos)
        PanelNucleos(datos)
        PanelArranque(aplicacion, datos)
        Box(Modifier.padding(top = 10.dp)) {
            PanelDesbloqueo(aplicacion, datos)
        }
    }
}

@Composable
private fun PanelEjecucion(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val persistencia = datos.objeto("persistence")
    val ajuste = datos.objeto("tuning")
    val habilitada = persistencia.logico("enabled")
    val ultima = datos.objeto("config").entero("cpu_oc_last_applied_frequency")
    val cpu = aplicacion.metricas.objeto("cpu")
    val temperatura = cpu.numero("temperature_c")?.roundToInt()?.toString() ?: "--"
    val frecuencia = cpu.numero("frequency_mhz")?.roundToInt()?.toString() ?: "--"
    val lecturas = listOf(
        t("Boot persistence") to persistencia.texto("value", "--"),
        t("Last operation") to if (ultima > 0) "$ultima MHz" else t("None"),
        t("Applied tuning") to ajuste.texto("applied_value", "--"),
        t("Detection reference") to ajuste.texto("detection_value", "--"),
        t("Active scale") to ajuste.texto("live_value", "--"),
        t("Live CPU status") to "$temperatura °C | $frecuencia MHz",
    )
    SubPanel {
        Row(Modifier.fillMaxWidth().height(23.dp), verticalAlignment = Alignment.CenterVertically) {
            TituloPanel(t("Runtime status"), Modifier.weight(1f))
            val estado = if (habilitada) "Persistence" else "Temporary"
            val color = if (habilitada) paleta.acento else paleta.verde
            Texto(t(estado), tamano = 11, peso = 780, color = color)
        }
        for (fila in lecturas.chunked(3)) {
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), Arrangement.spacedBy(10.dp)) {
                for ((nombre, valor) in fila) {
                    TarjetaLectura(nombre, valor, Modifier.weight(1f).fillMaxHeight())
                }
            }
        }
    }
}

@Composable
private fun PanelNucleos(datos: JsonObject) {
    val nucleos = datos.objeto("unlock").objetos("cores")
    SubPanel {
        TituloPanel(t("Live core monitor"))
        Leyenda(t("Detected by the OS"))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp)) {
            val mitad = NUCLEOS_EN_LA_PLACA / 2
            ColumnaNucleos(nucleos, 0 until mitad, Modifier.weight(1f))
            ColumnaNucleos(nucleos, mitad until NUCLEOS_EN_LA_PLACA, Modifier.weight(1f))
        }
    }
}

@Composable
private fun ColumnaNucleos(nucleos: List<JsonObject>, posiciones: IntRange, modifier: Modifier) {
    Column(modifier) {
        for (posicion in posiciones) {
            val nucleo = nucleos.firstOrNull { it.entero("index", -1) == posicion }
            if (posicion != posiciones.first) {
                LineaDivisoria()
            }
            FilaNucleo(posicion, nucleo)
        }
    }
}

@Composable
private fun FilaNucleo(posicion: Int, nucleo: JsonObject?) {
    val paleta = ColoresActuales.current
    val uso = nucleo?.numero("usage_percent")
    val frecuencia = nucleo?.numero("frequency_mhz")
    val colorNombre = if (nucleo == null) paleta.sutil else paleta.apagado
    val colorValor = if (nucleo == null) paleta.sutil else paleta.texto
    Row(Modifier.fillMaxWidth().height(30.dp), verticalAlignment = Alignment.CenterVertically) {
        Texto("N${posicion + 1}", tamano = 12, peso = 800, color = colorNombre, modifier = Modifier.width(36.dp))
        val texto = if (nucleo == null) t("Hidden") else gigahercios(frecuencia)
        Texto(texto, tamano = 13, peso = 750, color = colorValor, lineas = 1, modifier = Modifier.width(84.dp))
        BarraUso(uso, Modifier.weight(1f))
        val parte = if (nucleo == null) "" else porcentaje(uso)
        Texto(parte, 12, Modifier.width(50.dp), peso = 700, color = paleta.apagado, alineado = TextAlign.End)
    }
}

private fun gigahercios(megahercios: Double?): String {
    if (megahercios == null) {
        return "--"
    }
    val centesimas = (megahercios / 10.0).roundToInt()
    val decimales = (centesimas % 100).toString().padStart(2, '0')
    return "${centesimas / 100}.$decimales GHz"
}

@Composable
private fun PanelArranque(aplicacion: Aplicacion, datos: JsonObject) {
    val habilitada = datos.objeto("persistence").logico("enabled")
    val libre = aplicacion.trabajo.terminado

    fun guardar() {
        val detalle = datos.objeto("tuning").texto("applied_value")
        aplicacion.preguntarYEjecutar("cpu.persist", t("Save for boot"), detalle)
    }

    fun quitar() {
        aplicacion.preguntarYEjecutar("cpu.persist_off", t("Remove from boot"), peligro = true)
    }

    SubPanel {
        TituloPanel(t("Boot persistence"))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
            Boton(t("Save for boot"), ::guardar, Modifier.weight(194f), ClaseBoton.PRINCIPAL, libre, peso = 740)
            Boton(t("Review persistence"), { aplicacion.ejecutar("cpu.review", t("Review persistence")) }, Modifier.weight(181f), activo = libre)
            Boton(t("Remove from boot"), ::quitar, Modifier.weight(180f), ClaseBoton.PELIGRO, libre && habilitada, 36.dp, peso = 760)
        }
    }
}

@Composable
private fun PanelDesbloqueo(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val controles = datos.objeto("unlock_controls")
    val libre = aplicacion.trabajo.terminado
    val instalado = controles.logico("installed")
    var modo by remember { mutableStateOf("") }
    val persistente = if (modo.isEmpty()) instalado else modo == "persistent"
    var mascara by remember { mutableIntStateOf(MASCARA_NORMAL) }
    var forzar by remember { mutableStateOf(false) }
    val ofrecido = controles.logico("offered")
    val permitido = libre && controles.logico(if (persistente) "persist_allowed" else "temporary_allowed")
    val accion = if (persistente) controles.texto("action") else t("Unlock cores and restart")

    fun desbloquear() {
        val nombre = if (persistente) "cpu.unlock_persist" else "cpu.unlock"
        val parametros = mapOf<String, JsonElement>(
            "force_mask" to JsonPrimitive(forzar),
            "mask" to JsonPrimitive(mascara),
        )
        aplicacion.preguntarYEjecutar(nombre, accion, datos.texto("unlock_warning"), parametros, peligro = true)
    }

    fun quitarPersistencia() {
        val mensaje = t(
            "The boot service is removed. Nothing restarts: the cores stay unlocked until the next full power-off, " +
                "which brings the board back to 6 cores.",
        )
        aplicacion.preguntarYEjecutar("cpu.unlock_persist_off", t("Remove persistence"), mensaje, peligro = true)
    }

    SubPanel(
        fondo = if (paleta.esClaro) paleta.rojoSuave else paleta.color("risk_fill"),
        borde = if (paleta.esClaro) paleta.rojoBorde else paleta.color("risk_line"),
        margen = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        espacio = 8.dp,
    ) {
        Texto(t("Unlock hidden CPU cores"), tamano = 15, peso = 800)
        OpcionDesbloqueo(
            titulo = t("Temporary"),
            detalle = t("Until the next full power-off. Nothing is installed."),
            etiqueta = "",
            elegida = !persistente,
            activa = true,
            alElegir = { modo = "temporary" },
        )
        OpcionDesbloqueo(
            titulo = t("Persistence"),
            detalle = t("Applied again by itself on every cold boot, without flashing the BIOS."),
            etiqueta = controles.texto("status"),
            elegida = persistente,
            activa = ofrecido,
            alElegir = { modo = "persistent" },
        )
        val nota = controles.texto("note")
        if (nota.isNotEmpty()) {
            Texto(nota, tamano = 12, color = paleta.naranja)
        }
        val mascaras = datos.objetos("masks").map { opcion ->
            Eleccion(opcion.texto("value"), opcion.texto("text"), opcion.texto("short"))
        }
        FilaEleccion(
            nombre = t("Core mask of this board"),
            opciones = mascaras,
            elegida = mascara.toString(),
            alElegir = { valor -> mascara = valor.toInt() },
            activa = permitido && !forzar,
            modifier = Modifier.padding(vertical = 3.dp),
        )
        Row(
            modifier = Modifier.height(29.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Casilla(forzar, { valor -> forzar = valor }, activa = permitido, deRiesgo = true)
            Texto(t("Force a non-standard core mask (-f)"), tamano = 13)
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
            Boton(accion, ::desbloquear, Modifier.weight(1f), ClaseBoton.PELIGRO, permitido, 36.dp, peso = 760)
            if (persistente && instalado) {
                val puedeQuitar = libre && controles.logico("remove_allowed")
                Boton(t("Remove persistence"), ::quitarPersistencia, Modifier.weight(1f), activo = puedeQuitar)
            } else {
                val guia = datos.texto("firmware_guide")
                Boton(t("Firmware persistence guide"), { aplicacion.abrirEnlace(guia) }, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun OpcionDesbloqueo(
    titulo: String,
    detalle: String,
    etiqueta: String,
    elegida: Boolean,
    activa: Boolean,
    alElegir: () -> Unit,
) {
    val paleta = ColoresActuales.current
    val borde = when {
        elegida -> paleta.rojo
        activa -> paleta.borde
        else -> paleta.bordeSuave
    }
    val colorTitulo = if (activa) paleta.texto else paleta.textoInactivo
    val colorDetalle = if (activa) paleta.apagado else paleta.textoInactivo
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .marco(paleta.panelAlterno, borde, Medidas.radioBoton)
            .pulsable(activa, alPulsar = alElegir)
            .padding(horizontal = 13.dp, vertical = 11.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Opcion(elegida)
        Column(Modifier.weight(1f), Arrangement.spacedBy(2.dp)) {
            Row(Modifier.fillMaxWidth()) {
                Texto(titulo, tamano = 14, peso = 700, color = colorTitulo, modifier = Modifier.weight(1f))
                if (etiqueta.isNotEmpty() && elegida) {
                    Texto(etiqueta, tamano = 12, peso = 700, color = paleta.apagado)
                }
            }
            Texto(detalle, tamano = 12, color = colorDetalle)
        }
    }
}
