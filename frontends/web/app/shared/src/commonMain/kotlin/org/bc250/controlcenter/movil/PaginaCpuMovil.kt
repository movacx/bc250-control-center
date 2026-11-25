package org.bc250.controlcenter.movil

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.numero
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.paginas.DatosProcesador
import org.bc250.controlcenter.paginas.MASCARA_NORMAL
import org.bc250.controlcenter.paginas.NUCLEOS_EN_LA_PLACA
import org.bc250.controlcenter.paginas.PerfilCpu
import org.bc250.controlcenter.paginas.accionDesbloqueo
import org.bc250.controlcenter.paginas.exportarADecky
import org.bc250.controlcenter.paginas.gigahercios
import org.bc250.controlcenter.paginas.guardarArranqueCpu
import org.bc250.controlcenter.paginas.leerLimites
import org.bc250.controlcenter.paginas.leerPerfil
import org.bc250.controlcenter.paginas.pedirAplicacion
import org.bc250.controlcenter.paginas.pedirDesbloqueo
import org.bc250.controlcenter.paginas.porcentaje
import org.bc250.controlcenter.paginas.quitarArranqueCpu
import org.bc250.controlcenter.paginas.quitarDesbloqueo
import org.bc250.controlcenter.tema.ColoresActuales
import kotlin.math.roundToInt

private const val ESCALA_MENOR = -50
private const val FRECUENCIAS = 0

/** Lo que se está eligiendo en CPU y todavía no se aplicó. */
private class EleccionCpu {
    var perfil by mutableStateOf("board_average")
    var escalaManual by mutableStateOf(false)
    var escala by mutableIntStateOf(-34)

    /** "temporary", "persistent" o vacío mientras no se elija. */
    var modo by mutableStateOf("")
    var mascara by mutableIntStateOf(0)
    var forzar by mutableStateOf(false)
}

@Composable
fun PaginaCpuMovil(aplicacion: Aplicacion) {
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("cpu")
            delay(3000)
        }
    }
    val movil = movil()
    val eleccion = remember { EleccionCpu() }
    val datos = aplicacion.lectura("cpu")
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val perfiles = datos.objetos("profiles").map(::leerPerfil)
    val perfil = perfiles.firstOrNull { opcion -> opcion.clave == eleccion.perfil }
    val enDesbloqueo = movil.detalle.isNotEmpty()
    val enFrecuencias = movil.pestana("cpu") == FRECUENCIAS
    PaginaMovil(
        clave = "cpu",
        pestanas = listOf(t("Frequencies"), t("Cores")),
        pie = when {
            enDesbloqueo -> { { BotonDesbloqueo(aplicacion, datos, eleccion, Modifier.weight(1f)) } }
            enFrecuencias -> {
                {
                    BotonMovil(t("Apply configuration"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && perfil != null) {
                        if (perfil != null) {
                            pedirAplicacion(aplicacion, perfil, eleccion.escalaManual, eleccion.escala)
                        }
                    }
                }
            }
            else -> null
        },
    ) {
        EstadoLecturaMovil(datos)
        when {
            enDesbloqueo -> Desbloqueo(aplicacion, datos, eleccion)
            enFrecuencias -> Frecuencias(aplicacion, datos, perfiles, eleccion)
            else -> Nucleos(aplicacion, datos)
        }
    }
}

/** El aviso de que todavía no hay datos o de que no se pudieron leer. */
@Composable
fun EstadoLecturaMovil(datos: JsonObject) {
    if (datos.isEmpty()) {
        NotaMovil(t("Waiting for data…"))
    } else if (datos.texto("error").isNotEmpty()) {
        NotaMovil(datos.texto("error"), ColoresActuales.current.naranja, tamano = 13)
    }
}

// -- frecuencias ---------------------------------------------------------------------------------------

@Composable
private fun Frecuencias(aplicacion: Aplicacion, datos: JsonObject, perfiles: List<PerfilCpu>, eleccion: EleccionCpu) {
    val movil = movil()
    SeccionMovil(t("Operating profile")) {
        for (perfil in perfiles) {
            TarjetaPerfilMovil(
                nombre = t(perfil.nombre),
                valor = "${perfil.frecuencia} MHz",
                detalle = "${perfil.voltaje} mV · ${perfil.temperatura} °C",
                elegido = perfil.clave == eleccion.perfil,
                alEditar = { movil.abrirHoja { EditorPerfilCpu(aplicacion, datos, perfil) } },
            ) {
                eleccion.perfil = perfil.clave
            }
        }
    }
    Arranque(aplicacion, datos)
    GrupoMovil {
        val escala = if (eleccion.escalaManual) t("Manual") + " · " + eleccion.escala else t("Automatic")
        FilaAbrir(t("Scale"), t("How the tuning is tested"), escala) {
            movil.abrirHoja { HojaEscala(eleccion) }
        }
        val aplicado = datos.objeto("tuning").texto("applied_value", "--")
        FilaAbrir(t("Tuning status"), t("Last operation and reference"), aplicado) {
            movil.abrirHoja { HojaEstado(aplicacion, datos) }
        }
    }
}

@Composable
private fun EditorPerfilCpu(aplicacion: Aplicacion, datos: JsonObject, perfil: PerfilCpu) {
    val movil = movil()
    var nombre by remember { mutableStateOf(t(perfil.nombre)) }
    var frecuencia by remember { mutableStateOf(perfil.frecuencia.toString()) }
    var voltaje by remember { mutableStateOf(perfil.voltaje.toString()) }
    var temperatura by remember { mutableStateOf(perfil.temperatura.toString()) }
    var error by remember { mutableStateOf("") }

    fun volverAlOriginal() {
        val original = datos.objetos("default_profiles").map(::leerPerfil).firstOrNull { it.clave == perfil.clave }
        if (original != null) {
            nombre = t(original.nombre)
            frecuencia = original.frecuencia.toString()
            voltaje = original.voltaje.toString()
            temperatura = original.temperatura.toString()
        }
    }

    fun numeroValido(escrito: String, limite: String): Int? {
        val limites = leerLimites(datos, limite)
        val numero = escrito.toIntOrNull()
        return if (numero != null && numero in limites.menor..limites.mayor) numero else null
    }

    fun guardar() {
        val campos = listOf("frequency" to frecuencia, "vid" to voltaje, "temperature" to temperatura)
        val parametros = mutableMapOf<String, JsonElement>("key" to JsonPrimitive(perfil.clave), "name" to JsonPrimitive(nombre))
        for ((clave, escrito) in campos) {
            val numero = numeroValido(escrito, clave)
            if (numero == null) {
                val limites = leerLimites(datos, clave)
                error = t("Enter a value between {minimum} and {maximum}.", "minimum" to limites.menor.toString(), "maximum" to limites.mayor.toString())
                return
            }
            parametros[clave] = JsonPrimitive(numero)
        }
        aplicacion.guardar("cpu.profile", parametros, "cpu")
        movil.cerrarHoja()
    }

    TituloHoja(t("Edit profile"), t("Reset"), ::volverAlOriginal)
    CampoConNombreMovil(t("Name"), nombre) { nuevo -> nombre = nuevo.take(28) }
    CampoConNombreMovil(t("CPU frequency") + " (MHz)", frecuencia, numerico = true) { nuevo -> frecuencia = nuevo }
    CampoConNombreMovil("VID (mV)", voltaje, numerico = true) { nuevo -> voltaje = nuevo }
    CampoConNombreMovil(t("Temperature cap") + " (°C)", temperatura, numerico = true) { nuevo -> temperatura = nuevo }
    if (error.isNotEmpty()) {
        NotaMovil(error, ColoresActuales.current.rojo)
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { movil.cerrarHoja() }
        BotonMovil(t("Save profile"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, aplicacion.puedeControlar, ::guardar)
    }
}

@Composable
private fun Arranque(aplicacion: Aplicacion, datos: JsonObject) {
    val paleta = ColoresActuales.current
    val encendido = datos.objeto("persistence").logico("enabled")
    val persistente = datos.objeto("persistent")
    val disponible = persistente.isNotEmpty() && persistente.logico("persistence_supported", true)
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    SeccionMovil(t("Startup")) {
        GrupoMovil {
            FilaLibre(altoMinimo = 66.dp) {
                PuntoEstado(encendido)
                val detalle = if (encendido) "Enabled · the service applies it at every start" else "Disabled · lost on restart"
                TextosFila(t("Apply at startup"), t(detalle))
                InterruptorMovil(encendido, activo = libre && (encendido || disponible)) { pedido ->
                    if (pedido) guardarArranqueCpu(aplicacion, datos) else quitarArranqueCpu(aplicacion)
                }
            }
            if (encendido) {
                FilaAbrir(t("Saved"), t("Tap to save the current tuning"), datos.objeto("tuning").texto("detection_value"), activa = libre) {
                    guardarArranqueCpu(aplicacion, datos)
                }
            }
            TiraAcciones(
                AccionTira(t("Review"), libre) { aplicacion.ejecutar("cpu.review", t("Review persistence")) },
                AccionTira(t("Export to Decky"), libre) { exportarADecky(aplicacion) },
            )
        }
    }
    val detalle = datos.objeto("persistence").texto("detail")
    if (encendido && detalle.isNotEmpty()) {
        NotaMovil(detalle, paleta.sutil)
    }
}

@Composable
private fun HojaEscala(eleccion: EleccionCpu) {
    TituloHoja(t("Scale"))
    GrupoMovil {
        FilaRadio(t("Automatic"), !eleccion.escalaManual, t("Detection tests and chooses the scale")) { eleccion.escalaManual = false }
        FilaRadio(t("Manual"), eleccion.escalaManual, t("Enter the exact scale you want")) { eleccion.escalaManual = true }
    }
    if (eleccion.escalaManual) {
        GrupoMovil {
            FilaPaso(t("Scale"), eleccion.escala, "", ESCALA_MENOR, 0) { valor -> eleccion.escala = valor }
        }
        NotaMovil(
            t(
                "Enter the exact scale you want. It is stress-tested in 100 MHz steps before it stays applied, " +
                    "the way automatic detection tests its own.",
            ),
        )
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}

@Composable
private fun HojaEstado(aplicacion: Aplicacion, datos: JsonObject) {
    val ajuste = datos.objeto("tuning")
    val ultima = datos.objeto("config").entero("cpu_oc_last_applied_frequency")
    val cpu = aplicacion.metricas.objeto("cpu")
    val temperatura = cpu.numero("temperature_c")?.roundToInt()?.toString() ?: "--"
    val frecuencia = cpu.numero("frequency_mhz")?.roundToInt()?.toString() ?: "--"
    TituloHoja(t("Tuning status"))
    GrupoMovil {
        FilaDato(t("Boot persistence"), datos.objeto("persistence").texto("value", "--"))
        FilaDato(t("Last operation"), if (ultima > 0) "$ultima MHz" else t("None"))
        FilaDato(t("Applied tuning"), ajuste.texto("applied_value", "--"))
        FilaDato(t("Detection reference"), ajuste.texto("detection_value", "--"))
        FilaDato(t("Active scale"), ajuste.texto("live_value", "--"))
        FilaDato(t("Live CPU status"), "$temperatura °C · $frecuencia", "MHz")
    }
    CerrarHoja()
}

// -- núcleos -------------------------------------------------------------------------------------------

@Composable
private fun Nucleos(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    val desbloqueo = datos.objeto("unlock")
    val nucleos = desbloqueo.objetos("cores")
    val cpu = aplicacion.metricas.objeto("cpu")
    val carga = desbloqueo.objeto("processor").numero("total_usage_percent")
    FranjaLecturas(
        LecturaFranja(t("Cores"), nucleos.size.toString(), t("of {total}", "total" to NUCLEOS_EN_LA_PLACA.toString())),
        LecturaFranja(t("Load"), carga?.roundToInt()?.toString() ?: "--", "%"),
        LecturaFranja(t("Temperature"), cpu.numero("temperature_c")?.roundToInt()?.toString() ?: "--", "°C"),
    )
    GrupoMovil {
        for (posicion in 0 until NUCLEOS_EN_LA_PLACA) {
            FilaNucleoMovil(posicion, nucleos.firstOrNull { nucleo -> nucleo.entero("index", -1) == posicion })
        }
    }
    GrupoMovil {
        val titulo = t("Unlock cores")
        FilaAbrir(t("Unlock hidden CPU cores"), t("Temporary or at every start"), estadoDesbloqueo(datos, nucleos.size)) {
            movil.abrirDetalle(titulo)
        }
        FilaAbrir(t("Processor"), t("Architecture, cache and instructions")) {
            movil.abrirHoja { HojaProcesador(datos) }
        }
    }
}

private fun estadoDesbloqueo(datos: JsonObject, activos: Int): String {
    val instalado = datos.objeto("unlock_controls").logico("installed")
    return when {
        instalado -> datos.objeto("unlock_controls").texto("status")
        activos >= NUCLEOS_EN_LA_PLACA -> t("Temporary")
        else -> t("Locked")
    }
}

@Composable
fun FilaNucleoMovil(posicion: Int, nucleo: JsonObject?) {
    val paleta = ColoresActuales.current
    val uso = nucleo?.numero("usage_percent")
    Row(
        modifier = Modifier.fillMaxWidth().lineaArriba().heightIn(min = 40.dp).padding(horizontal = 14.dp, vertical = 5.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Texto("N${posicion + 1}", tamano = 13, peso = 700, color = paleta.apagado, modifier = Modifier.width(30.dp))
        val ancho = Modifier.width(76.dp)
        if (nucleo == null) {
            Texto(t("Hidden"), tamano = 12, color = paleta.apagado, alineado = TextAlign.End, lineas = 1, modifier = ancho)
        } else {
            Texto(gigahercios(nucleo.numero("frequency_mhz")), 14, ancho, peso = 700, alineado = TextAlign.End, lineas = 1)
        }
        BarraUso(uso, Modifier.weight(1f), alto = 5.dp)
        val parte = if (nucleo == null) "" else porcentaje(uso)
        Texto(parte, tamano = 13, color = paleta.apagado, alineado = TextAlign.End, modifier = Modifier.width(44.dp))
    }
}

@Composable
private fun HojaProcesador(datos: JsonObject) {
    val procesador = datos.objeto("unlock").objeto("processor")
    TituloHoja(t("Processor"))
    GrupoMovil {
        for ((clave, nombre) in DatosProcesador) {
            val esCarga = clave == "total_usage_percent"
            FilaDato(t(nombre), if (esCarga) porcentaje(procesador.numero(clave)) else procesador.texto(clave, "--"))
        }
    }
    CerrarHoja()
}

// -- desbloqueo de núcleos -------------------------------------------------------------------------------

private fun esPersistente(datos: JsonObject, eleccion: EleccionCpu): Boolean {
    val instalado = datos.objeto("unlock_controls").logico("installed")
    return if (eleccion.modo.isEmpty()) instalado else eleccion.modo == "persistent"
}

private fun sePuedeDesbloquear(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionCpu): Boolean {
    val permiso = if (esPersistente(datos, eleccion)) "persist_allowed" else "temporary_allowed"
    return aplicacion.puedeControlar && aplicacion.trabajo.terminado && datos.objeto("unlock_controls").logico(permiso)
}

private fun mascaraElegida(datos: JsonObject, eleccion: EleccionCpu): Int {
    return if (eleccion.mascara > 0) eleccion.mascara else datos.entero("board_mask", MASCARA_NORMAL)
}

@Composable
private fun BotonDesbloqueo(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionCpu, modifier: Modifier) {
    val persistente = esPersistente(datos, eleccion)
    val permitido = sePuedeDesbloquear(aplicacion, datos, eleccion)
    BotonMovil(accionDesbloqueo(datos, persistente), modifier, ClaseBoton.PELIGRO, permitido) {
        pedirDesbloqueo(aplicacion, datos, persistente, mascaraElegida(datos, eleccion), eleccion.forzar)
    }
}

@Composable
private fun Desbloqueo(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionCpu) {
    val paleta = ColoresActuales.current
    val controles = datos.objeto("unlock_controls")
    val persistente = esPersistente(datos, eleccion)
    val mascara = datos.objetos("masks").firstOrNull { opcion -> opcion.entero("value") == mascaraElegida(datos, eleccion) }
    val nombreMascara = mascara?.texto("short") ?: "0x77"
    val instalado = controles.logico("installed")
    FranjaLecturas(
        LecturaFranja(
            t("Cores"),
            datos.objeto("unlock").objetos("cores").size.toString(),
            t("of {total}", "total" to NUCLEOS_EN_LA_PLACA.toString()),
        ),
        LecturaFranja(t("Mask"), nombreMascara),
        LecturaFranja(t("Persistence"), controles.texto("status"), color = if (instalado) paleta.acento else null, larga = true),
    )
    SeccionMovil(t("Duration")) {
        GrupoMovil {
            FilaRadio(t("Temporary"), !persistente, t("Until the next full power-off. Nothing is installed.")) {
                eleccion.modo = "temporary"
                eleccion.forzar = false
            }
            FilaRadio(
                titulo = t("Persistence"),
                elegida = persistente,
                detalle = t("Applied again by itself on every cold boot, without flashing the BIOS."),
                etiqueta = if (instalado) controles.texto("status") else "",
                activa = controles.logico("offered"),
            ) {
                eleccion.modo = "persistent"
                eleccion.forzar = false
            }
        }
    }
    val nota = controles.texto("note")
    if (nota.isNotEmpty()) {
        NotaMovil(nota, paleta.naranja)
    }
    Comprobacion(aplicacion, datos, eleccion, nombreMascara, mascara?.texto("text") ?: "")
    GrupoMovil {
        FilaAbrir(t("Firmware persistence guide"), t("To keep it in the BIOS")) { aplicacion.abrirEnlace(datos.texto("firmware_guide")) }
        if (instalado) {
            val puedeQuitar = aplicacion.puedeControlar && aplicacion.trabajo.terminado && controles.logico("remove_allowed")
            FilaAbrir(
                t("Remove persistence"),
                t("Back to 6 cores after a full power-off"),
                colorTitulo = paleta.rojo,
                activa = puedeQuitar,
            ) {
                quitarDesbloqueo(aplicacion)
            }
        }
    }
    val ayuda = controles.texto("hint")
    if (ayuda.isNotEmpty()) {
        NotaMovil(ayuda)
    }
    NotaMovil(t("Experimental. The selected GPU governor is stopped before the restart."))
}

@Composable
private fun Comprobacion(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionCpu, nombre: String, detalle: String) {
    val movil = movil()
    val paleta = ColoresActuales.current
    val permitido = sePuedeDesbloquear(aplicacion, datos, eleccion)
    SeccionMovil(t("Check")) {
        GrupoMovil {
            FilaAbrir(
                titulo = t("Core mask of this board"),
                detalle = if (eleccion.forzar) t("Not checked") else detalle,
                valor = if (eleccion.forzar) "—" else nombre,
                activa = permitido && !eleccion.forzar,
            ) {
                movil.abrirHoja { HojaMascara(datos, eleccion) }
            }
            FilaInterruptor(
                titulo = t("Force a non-standard core mask (-f)"),
                encendido = eleccion.forzar,
                detalle = t("Enables all 8 cores without checking the mask"),
                activa = permitido,
                deRiesgo = true,
            ) { valor ->
                eleccion.forzar = valor
            }
        }
        if (eleccion.forzar) {
            NotaMovil(
                t(
                    "The core mask check is skipped (-f). If this board's mask is not 0x77, the " +
                        "factory probably disabled cores that were defective, and they are enabled " +
                        "anyway. Stress test for a few hours and check dmesg for MCE errors before " +
                        "relying on them.",
                ),
                paleta.naranja,
            )
        }
    }
}

@Composable
private fun HojaMascara(datos: JsonObject, eleccion: EleccionCpu) {
    TituloHoja(t("Core mask of this board"))
    TextoHoja(
        t(
            "Pick the mask the unlock tool reported for this board. It goes ahead only " +
                "when the board really reads that mask.",
        ),
    )
    GrupoMovil {
        for (opcion in datos.objetos("masks")) {
            val valor = opcion.entero("value")
            FilaRadio(opcion.texto("text"), valor == mascaraElegida(datos, eleccion)) { eleccion.mascara = valor }
        }
    }
    CerrarHoja(t("Done"), ClaseBoton.PRINCIPAL)
}
