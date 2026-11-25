package org.bc250.controlcenter.movil

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Bloque
import org.bc250.controlcenter.componentes.BorradorReporte
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.LocalPaletas
import org.bc250.controlcenter.componentes.Logotipo
import org.bc250.controlcenter.componentes.Ordenes
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.cambiarInterruptorAjuste
import org.bc250.controlcenter.componentes.elegirAjuste
import org.bc250.controlcenter.componentes.enviar
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.tema.ColoresActuales

private const val LARGO_EN_LINEA = 18

@Composable
fun BloquesMovil(bloques: List<JsonObject>, ordenes: Ordenes, aplicacion: Aplicacion) {
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp)) {
        FilasBloquesMovil(bloques, ordenes, aplicacion)
    }
}

@Composable
internal fun FilasBloquesMovil(bloques: List<JsonObject>, ordenes: Ordenes, aplicacion: Aplicacion) {
    for (bloque in bloques) BloqueMovil(bloque, ordenes, aplicacion)
}

@Composable
private fun BloqueMovil(bloque: JsonObject, ordenes: Ordenes, aplicacion: Aplicacion) {
    val movil = movil()
    when (bloque.texto("tipo")) {
        "grupo" -> {
            val titulo = bloque.texto("titulo")
            if (titulo.isEmpty()) GrupoMovil { HijosMovil(bloque, ordenes, aplicacion) }
            else SeccionMovil(titulo) { GrupoMovil { HijosMovil(bloque, ordenes, aplicacion) } }
        }
        "fila" -> FilaBloqueMovil(bloque, ordenes)
        "enlace" -> FilaAbrir(bloque.texto("texto")) { ordenes.cumplir(bloque.objeto("orden")) }
        "parrafo", "recuadro" -> NotaMovil(bloque.texto("texto"), tamano = 13)
        "advertencia" -> NotaMovil(bloque.texto("texto"), ColoresActuales.current.naranja, 13)
        "titulo", "titulo_guia" -> SeccionMovil(
            (if (bloque.entero("numero") > 0) bloque.entero("numero").toString() + " · " else "") + bloque.texto("texto"),
        ) {
            if (bloque.texto("marca").isNotEmpty()) NotaMovil(bloque.texto("marca"))
        }
        "puntos" -> for (texto in bloque.textos("textos")) TextoHoja("• $texto")
        "comando" -> GrupoMovil {
            FilaLibre { TextosFila(bloque.texto("texto")) }
            TiraAcciones(AccionTira(t("Copy")) { ordenes.copiar(bloque.texto("texto")) })
        }
        "botones" -> BotonesBloqueMovil(bloque, ordenes)
        "tabla" -> TablaMovil(bloque)
        "cabecera" -> {
            SeccionMovil(bloque.texto("texto")) {
                if (bloque.texto("cuenta").isNotEmpty()) {
                    NotaMovil(bloque.texto("cuenta"))
                }
                val control = bloque.objeto("interruptor")
                if (control.isNotEmpty()) {
                    GrupoMovil { InterruptorBloqueMovil(control.texto("texto"), "", control, ordenes) }
                }
                BotonesBloqueMovil(bloque, ordenes)
            }
        }
        "pestanas" -> {
            val opciones = bloque.objetos("pestanas")
            var elegida by remember { mutableStateOf(opciones.firstOrNull()?.texto("clave") ?: "") }
            SegmentadoMovil(opciones.map { it.texto("clave") to it.texto("nombre") }, elegida) { elegida = it }
            BloquesMovil(opciones.firstOrNull { it.texto("clave") == elegida }?.objetos("bloques") ?: emptyList(),
                ordenes, aplicacion)
        }
        "temas" -> SegmentadoMovil(opcionesDe(bloque), bloque.texto("valor")) {
            ordenes.guardar("theme", JsonPrimitive(it))
        }
        "terminales" -> {
            val opciones = bloque.objetos("grupos").flatMap { it.objetos("tarjetas") }
            FilaAbrir(t("Terminal theme"), valor = opciones.firstOrNull {
                it.texto("valor") == bloque.texto("valor")
            }?.texto("nombre") ?: "") {
                movil.abrirLista(t("Terminal theme"), opciones.map { it.texto("valor") to it.texto("nombre") },
                    bloque.texto("valor")) { ordenes.guardar("console_theme", JsonPrimitive(it)) }
            }
        }
        "identidad" -> GrupoMovil {
            FilaLibre {
                Logotipo(48.dp)
                TextosFila(bloque.texto("nombre"), bloque.texto("detalle"))
            }
            BotonEnGrupo(bloque.objeto("boton"), ordenes)
        }
        "hechos" -> GrupoMovil {
            for (dato in bloque.objetos("hechos")) FilaDato(dato.texto("nombre"), dato.texto("valor"))
        }
        "distribucion" -> FilaAbrir(bloque.texto("nombre"), valor = nombreOpcion(bloque)) {
            movil.abrirLista(bloque.texto("nombre"), opcionesDe(bloque), bloque.texto("valor")) {
                ordenes.ir("", mapOf("distro" to it))
            }
        }
        "tarjetas" -> GrupoMovil {
            for (tarjeta in bloque.objetos("tarjetas")) {
                FilaAbrir(tarjeta.texto("titulo"), tarjeta.texto("detalle")) { ordenes.cumplir(tarjeta.objeto("orden")) }
            }
        }
        "fichas", "errores" -> FichasMovil(bloque, ordenes)
        "enviados" -> EnviadosMovil(bloque, ordenes)
        "ficha_reporte" -> GrupoMovil {
            for (dato in bloque.objetos("datos")) FilaDato(dato.texto("nombre"), dato.texto("valor"))
            FilaLibre { TextosFila(bloque.texto("encabezado"), bloque.textos("adjuntos").joinToString("\n")
                .ifEmpty { bloque.texto("vacio") }) }
            BotonEnGrupo(bloque.objeto("boton"), ordenes)
        }
        "reporte" -> ReporteMovil(bloque, ordenes, aplicacion)
        "regla" -> Unit
        // Las fotos y sus ampliaciones ya se ajustan al ancho disponible.
        "foto", "fotos" -> Bloque(bloque, ordenes)
    }
}

/** Los bloques que ya traen su propio margen dentro de un grupo. */
private val SinMargen = setOf("fila", "enlace", "distribucion", "terminales", "regla")

@Composable
private fun BotonEnGrupo(boton: JsonObject, ordenes: Ordenes) {
    if (boton.isNotEmpty()) {
        Box(Modifier.padding(14.dp)) { BotonBloqueMovil(boton, ordenes) }
    }
}

@Composable
private fun HijosMovil(bloque: JsonObject, ordenes: Ordenes, aplicacion: Aplicacion) {
    FilasDeGrupo(bloque.objetos("bloques"), ordenes, aplicacion)
}

/** Las filas de un grupo; lo que no es una fila lleva su margen. */
@Composable
internal fun FilasDeGrupo(bloques: List<JsonObject>, ordenes: Ordenes, aplicacion: Aplicacion) {
    for (hijo in bloques) {
        if (hijo.texto("tipo") in SinMargen) {
            BloqueMovil(hijo, ordenes, aplicacion)
        } else {
            Box(Modifier.fillMaxWidth().lineaArriba().padding(14.dp)) { BloqueMovil(hijo, ordenes, aplicacion) }
        }
    }
}

private fun opcionesDe(control: JsonObject): List<Pair<String, String>> =
    control.objetos("opciones").map { it.texto("valor") to it.texto("nombre") }

private fun nombreOpcion(control: JsonObject): String =
    opcionesDe(control).firstOrNull { it.first == control.texto("valor") }?.second ?: control.texto("valor")

@Composable
private fun FilaBloqueMovil(fila: JsonObject, ordenes: Ordenes) {
    val control = fila.objeto("control")
    val titulo = fila.texto("titulo")
    val detalle = fila.texto("detalle")
    val movil = movil()
    when (control.texto("tipo")) {
        "lista" -> FilaAbrir(titulo, valor = nombreOpcion(control)) {
            movil.abrirHoja {
                TituloHoja(titulo)
                if (detalle.isNotEmpty()) TextoHoja(detalle)
                GrupoMovil {
                    for ((valor, nombre) in opcionesDe(control)) {
                        FilaRadio(nombre, valor == control.texto("valor")) {
                            elegirAjuste(control, ordenes, valor)
                            movil.cerrarHoja()
                        }
                    }
                }
                CerrarHoja()
            }
        }
        "interruptor" -> InterruptorBloqueMovil(titulo, detalle, control, ordenes)
        "segmentos" -> {
            SegmentadoMovil(opcionesDe(control), control.texto("valor")) {
                ordenes.guardar(control.texto("clave"), JsonPrimitive(it))
            }
        }
        "acentos" -> GrupoMovil {
            Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
                AcentosMovil(control, ordenes)
            }
        }
        "botones" -> Column(Modifier.padding(14.dp), Arrangement.spacedBy(10.dp)) {
            TextosControl(titulo, detalle)
            BotonesBloqueMovil(control, ordenes)
        }
        "ruta" -> FilaAbrir(titulo, detalle, control.texto("boton")) {
            movil.abrirHoja {
                TituloHoja(titulo)
                TextoHoja(control.texto("texto"))
                BotonMovil(control.texto("boton")) { ordenes.cumplir(control.objeto("orden")) }
                CerrarHoja()
            }
        }
        else -> FilaLibre {
            val valor = control.texto("texto")
            val largo = valor.length > LARGO_EN_LINEA
            TextosFila(titulo, if (largo) "$detalle\n$valor".trim() else detalle)
            if (!largo) {
                ValorConUnidad(valor)
            }
        }
    }
}

@Composable
private fun TextosControl(titulo: String, detalle: String) {
    Column {
        Texto(titulo, tamano = 14, peso = 700)
        if (detalle.isNotEmpty()) {
            Texto(detalle, tamano = 12, color = ColoresActuales.current.sutil)
        }
    }
}

@Composable
private fun InterruptorBloqueMovil(titulo: String, detalle: String, control: JsonObject, ordenes: Ordenes) {
    FilaLibre {
        TextosFila(titulo, detalle)
        InterruptorMovil(control.logico("activo")) { cambiarInterruptorAjuste(control, ordenes, it) }
    }
}

@Composable
private fun AcentosMovil(control: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val paletas = LocalPaletas.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        for (fila in opcionesDe(control).chunked(5)) {
            Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                for ((valor, _) in fila) {
                    val borde = if (valor == control.texto("valor")) paleta.texto else paleta.borde
                    val muestra = paletas.paleta(paletas.estilo, paletas.tema, valor) ?: paleta
                    CompositionLocalProvider(ColoresActuales provides muestra) {
                        Box(Modifier.size(44.dp).background(ColoresActuales.current.acento, CircleShape)
                            .border(2.dp, borde, CircleShape)
                            .pulsable { ordenes.guardar("accent", JsonPrimitive(valor)) })
                    }
                }
            }
        }
    }
}

@Composable
private fun BotonBloqueMovil(boton: JsonObject, ordenes: Ordenes) {
    if (boton.isEmpty()) return
    val clase = if (boton.texto("clase") == "principal") ClaseBoton.PRINCIPAL else ClaseBoton.NORMAL
    BotonMovil(boton.texto("texto"), Modifier.fillMaxWidth(), clase, boton.logico("activo", true)) {
        ordenes.cumplir(boton.objeto("orden"))
    }
}

@Composable
private fun BotonesBloqueMovil(bloque: JsonObject, ordenes: Ordenes) {
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
        if (bloque.texto("estado").isNotEmpty()) NotaMovil(bloque.texto("estado"))
        for (pareja in bloque.objetos("botones").chunked(2)) {
            ParejaBotones {
                for (boton in pareja) {
                    Box(Modifier.weight(1f)) { BotonBloqueMovil(boton, ordenes) }
                }
            }
        }
    }
}

@Composable
private fun TablaMovil(bloque: JsonObject) {
    val movil = movil()
    val columnas = bloque.textos("columnas")
    GrupoMovil {
        if (bloque.objetos("filas").isEmpty()) FilaLibre { TextosFila(bloque.texto("pista")) }
        for (fila in bloque.objetos("filas")) {
            val celdas = fila.textos("celdas")
            FilaAbrir(celdas.firstOrNull() ?: "", celdas.drop(1).joinToString(" · ")) {
                movil.abrirHoja {
                    TituloHoja(celdas.firstOrNull() ?: "")
                    GrupoMovil {
                        for ((indice, valor) in celdas.withIndex()) FilaDato(columnas.getOrElse(indice) { "" }, valor)
                    }
                    if (bloque.logico("con_detalle")) TextoHoja(fila.texto("detalle").ifEmpty { bloque.texto("pista") })
                    CerrarHoja()
                }
            }
        }
    }
}

@Composable
private fun FichasMovil(bloque: JsonObject, ordenes: Ordenes) {
    val errores = bloque.texto("tipo") == "errores"
    var busqueda by remember { mutableStateOf(bloque.texto("consulta")) }
    var modulo by remember { mutableStateOf(bloque.texto("modulo")) }
    val movil = movil()
    LaunchedEffect(busqueda, modulo) {
        if (errores && (busqueda != bloque.texto("consulta") || modulo != bloque.texto("modulo"))) {
            delay(250)
            ordenes.ir("support_errors", mapOf("query" to busqueda, "module" to modulo))
        }
    }
    CampoMovil(busqueda, Modifier.fillMaxWidth(), ayuda = bloque.texto("buscar")) { busqueda = it }
    if (errores) {
        val opciones = bloque.objetos("modulos").map { it.texto("valor") to it.texto("nombre") }
        FilaAbrir(t("Module"), valor = opciones.firstOrNull { it.first == modulo }?.second ?: "") {
            movil.abrirLista(t("Module"), opciones, modulo) { modulo = it }
        }
    }
    val fichas = bloque.objetos("fichas").filter {
        errores || (it.texto("titulo") + " " + it.texto("detalle")).contains(busqueda.trim(), ignoreCase = true)
    }
    GrupoMovil {
        for (ficha in fichas) {
            FilaLibre {
                val numero = ficha.texto("numero")
                TextosFila((if (numero.isEmpty()) "" else "$numero · ") + ficha.texto("titulo"), ficha.texto("detalle"))
            }
            if (ficha.texto("marca").isNotEmpty()) {
                Box(Modifier.padding(horizontal = 12.dp)) { NotaMovil(ficha.texto("marca"), ColoresActuales.current.naranja) }
            }
            BotonEnGrupo(ficha.objeto("boton"), ordenes)
        }
    }
    if (fichas.isEmpty()) {
        NotaMovil(bloque.texto("vacio"))
        if (errores) {
            NotaMovil(bloque.texto("ayuda"))
            for (sugerencia in bloque.objetos("sugerencias")) {
                BotonMovil(sugerencia.texto("texto"), Modifier.fillMaxWidth()) {
                    busqueda = sugerencia.texto("buscar")
                    modulo = sugerencia.texto("modulo")
                }
            }
            BotonMovil(bloque.texto("reportar"), Modifier.fillMaxWidth()) {
                ordenes.ir("support_report", mapOf("query" to busqueda))
            }
        }
    }
}

@Composable
private fun EnviadosMovil(bloque: JsonObject, ordenes: Ordenes) {
    var semana by remember { mutableStateOf(false) }
    SeccionMovil(bloque.texto("titulo")) {
        SegmentadoMovil(listOf("all" to bloque.texto("todos"), "week" to bloque.texto("semana")),
            if (semana) "week" else "all") { semana = it == "week" }
        val filas = bloque.objetos("filas").filter { !semana || it.logico("semana") }
        GrupoMovil {
            if (filas.isEmpty()) FilaLibre { TextosFila(bloque.texto("vacio")) }
            for (fila in filas) {
                val id = fila.texto("id")
                FilaAbrir(fila.texto("titulo"), fila.texto("detalle") + "\n" + id + " · " +
                    fila.texto("version") + " · " + fila.texto("cuando")) {
                    ordenes.ir("support_detail", mapOf("id" to id))
                }
                TiraAcciones(AccionTira(bloque.texto("copiar")) { ordenes.copiar(id) })
            }
        }
    }
}

@Composable
private fun ReporteMovil(bloque: JsonObject, ordenes: Ordenes, aplicacion: Aplicacion) {
    val borrador = remember { BorradorReporte(bloque.objeto("valores")) }
    SegmentadoMovil(listOf("problem" to t("Report a problem"), "idea" to t("Suggest an idea")), borrador.clase) {
        borrador.clase = it
    }
    if (borrador.clase == "problem") ProblemaMovil(bloque, borrador, ordenes)
    else CampoReporte(t("Suggestions and ideas") + " *", "notes", borrador, largo = true)
    CampoReporte(t("Telegram or Discord username"), "contact", borrador)
    NotaMovil(t("Optional. Only if you want an answer."))
    ParejaBotones {
        BotonMovil(t("Cancel"), Modifier.weight(1f)) { ordenes.ir("support") }
        BotonMovil(t("Send"), Modifier.weight(1f), ClaseBoton.PRINCIPAL,
            aplicacion.puedeControlar && aplicacion.trabajo.terminado) { enviar(borrador, bloque, ordenes) }
    }
}

@Composable
private fun ProblemaMovil(bloque: JsonObject, borrador: BorradorReporte, ordenes: Ordenes) {
    val movil = movil()
    CampoReporte(t("What went wrong?") + " *", "summary", borrador,
        ayuda = t("Example: \"GPU governor stops after a few seconds\""))
    GrupoMovil {
        ListaReporte(t("Which part of the app?"), "areas", "area", bloque, borrador)
        ListaReporte(t("How often does it happen?"), "frecuencias", "frequency", bloque, borrador)
        ListaReporte(t("Did it work before?"), "antes", "worked_before", bloque, borrador)
    }
    CampoReporte(t("Error code"), "code", borrador, ayuda = "BC250-…")
    SeccionMovil(t("What did you see?")) { MarcasReporte(bloque.objetos("vistos"), borrador.vistos) }
    CampoReporte(t("Steps to reproduce"), "steps", borrador, largo = true)
    CampoReporte(t("What did you expect to happen?"), "expected", borrador, largo = true)
    GrupoMovil {
        FilaAbrir(t("Your system")) { movil.abrirHoja { SistemaReporte(bloque, borrador) } }
        FilaAbrir(t("Logs")) {
            movil.abrirHoja {
                TituloHoja(t("Logs"))
                CampoReporte(t("Terminal output"), "terminal", borrador, largo = true)
                CampoReporte(t("Screenshot or video link"), "media", borrador, ayuda = "https://…")
                CerrarHoja()
            }
        }
        FilaAbrir(t("Automatic report")) { movil.abrirHoja { AutomaticoReporte(bloque, borrador, ordenes) } }
        FilaAbrir(t("Suggestions and ideas")) {
            movil.abrirHoja {
                TituloHoja(t("Suggestions and ideas"))
                CampoReporte(t("Suggestions and ideas"), "notes", borrador, largo = true)
                CerrarHoja()
            }
        }
    }
}

@Composable
private fun SistemaReporte(bloque: JsonObject, borrador: BorradorReporte) {
    TituloHoja(t("Your system"))
    TextoHoja(t("Filled in from this system. Change anything that is wrong."))
    GrupoMovil {
        ListaReporte(t("Distribution"), "distribuciones", "distribution", bloque, borrador)
        ListaReporte(t("How did you install it?"), "instalaciones", "install", bloque, borrador)
        ListaReporte(t("BIOS"), "bios", "bios", bloque, borrador)
        ListaReporte(t("CPU cores"), "nucleos", "cores", bloque, borrador)
        ListaReporte(t("GPU compute units"), "unidades", "cus", bloque, borrador)
    }
    CampoReporte(t("Control Center version"), "version", borrador)
    SeccionMovil(t("Other BC-250 tools you used on this system")) {
        MarcasReporte(bloque.objetos("herramientas"), borrador.herramientas)
    }
    CerrarHoja()
}

@Composable
private fun AutomaticoReporte(bloque: JsonObject, borrador: BorradorReporte, ordenes: Ordenes) {
    TituloHoja(t("Automatic report"))
    TextoHoja(t("Captured by Control Center. Nothing here needs to be written by you."))
    GrupoMovil {
        for (dato in bloque.objetos("automatico")) FilaDato(dato.texto("nombre"), dato.texto("valor"))
        FilaInterruptor(t("Send the automatic report"), borrador.adjuntar) { borrador.adjuntar = it }
    }
    BotonMovil(t("See what is sent"), Modifier.fillMaxWidth()) {
        org.bc250.controlcenter.componentes.previsualizarReporte(borrador, ordenes)
    }
    TextoHoja(t("Linux may ask for your password once to read the kernel log for this report. " +
        "If you cancel it, the report is still sent, without that log."))
    CerrarHoja()
}

@Composable
private fun MarcasReporte(opciones: List<JsonObject>, marcadas: MutableList<String>) {
    GrupoMovil {
        for (opcion in opciones) {
            val valor = opcion.texto("valor")
            FilaInterruptor(opcion.texto("nombre"), valor in marcadas) {
                if (it) marcadas.add(valor) else marcadas.remove(valor)
            }
        }
    }
}

@Composable
private fun ListaReporte(titulo: String, lista: String, clave: String, bloque: JsonObject, borrador: BorradorReporte) {
    val opciones = bloque.objetos(lista).map { it.texto("valor") to it.texto("nombre") }
    val valor = borrador.leer(clave)
    val otro = bloque.texto("otro")
    val conocido = opciones.any { it.first == valor }
    var escribiendo by remember { mutableStateOf(valor.isNotEmpty() && !conocido) }
    val movil = movil()
    FilaAbrir(titulo, valor = opciones.firstOrNull { it.first == valor }?.second ?: valor.ifEmpty { t("Choose…") }) {
        movil.abrirHoja {
            TituloHoja(titulo)
            GrupoMovil {
                for ((id, nombre) in opciones) {
                    FilaRadio(nombre, id == borrador.leer(clave)) {
                        escribiendo = id == otro
                        borrador.escribir(clave, if (escribiendo) "" else id)
                    }
                }
            }
            if (escribiendo) CampoReporte(otro, clave, borrador)
            CerrarHoja()
        }
    }
}

@Composable
private fun CampoReporte(
    titulo: String,
    clave: String,
    borrador: BorradorReporte,
    largo: Boolean = false,
    ayuda: String = "",
) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
        Texto(titulo, tamano = 13, peso = 700)
        if (largo) {
            BasicTextField(
                value = borrador.leer(clave),
                onValueChange = { borrador.escribir(clave, it) },
                textStyle = estiloTexto(14),
                cursorBrush = SolidColor(paleta.texto),
                minLines = 4,
                modifier = Modifier.fillMaxWidth().marco(paleta.control, paleta.borde, 6.dp).padding(12.dp),
            )
        } else CampoMovil(borrador.leer(clave), Modifier.fillMaxWidth(), ayuda) { borrador.escribir(clave, it) }
    }
}
