package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Desplegable
import org.bc250.controlcenter.componentes.Eleccion
import org.bc250.controlcenter.componentes.Leyenda
import org.bc250.controlcenter.componentes.Esperando
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Opcion
import org.bc250.controlcenter.componentes.PaginaDesplazable
import org.bc250.controlcenter.componentes.TarjetaPagina
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ImagenLogo
import org.bc250.controlcenter.datos.elegirImagen
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.puedeElegirImagen
import org.bc250.controlcenter.datos.reescalarImagen
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.fw_logo
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.jetbrains.compose.resources.decodeToImageBitmap
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

private const val TAMANO_MENOR = 30
private const val TAMANO_MAYOR = 100
private const val MAX_NUCLEOS = 8

/** Lo que la persona ha elegido para su memoria USB. */
private class EleccionFirmware {
    var familia by mutableStateOf("")
    var imagen by mutableStateOf("")
    var unidad by mutableStateOf("")
    var logo by mutableStateOf<ImagenLogo?>(null)
    var tamano by mutableIntStateOf(TAMANO_MAYOR)
}

/** Firmware: elegir la BIOS y preparar la memoria USB que la lleva. Nunca graba la BIOS. */
@Composable
fun PaginaFirmware(aplicacion: Aplicacion) {
    val eleccion = remember { EleccionFirmware() }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("firmware")
            delay(3000)
        }
    }
    val datos = aplicacion.lectura("firmware")
    val porDefecto = datos.texto("default_family")
    LaunchedEffect(porDefecto) {
        if (eleccion.familia.isEmpty()) {
            eleccion.familia = porDefecto
        }
    }
    PaginaDesplazable(PaddingValues(start = 16.dp, top = 12.dp, end = 16.dp, bottom = 20.dp)) {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth >= 1000.dp) {
                Row(Modifier.fillMaxWidth().height(832.dp), Arrangement.spacedBy(12.dp)) {
                    TarjetaCatalogo(aplicacion, datos, eleccion, Modifier.weight(889f).height(832.dp), conDesplazador = true)
                    TarjetaPreparacion(aplicacion, datos, eleccion, Modifier.weight(727f).height(832.dp))
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    TarjetaCatalogo(aplicacion, datos, eleccion, Modifier.fillMaxWidth(), conDesplazador = false)
                    TarjetaPreparacion(aplicacion, datos, eleccion, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@Composable
private fun Rotulo(texto: String, tamano: Int = 10, modifier: Modifier = Modifier) {
    Texto(texto.uppercase(), tamano, modifier, peso = 800, color = ColoresActuales.current.apagado)
}

// -- catálogo -------------------------------------------------------------------------------------------

@Composable
private fun TarjetaCatalogo(
    aplicacion: Aplicacion,
    datos: JsonObject,
    eleccion: EleccionFirmware,
    modifier: Modifier,
    conDesplazador: Boolean,
) {
    TarjetaPagina(modifier, espacio = 6.dp) {
        Rotulo(t("Firmware"))
        Leyenda(t("Every file comes from the project that publishes it and is checked against its SHA-256 before it reaches the USB."))
        val error = datos.texto("error")
        if (error.isNotEmpty()) {
            Texto(error, tamano = 12, color = ColoresActuales.current.naranja)
        }
        val lista = if (conDesplazador) Modifier.weight(1f).verticalScroll(rememberScrollState()) else Modifier
        Column(lista.fillMaxWidth().padding(end = 18.dp, top = 2.dp), Arrangement.spacedBy(8.dp)) {
            val familias = datos.objetos("families")
            val modificadas = familias.filter { familia -> familia.texto("origin") != "stock" }
            val originales = familias.filter { familia -> familia.texto("origin") == "stock" }
            GrupoFirmware(t("Modded BIOS"), modificadas, eleccion)
            GrupoFirmware(t("Stock BIOS (ASRock)"), originales, eleccion)
        }
    }
}

@Composable
private fun GrupoFirmware(titulo: String, familias: List<JsonObject>, eleccion: EleccionFirmware) {
    if (familias.isEmpty()) {
        return
    }
    Rotulo(titulo, tamano = 11, modifier = Modifier.padding(start = 3.dp, top = 4.dp))
    for (familia in familias) {
        TarjetaFamilia(familia, familia.texto("key") == eleccion.familia) {
            eleccion.familia = familia.texto("key")
            eleccion.imagen = ""
        }
    }
    Spacer(Modifier.height(4.dp))
}

@Composable
private fun TarjetaFamilia(familia: JsonObject, elegida: Boolean, alElegir: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (elegida) paleta.elegido else paleta.panelAlterno
    val borde = if (elegida) paleta.acentoBorde else paleta.borde
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .marco(fondo, borde, Medidas.radioPanel)
            .pulsable(alPulsar = alElegir)
            .padding(horizontal = 15.dp, vertical = 13.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(Modifier.fillMaxWidth()) {
            Texto(familia.texto("title"), 14, Modifier.weight(1f), peso = 780)
            Leyenda(familia.texto("download"))
        }
        Texto(familia.texto("summary"), tamano = 11, color = paleta.apagado)
        VentajasFirmware(familia.textos("highlights"))
        HechosFirmware(familia)
        if (familia.texto("caution").isNotEmpty() && elegida) {
            Texto(familia.texto("caution"), tamano = 12, color = paleta.naranja)
        }
    }
}

@Composable
private fun VentajasFirmware(ventajas: List<String>) {
    val paleta = ColoresActuales.current
    Column(Modifier.padding(vertical = 2.dp), Arrangement.spacedBy(3.dp)) {
        for (pareja in ventajas.chunked(2)) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp)) {
                for (ventaja in pareja) {
                    Row(Modifier.weight(1f), Arrangement.spacedBy(7.dp)) {
                        Texto("•", tamano = 12, peso = 800, color = paleta.acento)
                        Texto(ventaja, tamano = 12)
                    }
                }
                if (pareja.size == 1) {
                    Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun HechosFirmware(familia: JsonObject) {
    val paleta = ColoresActuales.current
    val menu = familia.logico("vram_menu")
    val nucleos = familia.entero("cores")
    val logos = familia.entero("boot_logos")
    Row(Modifier.fillMaxWidth().padding(top = 4.dp), Arrangement.spacedBy(18.dp)) {
        HechoFirmware(t("VRAM in the BIOS"), t(if (menu) "Yes" else "No"), menu, Modifier.weight(1f))
        val textoNucleos = t("{active} of {total}", "active" to nucleos.toString(), "total" to MAX_NUCLEOS.toString())
        HechoFirmware(t("CPU cores"), textoNucleos, nucleos == MAX_NUCLEOS, Modifier.weight(1f))
        val textoLogos = if (logos > 0) t("{count} to choose from", "count" to logos.toString()) else t("As shipped")
        HechoFirmware(t("Boot logo"), textoLogos, logos > 0, Modifier.weight(1f))
        HechoFirmware(t("After flashing"), t("Clear CMOS"), true, Modifier.weight(1f), paleta.naranja)
    }
}

@Composable
private fun HechoFirmware(nombre: String, valor: String, destacado: Boolean, modifier: Modifier, color: Color? = null) {
    val paleta = ColoresActuales.current
    val colorValor = color ?: if (destacado) paleta.texto else paleta.apagado
    Column(modifier, Arrangement.spacedBy(8.dp)) {
        Rotulo(nombre)
        Texto(valor, tamano = 13, peso = if (destacado) 720 else 600, color = colorValor)
    }
}

// -- preparación ------------------------------------------------------------------------------------------

@Composable
private fun TarjetaPreparacion(aplicacion: Aplicacion, datos: JsonObject, eleccion: EleccionFirmware, modifier: Modifier) {
    val familia = datos.objetos("families").firstOrNull { item -> item.texto("key") == eleccion.familia }
    TarjetaPagina(modifier, espacio = 8.dp) {
        SeccionLogo(aplicacion, familia, eleccion)
        LineaDivisoria(Modifier.padding(top = 34.dp, bottom = 34.dp))
        SeccionInstalada(datos)
        Spacer(Modifier.height(30.dp))
        SeccionUnidades(datos, eleccion)
        Spacer(Modifier.height(30.dp))
        SeccionResumen(aplicacion, datos, familia, eleccion)
    }
}

@Composable
private fun SeccionLogo(aplicacion: Aplicacion, familia: JsonObject?, eleccion: EleccionFirmware) {
    val admite = familia != null && familia.logico("logo_replaceable")
    Rotulo(t("Custom boot logo"))
    Leyenda(t("Put your own picture on the screen the board shows while it starts. It goes into the chosen firmware when the USB is prepared, and nothing else in that firmware changes."))
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth >= 560.dp) {
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), Arrangement.spacedBy(20.dp)) {
                VistaLogo(eleccion.logo, Modifier.width(365.dp))
                DatosLogo(aplicacion, admite, eleccion, Modifier.weight(1f))
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                VistaLogo(eleccion.logo, Modifier.fillMaxWidth())
                DatosLogo(aplicacion, admite, eleccion, Modifier.fillMaxWidth())
            }
        }
    }
    Leyenda(t("Before the USB is written, the new firmware is read back and compared with the published one: only the logo may differ. Custom logos have been tested on real boards with P2.00, P3.00, P5.00 and MeiMeiDXE v3. As with any BIOS change, an SPI programmer at hand is the way back."))
}

@OptIn(ExperimentalEncodingApi::class)
@Composable
private fun VistaLogo(logo: ImagenLogo?, modifier: Modifier) {
    val paleta = ColoresActuales.current
    Box(modifier.aspectRatio(672f / 378f).background(Color.Black, RoundedCornerShape(5.dp)), Alignment.Center) {
        if (logo == null) {
            Texto(t("Your picture shows here"), tamano = 13, color = paleta.sutil)
        } else {
            val dibujo = remember(logo.jpegBase64) { Base64.decode(logo.jpegBase64).decodeToImageBitmap() }
            Image(dibujo, contentDescription = logo.nombre, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun DatosLogo(aplicacion: Aplicacion, admite: Boolean, eleccion: EleccionFirmware, modifier: Modifier) {
    val tareas = rememberCoroutineScope()
    val logo = eleccion.logo

    fun guardar(imagen: ImagenLogo?) {
        eleccion.logo = imagen
        val datos = imagen?.jpegBase64 ?: ""
        tareas.launch {
            val guardado = aplicacion.guardarAhora("firmware.logo", JsonObject(mapOf("logo" to JsonPrimitive(datos))))
            if (!guardado) {
                eleccion.logo = null
            }
        }
    }

    fun elegir() {
        eleccion.tamano = TAMANO_MAYOR
        elegirImagen(::guardar)
    }

    fun cambiarTamano(porcentaje: Int) {
        eleccion.tamano = porcentaje
        reescalarImagen(porcentaje, ::guardar)
    }

    Column(modifier) {
        Rotulo(t("Picture"))
        HechoFila(t("File name"), logo?.nombre ?: "--")
        LineaDivisoria()
        HechoFila(t("Original size"), if (logo == null) "--" else "${logo.ancho} × ${logo.alto} px")
        LineaDivisoria()
        val kilobytes = (logo?.jpegBase64?.length ?: 0) * 3 / 4 / 1024
        HechoFila(t("In the firmware"), if (logo == null) "--" else "672 × 378 px · JPEG · $kilobytes KB")
        Row(Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 8.dp), Arrangement.spacedBy(12.dp), Alignment.CenterVertically) {
            Texto(t("Size"), tamano = 11, peso = 760)
            Deslizador(eleccion.tamano, logo != null, Modifier.weight(1f), ::cambiarTamano)
            Texto("${eleccion.tamano} %", 10, Modifier.width(44.dp), color = ColoresActuales.current.sutil, alineado = TextAlign.End)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val puede = admite && puedeElegirImagen && aplicacion.puedeControlar
            Boton(t("Choose picture…"), ::elegir, activo = puede, icono = Res.drawable.fw_logo)
            Boton(t("Remove"), { guardar(null) }, activo = logo != null)
        }
    }
}

@Composable
private fun HechoFila(nombre: String, valor: String) {
    Row(Modifier.fillMaxWidth().height(34.dp), Arrangement.spacedBy(12.dp), Alignment.CenterVertically) {
        Texto(nombre, tamano = 12, peso = 500, color = ColoresActuales.current.apagado)
        Texto(valor, 14, Modifier.weight(1f), peso = 700, alineado = TextAlign.End, lineas = 1)
    }
}

/** Un deslizador de 30 a 100. */
@Composable
private fun Deslizador(valor: Int, activo: Boolean, modifier: Modifier, alCambiar: (Int) -> Unit) {
    val paleta = ColoresActuales.current
    val color = if (activo) paleta.acento else paleta.borde
    BoxWithConstraints(modifier.height(18.dp)) {
        val ancho = maxWidth
        val parte = (valor - TAMANO_MENOR).toFloat() / (TAMANO_MAYOR - TAMANO_MENOR)
        fun mover(x: Float, total: Int) {
            val proporcion = (x / total).coerceIn(0f, 1f)
            val nuevo = TAMANO_MENOR + (proporcion * (TAMANO_MAYOR - TAMANO_MENOR)).toInt()
            alCambiar(nuevo / 5 * 5)
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(18.dp)
                .pointerInput(activo) {
                    if (activo) {
                        detectTapGestures { punto -> mover(punto.x, size.width) }
                    }
                }
                .pointerInput(activo) {
                    if (activo) {
                        detectDragGestures { cambio, _ -> mover(cambio.position.x, size.width) }
                    }
                },
            contentAlignment = Alignment.CenterStart,
        ) {
            Box(Modifier.fillMaxWidth().height(6.dp).background(paleta.bordeSuave, RoundedCornerShape(2.dp)))
            Box(Modifier.fillMaxWidth(parte.coerceAtLeast(0.01f)).height(6.dp).background(color, RoundedCornerShape(2.dp)))
            Box(Modifier.offset(x = (ancho - 18.dp) * parte).size(18.dp).marco(paleta.panel, color, 4.dp))
        }
    }
}

@Composable
private fun SeccionInstalada(datos: JsonObject) {
    val placa = datos.objeto("board")
    Rotulo(t("INSTALLED BIOS"))
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(18.dp)) {
        val hechos = listOf(t("Version") to placa.texto("version"), t("Date") to placa.texto("date"), t("Board") to placa.texto("board"))
        for ((nombre, valor) in hechos) {
            Column(Modifier.weight(1f), Arrangement.spacedBy(4.dp)) {
                Rotulo(nombre)
                Texto(valor.ifEmpty { "--" }, tamano = 13, peso = 720)
            }
        }
    }
}

@Composable
private fun SeccionUnidades(datos: JsonObject, eleccion: EleccionFirmware) {
    val paleta = ColoresActuales.current
    val unidades = datos.objetos("drives")
    Rotulo(t("USB drive"))
    if (unidades.isEmpty()) {
        Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
            Esperando()
            Leyenda(t("Waiting for a USB drive…"))
        }
        Leyenda(t("Plug in a USB drive of at least 1 GB and it shows up here by itself. Everything on it will be erased."))
    }
    for (unidad in unidades) {
        val id = unidad.texto("id")
        val puede = unidad.logico("eligible")
        val elegida = id == eleccion.unidad
        val borde = if (elegida) paleta.acentoBorde else paleta.borde
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 52.dp)
                .marco(if (elegida) paleta.elegido else paleta.panelAlterno, borde, Medidas.radioBoton)
                .pulsable(puede) { eleccion.unidad = id }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Opcion(elegida, color = paleta.acento)
            Column(Modifier.weight(1f)) {
                Texto(unidad.texto("name") + " · " + unidad.texto("size_text"), tamano = 13, peso = 700)
                val nota = unidad.texto("blocker").ifEmpty { unidad.texto("warning") }
                val contenido = unidad.textos("labels").joinToString(", ").ifEmpty { t("No volumes") }
                Texto(nota.ifEmpty { unidad.texto("path") + " · " + contenido }, 11, color = if (nota.isEmpty()) paleta.apagado else paleta.naranja)
            }
        }
    }
}

@Composable
private fun SeccionResumen(aplicacion: Aplicacion, datos: JsonObject, familia: JsonObject?, eleccion: EleccionFirmware) {
    val imagenes = familia?.objetos("images") ?: emptyList()
    val clave = eleccion.imagen.ifEmpty { familia?.texto("default_image") ?: "" }
    val imagen = imagenes.firstOrNull { item -> item.texto("key") == clave }
    val unidad = datos.objetos("drives").firstOrNull { item -> item.texto("id") == eleccion.unidad }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    Rotulo(t("Preparation"))
    Column {
        HechoFila(t("Firmware"), familia?.texto("title") ?: "--")
        LineaDivisoria()
        if (imagenes.size > 1) {
            val opciones = imagenes.map { item -> Eleccion(item.texto("key"), item.texto("label")) }
            Desplegable(opciones, clave, { valor -> eleccion.imagen = valor }, Modifier.fillMaxWidth())
            LineaDivisoria()
        }
        HechoFila(t("USB drive"), unidad?.texto("name") ?: t("Choose a USB drive"))
        LineaDivisoria()
        HechoFila(t("Download"), textoDescarga(imagen))
    }
    val lista = familia != null && imagen != null && unidad != null && imagen.logico("available")
    Boton(
        texto = t("Prepare USB"),
        alPulsar = { prepararUsb(aplicacion, datos, familia, clave, unidad, eleccion) },
        modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
        clase = ClaseBoton.PRINCIPAL,
        activo = libre && lista && datos.logico("udisks"),
        alto = 44.dp,
        peso = 780,
    )
}

private fun textoDescarga(imagen: JsonObject?): String {
    if (imagen == null) {
        return "--"
    }
    return imagen.texto("size").ifEmpty { imagen.texto("detail") }
}

private fun prepararUsb(
    aplicacion: Aplicacion,
    datos: JsonObject,
    familia: JsonObject?,
    imagen: String,
    unidad: JsonObject?,
    eleccion: EleccionFirmware,
) {
    if (familia == null || unidad == null) {
        return
    }
    val conLogo = eleccion.logo != null && familia.logico("logo_replaceable")
    val parametros = mapOf<String, JsonElement>(
        "family" to JsonPrimitive(familia.texto("key")),
        "image" to JsonPrimitive(imagen),
        "drive" to JsonPrimitive(unidad.texto("id")),
        "logo" to JsonPrimitive(conLogo),
    )
    val mensaje = t("Everything on it will be erased and replaced by the BIOS update kit. This cannot be undone.") +
        "\n\n" + familia.texto("title") + "\n" + unidad.texto("name") + " · " + unidad.texto("size_text") +
        "\n\n" + t(datos.texto("cmos_warning"))
    aplicacion.preguntarYEjecutar("firmware.prepare", t("Erase this USB drive?"), mensaje, parametros, peligro = true)
}
