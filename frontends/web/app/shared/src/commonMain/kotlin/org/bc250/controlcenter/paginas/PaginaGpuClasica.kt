package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.DosColumnas
import org.bc250.controlcenter.componentes.Icono
import org.bc250.controlcenter.componentes.Leyenda
import org.bc250.controlcenter.componentes.RejillaGpuCu
import org.bc250.controlcenter.componentes.SubPanel
import org.bc250.controlcenter.componentes.TarjetaPagina
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.gamepad_menu
import org.bc250.controlcenter.recursos.warning_orange
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import kotlin.math.abs

private val MargenClasico = PaddingValues(14.dp, 12.dp)
private val AnchoDosColumnas = 1180.dp

/** Lo que la pantalla clásica le pide a la página. */
internal class AccionesGpuClasica(
    val elegirRango: (Int, Int) -> Unit,
    val editarPerfil: (JsonObject) -> Unit,
    val guardarArranque: () -> Unit,
    val aplicar: () -> Unit,
    val abrirLaboratorio: () -> Unit,
    val abrirConfiguracion: () -> Unit,
)

/** El diseño antiguo: los controles a la izquierda, las lecturas y el servicio a la derecha. */
@Composable
internal fun GpuClasica(
    aplicacion: Aplicacion,
    datos: JsonObject,
    libre: Boolean,
    minimo: Int,
    maximo: Int,
    acciones: AccionesGpuClasica,
) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= AnchoDosColumnas) {
            DosColumnas(
                parteInicial = 0.6f,
                alto = 710.dp,
                izquierda = { modificador -> TarjetaControles(aplicacion, datos, libre, minimo, maximo, acciones, modificador) },
                derecha = { modificador -> TarjetaLecturas(aplicacion, datos, libre, maximo, acciones, modificador) },
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                TarjetaControles(aplicacion, datos, libre, minimo, maximo, acciones, Modifier.fillMaxWidth())
                TarjetaLecturas(aplicacion, datos, libre, maximo, acciones, Modifier.fillMaxWidth())
            }
        }
    }
}

// -- izquierda ------------------------------------------------------------------------------------------

@Composable
private fun TarjetaControles(
    aplicacion: Aplicacion,
    datos: JsonObject,
    libre: Boolean,
    minimo: Int,
    maximo: Int,
    acciones: AccionesGpuClasica,
    modifier: Modifier,
) {
    TarjetaPagina(modifier, espacio = 12.dp) {
        PanelPerfiles(aplicacion, datos, libre, minimo, maximo, acciones)
        PanelRango(datos, libre, minimo, maximo, acciones)
        CompatibilidadGpu(aplicacion, datos, libre, clasica = true)
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
            Boton(t("Save for startup"), acciones.guardarArranque, Modifier.weight(1f), activo = libre)
            val techo = datos.entero("ceiling", 2000)
            Boton(
                texto = t("Review and apply range"),
                alPulsar = acciones.aplicar,
                modifier = Modifier.weight(2f),
                clase = ClaseBoton.PRINCIPAL,
                activo = libre && minimo <= maximo && maximo <= techo,
                peso = 780,
            )
        }
    }
}

@Composable
private fun PanelPerfiles(
    aplicacion: Aplicacion,
    datos: JsonObject,
    libre: Boolean,
    minimo: Int,
    maximo: Int,
    acciones: AccionesGpuClasica,
) {
    fun exportar() {
        aplicacion.preguntarYEjecutar("gpu.export_decky", t("Export to Decky"))
    }
    val perfiles = datos.objetos("profiles")
    val techo = datos.entero("ceiling", 2000)
    SubPanel(margen = MargenClasico, espacio = 9.dp) {
        Row(Modifier.fillMaxWidth().height(35.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(t("Operating profile"), 14, Modifier.weight(1f), peso = 780)
            Boton(t("Export to Decky"), ::exportar, activo = libre, alto = 35.dp, tamano = 12, peso = 700, icono = Res.drawable.gamepad_menu)
        }
        Leyenda(t("One click sets the range. The pencil changes name and frequencies."))
        RejillaGpuCu(perfiles.size, 3, separacion = 8.dp) { indice, modificador ->
            val perfil = perfiles[indice]
            val bajo = perfil.entero("min")
            val alto = perfil.entero("max")
            TarjetaPerfilGpu(
                perfil = perfil,
                elegido = minimo == bajo && maximo == alto,
                activo = libre && alto <= techo,
                modifier = modificador,
                alElegir = { acciones.elegirRango(bajo, alto) },
                alEditar = { acciones.editarPerfil(perfil) },
            )
        }
    }
}

@Composable
private fun PanelRango(datos: JsonObject, libre: Boolean, minimo: Int, maximo: Int, acciones: AccionesGpuClasica) {
    val paleta = ColoresActuales.current
    val techo = datos.entero("ceiling", 2000)
    SubPanel(margen = MargenClasico, espacio = 9.dp) {
        Texto(t("Frequency range"), tamano = 14, peso = 780)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Leyenda(t("Fine-tune over the TOML points · current ceiling {ceiling} MHz.", "ceiling" to techo.toString()), Modifier.weight(1f))
            if (!datos.objeto("high_frequency_points").logico("enabled")) {
                val aviso = t("{minimum}–{maximum} MHz COMMENTED IN THE TOML", "minimum" to "2050", "maximum" to "2400")
                Texto(aviso, tamano = 11, peso = 800, color = paleta.rojo)
            }
        }
        CarrilGpu(datos.objetos("rail"), minimo, maximo, techo, libre, acciones.elegirRango)
        RejillaGpuCu(2, 2, separacion = 12.dp) { indice, modificador ->
            if (indice == 0) {
                CampoRango(t("Minimum frequency"), t("Governor floor applied through the validated D-Bus interface."), minimo, false, modificador)
            } else {
                val nota = t("Current ceiling {ceiling} MHz per config.toml.", "ceiling" to techo.toString())
                CampoRango(t("Maximum frequency"), nota, maximo, true, modificador)
            }
        }
    }
}

@Composable
private fun CampoRango(nombre: String, nota: String, valor: Int, destacado: Boolean, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val borde = if (destacado) paleta.acentoBorde else paleta.borde
    val color = if (destacado) paleta.acento else paleta.texto
    Row(modifier.height(36.dp), Arrangement.spacedBy(9.dp), Alignment.CenterVertically) {
        Column(Modifier.weight(1f), Arrangement.spacedBy(2.dp)) {
            Texto(nombre, tamano = 13, peso = 700)
            Leyenda(nota)
        }
        Box(Modifier.width(84.dp).fillMaxHeight().marco(paleta.ventana, borde, 4.dp).padding(end = 15.dp), Alignment.CenterEnd) {
            Texto(valor.toString(), tamano = 14, peso = 800, color = color)
        }
        Texto("MHz", tamano = 12, peso = 750, color = paleta.apagado)
    }
}

// -- derecha ---------------------------------------------------------------------------------------------

@Composable
private fun TarjetaLecturas(
    aplicacion: Aplicacion,
    datos: JsonObject,
    libre: Boolean,
    maximo: Int,
    acciones: AccionesGpuClasica,
    modifier: Modifier,
) {
    val lecturas = datos.objetos("tiles")
    TarjetaPagina(modifier, espacio = 12.dp) {
        RejillaGpuCu(lecturas.size, 3, umbral = 420.dp, separacion = 10.dp) { indice, modificador ->
            FichaLectura(lecturas[indice], modificador)
        }
        Leyenda(t("Passive readings · hardware changes require confirmation."))
        PanelServicio(aplicacion, datos, libre)
        PanelLaboratorio(datos, maximo, acciones)
        PanelRiesgo(aplicacion, datos, libre)
    }
}

@Composable
private fun FichaLectura(lectura: JsonObject, modifier: Modifier) {
    val paleta = ColoresActuales.current
    Column(
        modifier.height(77.dp).marco(paleta.panelAlterno, paleta.borde, Medidas.radioPanel).padding(horizontal = 12.dp, vertical = 10.dp),
        Arrangement.spacedBy(1.dp),
    ) {
        Texto(lectura.texto("label"), tamano = 11, peso = 700, color = paleta.apagado, lineas = 1)
        Texto(lectura.texto("value"), tamano = 19, peso = 830, lineas = 1)
        Texto(lectura.texto("detail"), tamano = 10, color = paleta.sutil, lineas = 1)
    }
}

@Composable
private fun PanelServicio(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean) {
    SubPanel(margen = MargenClasico, espacio = 9.dp) {
        Texto(t("Governor service"), tamano = 14, peso = 780)
        Leyenda(t("Start governor runs it now and saves it for startup (enables the service). Stop governor stops it and removes it from startup (disables the service)."))
        val funcionando = datos.texto("service_active") == "active"
        RejillaAccionesServicioGpu(aplicacion, datos, funcionando, libre, alto = 38.dp, tamano = 13)
    }
}

@Composable
private fun PanelLaboratorio(datos: JsonObject, maximo: Int, acciones: AccionesGpuClasica) {
    SubPanel(margen = MargenClasico, espacio = 9.dp) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Texto(t("Voltage laboratory"), 14, Modifier.weight(1f), peso = 780)
            Texto("$maximo MHz · ${voltajeDe(datos, maximo)} mV", tamano = 16, peso = 820)
        }
        Leyenda(t("Point-by-point conservative validation of the selected range."))
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
            Boton(t("Open laboratory"), acciones.abrirLaboratorio, Modifier.weight(1f), clase = ClaseBoton.PRINCIPAL)
            Boton(t("Open config.toml"), acciones.abrirConfiguracion, Modifier.weight(1f))
        }
    }
}

private fun voltajeDe(datos: JsonObject, frecuencia: Int): Int {
    val cercano = datos.objetos("rail").minByOrNull { punto -> abs(punto.entero("frequency") - frecuencia) }
    return cercano?.entero("voltage") ?: 0
}

@Composable
private fun PanelRiesgo(aplicacion: Aplicacion, datos: JsonObject, libre: Boolean) {
    val paleta = ColoresActuales.current
    val habilitados = datos.objeto("high_frequency_points").logico("enabled")
    val titulo = t(if (habilitados) "Re-comment the +2000 MHz points" else "Uncomment +2000 MHz points")
    fun cambiar() {
        val parametros = mapOf("enable" to JsonPrimitive(!habilitados))
        aplicacion.preguntarYEjecutar("gpu.high_points", titulo, titulo, parametros, peligro = true)
    }
    SubPanel(Modifier.padding(top = 10.dp), borde = paleta.bordeRiesgo, margen = MargenClasico, espacio = 9.dp) {
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(7.dp), Alignment.CenterVertically) {
            Icono(Res.drawable.warning_orange, 14.dp)
            Texto(t("DANGER ZONE"), 11, Modifier.weight(1f), peso = 800, color = paleta.rojo)
            Texto(t(if (habilitados) "Enabled" else "Locked"), 10, color = paleta.sutil, alineado = TextAlign.End)
        }
        Texto(t("TOML points above 2000 MHz"), tamano = 15, peso = 800)
        Leyenda(
            t(
                "Uncomment the {extra_low}–{extra_high} MHz safe-points in config.toml (up to {voltage} mV). It can hang the board or corrupt the SMU state.",
                "extra_low" to "2050", "extra_high" to "2400", "voltage" to "1150",
            ),
        )
        Boton(titulo, ::cambiar, Modifier.fillMaxWidth(), clase = ClaseBoton.PELIGRO, activo = libre, alto = 36.dp, peso = 760)
    }
}
