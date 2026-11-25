package org.bc250.controlcenter.movil

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.datos.Aplicacion
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
import org.bc250.controlcenter.paginas.EleccionFirmware
import org.bc250.controlcenter.paginas.guardarLogoFirmware
import org.bc250.controlcenter.paginas.prepararUsb
import org.bc250.controlcenter.tema.ColoresActuales
import org.jetbrains.compose.resources.decodeToImageBitmap

@Composable
fun PaginaFirmwareMovil(aplicacion: Aplicacion) {
    val eleccion = remember { EleccionFirmware() }
    LaunchedEffect(Unit) {
        while (true) {
            aplicacion.leerPagina("firmware")
            delay(3000)
        }
    }
    val datos = aplicacion.lectura("firmware")
    LaunchedEffect(datos.texto("default_family")) {
        if (eleccion.familia.isEmpty()) eleccion.familia = datos.texto("default_family")
    }
    val familia = datos.objetos("families").firstOrNull { it.texto("key") == eleccion.familia }
    val clave = eleccion.imagen.ifEmpty { familia?.texto("default_image") ?: "" }
    val imagen = familia?.objetos("images")?.firstOrNull { it.texto("key") == clave }
    val unidad = datos.objetos("drives").firstOrNull { it.texto("id") == eleccion.unidad }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && !eleccion.guardandoLogo
    val lista = familia != null && imagen != null && unidad != null && unidad.logico("eligible") && imagen.logico("available")
    PaginaMovil("firmware", pie = {
        BotonMovil(t("Prepare USB"), Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && lista && datos.logico("udisks")) {
            prepararUsb(aplicacion, datos, familia, clave, unidad, eleccion)
        }
    }) {
        EstadoLecturaMovil(datos)
        val familias = datos.objetos("families")
        CatalogoFirmware(t("Modded BIOS"), familias.filter { it.texto("origin") != "stock" }, eleccion)
        CatalogoFirmware(t("Stock BIOS (ASRock)"), familias.filter { it.texto("origin") == "stock" }, eleccion)
        LogoFirmware(aplicacion, datos, familia, eleccion)
        UnidadesFirmware(datos, eleccion)
        NotaMovil(t("Everything on it will be erased. The app never flashes the BIOS."), ColoresActuales.current.naranja)
        val movil = movil()
        GrupoMovil {
            FilaAbrir(t("Preparation"), valor = imagen?.texto("label") ?: "") {
                movil.abrirHoja { ResumenFirmware(datos, familia, eleccion) }
            }
            FilaAbrir(t("INSTALLED BIOS"), valor = datos.objeto("board").texto("version", "--")) {
                movil.abrirHoja {
                    TituloHoja(t("INSTALLED BIOS"))
                    GrupoMovil {
                        val placa = datos.objeto("board")
                        FilaDato(t("Version"), placa.texto("version", "--"))
                        FilaDato(t("Date"), placa.texto("date", "--"))
                        FilaDato(t("Board"), placa.texto("board", "--"))
                    }
                    CerrarHoja()
                }
            }
        }
    }
}

@Composable
private fun CatalogoFirmware(titulo: String, familias: List<JsonObject>, eleccion: EleccionFirmware) {
    if (familias.isEmpty()) return
    val movil = movil()
    SeccionMovil(titulo) {
        for (familia in familias) {
            val nucleos = t("CPU cores") + " " + familia.entero("cores")
            val vram = t("VRAM in the BIOS") + ": " + t(if (familia.logico("vram_menu")) "Yes" else "No")
            TarjetaPerfilMovil(
                nombre = familia.texto("title"),
                valor = "",
                detalle = familia.texto("summary") + "\n$nucleos · $vram · " + familia.texto("download"),
                elegido = eleccion.familia == familia.texto("key"),
                adorno = { FlechaDetalle { movil.abrirHoja { DetalleFamilia(familia) } } },
            ) {
                eleccion.familia = familia.texto("key")
                eleccion.imagen = ""
            }
        }
    }
}

@Composable
private fun DetalleFamilia(familia: JsonObject) {
    TituloHoja(familia.texto("title"))
    TextoHoja(familia.texto("summary"))
    for (ventaja in familia.textos("highlights")) TextoHoja("• $ventaja")
    GrupoMovil {
        FilaDato(t("VRAM in the BIOS"), t(if (familia.logico("vram_menu")) "Yes" else "No"))
        FilaDato(t("CPU cores"), t("{active} of {total}", "active" to familia.entero("cores").toString(), "total" to "8"))
        val logos = familia.entero("boot_logos")
        val texto = if (logos > 0) t("{count} to choose from", "count" to logos.toString()) else t("As shipped")
        FilaDato(t("Boot logo"), texto)
        FilaDato(t("After flashing"), t("Clear CMOS"), color = ColoresActuales.current.naranja)
    }
    if (familia.texto("caution").isNotEmpty()) NotaMovil(familia.texto("caution"), ColoresActuales.current.naranja)
    TextoHoja(t("Every file comes from the project that publishes it and is checked against its SHA-256 before it reaches the USB."))
    CerrarHoja()
}

@OptIn(ExperimentalEncodingApi::class)
@Composable
private fun LogoFirmware(aplicacion: Aplicacion, datos: JsonObject, familia: JsonObject?, eleccion: EleccionFirmware) {
    val paleta = ColoresActuales.current
    val tareas = rememberCoroutineScope()
    val movil = movil()
    val logo = eleccion.logo
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && !eleccion.guardandoLogo
    val admite = familia?.logico("logo_replaceable") == true && datos.texto("logo_codec").isEmpty()
    fun guardar(imagen: org.bc250.controlcenter.datos.ImagenLogo?) {
        guardarLogoFirmware(aplicacion, eleccion, imagen, tareas)
    }
    SeccionMovil(t("Boot logo")) {
        GrupoMovil {
            Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(paleta.color("console_bg")), Alignment.Center) {
                    if (logo == null) TextoHoja(t("Your picture shows here"))
                    else {
                        val dibujo = remember(logo.jpegBase64) { Base64.decode(logo.jpegBase64).decodeToImageBitmap() }
                        Image(dibujo, logo.nombre, Modifier.fillMaxWidth())
                    }
                }
                ParejaBotones {
                    BotonMovil(t("Choose picture…"), Modifier.weight(1f), activo = admite && puedeElegirImagen && libre) {
                        eleccion.tamano = 100
                        elegirImagen(::guardar)
                    }
                    BotonMovil(t("Remove"), Modifier.weight(1f), activo = logo != null && libre) { guardar(null) }
                }
            }
            FilaAbrir(t("Custom boot logo"), valor = logo?.nombre ?: "") {
                movil.abrirHoja {
                    HojaLogoFirmware(aplicacion, eleccion, admite)
                }
            }
        }
    }
}

@Composable
private fun HojaLogoFirmware(aplicacion: Aplicacion, eleccion: EleccionFirmware, admite: Boolean) {
    val datos = aplicacion.lectura("firmware")
    val logo = eleccion.logo
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado && !eleccion.guardandoLogo
    val tareas = rememberCoroutineScope()
    fun guardar(imagen: org.bc250.controlcenter.datos.ImagenLogo?) {
        guardarLogoFirmware(aplicacion, eleccion, imagen, tareas)
    }
    TituloHoja(t("Custom boot logo"))
    TextoHoja(t("Put your own picture on the screen the board shows while it starts. " +
        "It goes into the chosen firmware when the USB is prepared, and nothing else in that firmware changes."))
    GrupoMovil {
        FilaDato(t("File name"), logo?.nombre ?: "--")
        FilaDato(t("Original size"), if (logo == null) "--" else "${logo.ancho} × ${logo.alto} px")
        val kb = (logo?.jpegBase64?.length ?: 0) * 3 / 4 / 1024
        FilaDato(t("In the firmware"), if (logo == null) "--" else "672 × 378 px · JPEG · $kb KB")
        FilaPaso(t("Size"), eleccion.tamano, "%", 30, 100, 5, activa = logo != null && admite && libre) {
            eleccion.tamano = it
            reescalarImagen(it, ::guardar)
        }
    }
    if (datos.texto("logo_codec").isNotEmpty()) NotaMovil(datos.texto("logo_codec"))
    TextoHoja(t("Before the USB is written, the new firmware is read back and compared with the published one: " +
        "only the logo may differ. Custom logos have been tested on real boards with P2.00, P3.00, " +
        "P5.00 and MeiMeiDXE v3. " +
        "As with any BIOS change, an SPI programmer at hand is the way back."))
    CerrarHoja()
}

@Composable
private fun UnidadesFirmware(datos: JsonObject, eleccion: EleccionFirmware) {
    SeccionMovil(t("USB drive")) {
        GrupoMovil {
            if (datos.objetos("drives").isEmpty()) {
                FilaLibre { TextosFila(t("Waiting for a USB drive…"),
                    t("Plug in a USB drive of at least 1 GB and it shows up here by itself. Everything on it will be erased.")) }
            }
            for (unidad in datos.objetos("drives")) {
                val nota = unidad.texto("blocker").ifEmpty { unidad.texto("warning") }
                val volumenes = unidad.textos("labels").joinToString(", ").ifEmpty { t("No volumes") }
                FilaRadio(
                    unidad.texto("name") + " · " + unidad.texto("size_text"),
                    unidad.texto("id") == eleccion.unidad,
                    nota.ifEmpty { unidad.texto("path") + " · " + volumenes },
                    activa = unidad.logico("eligible"),
                ) { eleccion.unidad = unidad.texto("id") }
            }
        }
    }
}

@Composable
private fun ResumenFirmware(datos: JsonObject, familia: JsonObject?, eleccion: EleccionFirmware) {
    val movil = movil()
    val imagenes = familia?.objetos("images") ?: emptyList()
    val clave = eleccion.imagen.ifEmpty { familia?.texto("default_image") ?: "" }
    val imagen = imagenes.firstOrNull { it.texto("key") == clave }
    TituloHoja(t("Preparation"))
    GrupoMovil {
        FilaDato(t("Firmware"), familia?.texto("title") ?: "--")
        if (imagenes.size > 1) {
            FilaAbrir(t("Boot logo"), valor = imagen?.texto("label") ?: "") {
                movil.abrirLista(t("Boot logo"), imagenes.map { it.texto("key") to it.texto("label") }, clave) {
                    eleccion.imagen = it
                }
            }
        }
        val unidad = datos.objetos("drives").firstOrNull { it.texto("id") == eleccion.unidad }
        FilaDato(t("USB drive"), unidad?.texto("name") ?: t("Choose a USB drive"))
        FilaDato(t("Download"), imagen?.texto("size")?.ifEmpty { imagen.texto("detail") } ?: "--")
    }
    CerrarHoja()
}
