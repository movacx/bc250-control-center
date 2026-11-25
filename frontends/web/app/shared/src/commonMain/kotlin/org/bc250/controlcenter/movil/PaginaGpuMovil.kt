package org.bc250.controlcenter.movil

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.paginas.AjusteCyan
import org.bc250.controlcenter.paginas.aplicarCompatibilidad
import org.bc250.controlcenter.paginas.avisoDosGobernadores
import org.bc250.controlcenter.paginas.avisoProcess
import org.bc250.controlcenter.paginas.avisoSinRespuesta
import org.bc250.controlcenter.paginas.cambiarGobernador
import org.bc250.controlcenter.paginas.guardarArranqueGpu
import org.bc250.controlcenter.paginas.leerAjusteCyan
import org.bc250.controlcenter.paginas.perfilGpuOriginal
import org.bc250.controlcenter.paginas.pedirServicioGpu
import org.bc250.controlcenter.paginas.revisarRangoGpu
import org.bc250.controlcenter.tema.ColoresActuales

private const val FRECUENCIAS = 0
private const val GOBERNADOR_CYAN = "cyan-skillfish-governor-smu"
private const val GOBERNADOR_OBERON = "oberon-governor"

/** El rango elegido; mientras no se toque, sigue al que está en marcha. */
private class EleccionGpu {
    var minimo by mutableStateOf(500)
    var maximo by mutableStateOf(1500)
    var editado by mutableStateOf(false)

    fun elegir(bajo: Int, alto: Int) {
        minimo = bajo
        maximo = alto
        editado = true
    }
}

fun esOberon(datos: JsonObject): Boolean {
    return datos.texto("governor_backend") == GOBERNADOR_OBERON
}

/** Si ahora se puede operar con el gobernador. */
fun gpuLibre(aplicacion: Aplicacion, datos: JsonObject): Boolean {
    val legible = datos.isNotEmpty() && datos.texto("error").isEmpty() && !datos.logico("empty")
    return aplicacion.puedeControlar && aplicacion.trabajo.terminado && legible
}

@Composable
fun PaginaGpuMovil(aplicacion: Aplicacion) {
    val tareas = rememberCoroutineScope()
    val movil = movil()
    val eleccion = remember { EleccionGpu() }
    val voltaje = remember { EleccionVoltaje() }
    val datos = aplicacion.lectura("gpu")
    var trabajoAnterior by remember { mutableStateOf(aplicacion.trabajo.id) }
    LaunchedEffect(aplicacion) {
        while (true) {
            aplicacion.leerPagina("gpu")
            aplicacion.pausar(3000)
        }
    }
    LaunchedEffect(aplicacion.trabajo.id, aplicacion.trabajo.terminado) {
        if (aplicacion.trabajo.id != trabajoAnterior && aplicacion.trabajo.terminado) {
            eleccion.editado = false
            voltaje.descartar()
            trabajoAnterior = aplicacion.trabajo.id
        }
    }
    LaunchedEffect(datos.entero("current_min"), datos.entero("current_max"), eleccion.editado) {
        if (!eleccion.editado) {
            eleccion.minimo = datos.entero("current_min", 500)
            eleccion.maximo = datos.entero("current_max", 1500)
        }
    }
    LeerVoltajes(aplicacion, datos, voltaje)
    val libre = gpuLibre(aplicacion, datos)
    val enFrecuencias = movil.pestana("gpu") == FRECUENCIAS
    val dentroDelTecho = esOberon(datos) || eleccion.maximo <= datos.entero("ceiling", 2000)
    PaginaMovil(
        clave = "gpu",
        pestanas = listOf(t("Frequencies"), t("Voltage")),
        pie = when {
            enFrecuencias -> {
                {
                    val puede = libre && datos.objeto("availability").logico("range") && dentroDelTecho
                    BotonMovil(t("Apply profile"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, puede) {
                        tareas.launch { revisarRangoGpu(aplicacion, eleccion.minimo, eleccion.maximo) }
                    }
                }
            }
            esOberon(datos) -> null
            else -> {
                {
                    BotonMovil(t("Discard"), Modifier.weight(1f), activo = voltaje.cambiado) { voltaje.descartar() }
                    BotonMovil(t("Review and apply"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && voltaje.sePuedeAplicar) {
                        tareas.launch { voltaje.aplicar(aplicacion) }
                    }
                }
            }
        },
    ) {
        EstadoLecturaMovil(datos)
        if (datos.logico("empty")) {
            NotaMovil(t("Not detected"))
        }
        if (enFrecuencias) {
            FrecuenciasGpu(aplicacion, datos, eleccion, libre)
        } else {
            VoltajeGpu(aplicacion, datos, voltaje, libre)
        }
    }
}

// -- perfiles ------------------------------------------------------------------------------------------

@Composable
private fun FrecuenciasGpu(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionGpu, libre: Boolean) {
    val movil = movil()
    val oberon = esOberon(datos)
    val techo = datos.entero("ceiling", 2000)
    if (!datos.logico("dbus_responsive", true)) {
        NotaMovil(avisoSinRespuesta(datos), ColoresActuales.current.naranja, tamano = 13)
    }
    SeccionMovil(t("Operating profile")) {
        for (perfil in datos.objetos("profiles")) {
            val bajo = perfil.entero("min")
            val alto = perfil.entero("max")
            TarjetaPerfilMovil(
                nombre = t(perfil.texto("name")),
                valor = "$bajo – $alto MHz",
                detalle = perfil.texto("voltage"),
                elegido = eleccion.minimo == bajo && eleccion.maximo == alto,
                activo = libre && (oberon || alto <= techo),
                alEditar = if (oberon) null else { { movil.abrirHoja { EditorPerfilGpuMovil(aplicacion, perfil) } } },
            ) {
                eleccion.elegir(bajo, alto)
            }
        }
        val razon = datos.objeto("high_frequency_points").texto("ceiling_reason")
        if (!oberon && razon.isNotEmpty()) {
            NotaMovil(razon, ColoresActuales.current.naranja)
        }
    }
    Gobernador(aplicacion, datos, libre)
    if (!oberon) {
        GrupoMovil {
            val ajuste = leerAjusteCyan(datos)
            FilaAbrir(t("Cyan compatibility"), valor = nombreDeAjuste(ajuste), activa = datos.isNotEmpty()) {
                movil.abrirHoja { HojaCompatibilidad(aplicacion, datos, ajuste) }
            }
            FilaAbrir(t("Export to Decky"), activa = libre) {
                aplicacion.preguntarYEjecutar("gpu.export_decky", t("Export to Decky"))
            }
        }
    }
}

@Composable
private fun EditorPerfilGpuMovil(aplicacion: Aplicacion, perfil: JsonObject) {
    val movil = movil()
    var nombre by remember { mutableStateOf(t(perfil.texto("name"))) }
    var minimo by remember { mutableStateOf(perfil.entero("min").toString()) }
    var maximo by remember { mutableStateOf(perfil.entero("max").toString()) }
    val bajo = minimo.toIntOrNull()
    val alto = maximo.toIntOrNull()
    val valido = bajo != null && alto != null && bajo in 500..alto && alto <= 2400
    TituloHoja(t("Edit profile"), t("Reset")) {
        val original = perfilGpuOriginal(perfil.texto("key"))
        nombre = t(original.nombre)
        minimo = original.minimo.toString()
        maximo = original.maximo.toString()
    }
    CampoConNombreMovil(t("Name"), nombre) { nuevo -> nombre = nuevo.take(28) }
    CampoConNombreMovil(t("Min. MHz"), minimo, numerico = true) { nuevo -> minimo = nuevo }
    CampoConNombreMovil(t("Max. MHz"), maximo, numerico = true) { nuevo -> maximo = nuevo }
    if (!valido) {
        val aviso = t("Enter a value between {minimum} and {maximum} MHz.", "minimum" to "500", "maximum" to "2400")
        NotaMovil(aviso, ColoresActuales.current.rojo)
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { movil.cerrarHoja() }
        BotonMovil(t("Save profile"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, valido && nombre.isNotBlank() && aplicacion.puedeControlar) {
            val parametros = mapOf(
                "key" to JsonPrimitive(perfil.texto("key")),
                "name" to JsonPrimitive(nombre),
                "min" to JsonPrimitive(bajo),
                "max" to JsonPrimitive(alto),
            )
            aplicacion.guardar("gpu.profile", parametros, "gpu")
            movil.cerrarHoja()
        }
    }
}

// -- gobernador ----------------------------------------------------------------------------------------

@Composable
private fun Gobernador(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean) {
    val movil = movil()
    val funcionando = datos.texto("service_active") == "active"
    val disponible = datos.objeto("availability")
    SeccionMovil(t("Governor")) {
        GrupoMovil {
            FilaLibre(altoMinimo = 66.dp) {
                val estado = if (funcionando) "Running" else "Stopped"
                TextosFila(if (esOberon(datos)) "Oberon" else "Cyan Skillfish", t(estado))
                val puede = libre && disponible.logico(if (funcionando) "stop" else "start")
                InterruptorMovil(funcionando, activo = puede) {
                    pedirServicioGpu(aplicacion, datos, if (funcionando) "desactivar" else "activar")
                }
            }
            TiraAcciones(
                AccionTira(t("Restart"), libre && disponible.logico("restart")) { pedirServicioGpu(aplicacion, datos, "reiniciar") },
                AccionTira(t("View status")) { aplicacion.ejecutar("gpu.status", t("View status")) },
                AccionTira(t("Change")) { movil.abrirHoja { HojaGobernador(aplicacion, datos) } },
            )
            if (!esOberon(datos)) {
                val rango = "${datos.entero("current_min")} – ${datos.entero("current_max")}"
                FilaAbrir(t("At startup"), t("Tap to keep the active range"), rango, "MHz", activa = libre && disponible.logico("save_boot")) {
                    guardarArranqueGpu(aplicacion, datos)
                }
            }
        }
    }
}

@Composable
private fun HojaGobernador(aplicacion: Aplicacion, datos: JsonObject) {
    val movil = movil()
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val actual = if (esOberon(datos)) GOBERNADOR_OBERON else GOBERNADOR_CYAN
    fun elegir(nuevo: String) {
        movil.cerrarHoja()
        if (nuevo != actual) {
            cambiarGobernador(aplicacion, nuevo)
        }
    }
    TituloHoja(t("Change governor"))
    GrupoMovil {
        FilaRadio("Cyan Skillfish", actual == GOBERNADOR_CYAN, t("Editable profiles and voltage curve"), activa = libre) { elegir(GOBERNADOR_CYAN) }
        FilaRadio("Oberon", actual == GOBERNADOR_OBERON, t("Three fixed profiles at 1000 mV"), activa = libre) { elegir(GOBERNADOR_OBERON) }
    }
    NotaMovil(avisoDosGobernadores())
    CerrarHoja()
}

// -- compatibilidad de Cyan ------------------------------------------------------------------------------

private val AjusteNormal = AjusteCyan("smu", "busy-flag", "drm", metricas = true, frecuencias = false)
private val AjusteKernel = AjusteCyan("kernel", "kernel", "sysfs", metricas = false, frecuencias = false)

private fun nombreDeAjuste(ajuste: AjusteCyan): String {
    return when (ajuste) {
        AjusteNormal -> t("Standard")
        AjusteKernel -> t("BC-250 kernel")
        else -> t("Custom")
    }
}

@Composable
private fun HojaCompatibilidad(aplicacion: Aplicacion, datos: JsonObject, inicial: AjusteCyan) {
    val movil = movil()
    val libre = gpuLibre(aplicacion, datos)
    var ajuste by remember { mutableStateOf(inicial) }
    var propio by remember { mutableStateOf(inicial != AjusteNormal && inicial != AjusteKernel) }
    TituloHoja(t("Cyan compatibility"))
    GrupoMovil {
        FilaRadio(t("Standard"), !propio && ajuste == AjusteNormal, t("For the normal kernel of your distribution"), activa = libre) {
            ajuste = AjusteNormal
            propio = false
        }
        FilaRadio(t("BC-250 kernel"), !propio && ajuste == AjusteKernel, t("For a kernel with the board patches"), activa = libre) {
            ajuste = AjusteKernel
            propio = false
        }
        FilaRadio(t("Custom"), propio, t("Choose each reading separately"), activa = libre) { propio = true }
    }
    if (propio) {
        val conTemperatura = datos.objeto("cyan_telemetry").logico("temp_read_supported", true)
        ElegirLectura(t("Governor method"), listOf("smu", "kernel"), ajuste.metodo, libre) { ajuste = ajuste.copy(metodo = it) }
        ElegirLectura(t("Usage reading"), listOf("busy-flag", "process", "kernel"), ajuste.uso, libre) { ajuste = ajuste.copy(uso = it) }
        if (ajuste.uso == "process") {
            NotaMovil(avisoProcess(), ColoresActuales.current.naranja)
        }
        ElegirLectura(t("Temperature reading"), listOf("drm", "sysfs"), ajuste.temperatura, libre && conTemperatura) {
            ajuste = ajuste.copy(temperatura = it)
        }
        GrupoMovil {
            val nombres = datos.objeto("fix_labels")
            FilaInterruptor(nombres.texto("metrics"), ajuste.metricas, activa = libre) { ajuste = ajuste.copy(metricas = it) }
            FilaInterruptor(nombres.texto("frequency"), ajuste.frecuencias, activa = libre) { ajuste = ajuste.copy(frecuencias = it) }
        }
    }
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { movil.cerrarHoja() }
        BotonMovil(t("Apply"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && ajuste != inicial) {
            movil.cerrarHoja()
            aplicarCompatibilidad(aplicacion, ajuste)
        }
    }
}

@Composable
private fun ElegirLectura(nombre: String, opciones: List<String>, elegida: String, activa: Boolean, alElegir: (String) -> Unit) {
    val nombres = opciones.map { opcion -> opcion to (if (opcion == "smu" || opcion == "drm") opcion.uppercase() else opcion) }
    TextoHoja(nombre)
    SegmentadoMovil(nombres, elegida, activa, alElegir)
}
