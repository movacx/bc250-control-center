package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

private const val PROBLEMA = "problem"
private const val IDEA = "idea"

/** Lo que la persona ha escrito en el reporte. */
class BorradorReporte(iniciales: JsonObject) {
    var clase by mutableStateOf(PROBLEMA)
    var adjuntar by mutableStateOf(true)
    val valores = mutableStateMapOf<String, String>()
    val vistos = mutableStateListOf<String>()
    val herramientas = mutableStateListOf<String>()

    init {
        for (clave in iniciales.keys) {
            valores[clave] = iniciales.texto(clave)
        }
    }

    fun leer(clave: String): String {
        return valores[clave] ?: ""
    }

    fun escribir(clave: String, valor: String) {
        valores[clave] = valor
    }

    /** El reporte tal como lo espera el servidor. */
    fun comoParametros(): JsonObject {
        val escritos = valores.filterValues { valor -> valor.isNotBlank() }
        return JsonObject(
            mapOf(
                "kind" to JsonPrimitive(clase),
                "attach" to JsonPrimitive(adjuntar),
                "values" to JsonObject(escritos.mapValues { (_, valor) -> JsonPrimitive(valor) }),
                "seen" to JsonArray(vistos.map(::JsonPrimitive)),
                "other_tools" to JsonArray(herramientas.map(::JsonPrimitive)),
            ),
        )
    }
}

@Composable
fun FormularioReporte(bloque: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val borrador = remember { BorradorReporte(bloque.objeto("valores")) }
    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        Column(Modifier.padding(horizontal = 22.dp, vertical = 16.dp), Arrangement.spacedBy(14.dp)) {
            ClaseReporte(borrador)
            if (borrador.clase == PROBLEMA) {
                PartesDelProblema(bloque, borrador, ordenes)
            } else {
                PartesDeLaIdea(borrador)
            }
        }
        Row(
            modifier = Modifier.fillMaxWidth().background(paleta.panelElevado).padding(horizontal = 22.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End),
        ) {
            Boton(t("Cancel"), { ordenes.ir("support") }, alto = 34.dp)
            Boton(t("Send"), { enviar(borrador, bloque, ordenes) }, clase = ClaseBoton.PRINCIPAL, alto = 34.dp)
        }
    }
}

private fun enviar(borrador: BorradorReporte, bloque: JsonObject, ordenes: Ordenes) {
    val obligatorio = if (borrador.clase == PROBLEMA) "summary" else "notes"
    if (borrador.leer(obligatorio).isBlank()) {
        ordenes.avisar(bloque.texto("pista"))
        return
    }
    val mensaje = t("Goes straight to the developer. Only the developer sees it.")
    ordenes.guardarYEjecutar("support.draft", borrador.comoParametros(), "support.send", t("Send"), mensaje)
}

@Composable
private fun ClaseReporte(borrador: BorradorReporte) {
    Row(Modifier.fillMaxWidth()) {
        PestanaReporte(t("Report a problem"), borrador.clase == PROBLEMA, Modifier.weight(1f)) { borrador.clase = PROBLEMA }
        PestanaReporte(t("Suggest an idea"), borrador.clase == IDEA, Modifier.weight(1f)) { borrador.clase = IDEA }
    }
}

@Composable
private fun PestanaReporte(texto: String, elegida: Boolean, modifier: Modifier, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (elegida) paleta.acentoSuave else paleta.panelAlterno
    val borde = if (elegida) paleta.acentoBorde else paleta.borde
    val color = if (elegida) paleta.acento else paleta.apagado
    Box(modifier.height(36.dp).marco(fondo, borde, Medidas.radioChico).pulsable(alPulsar = alPulsar), Alignment.Center) {
        Texto(texto, tamano = 13, peso = 700, color = color)
    }
}

// -- las dos hojas -------------------------------------------------------------------------------------

@Composable
private fun PartesDeLaIdea(borrador: BorradorReporte) {
    Pregunta(t("Suggestions and ideas") + " *") {
        AreaTexto(borrador.leer("notes"), { valor -> borrador.escribir("notes", valor) }, alto = 160)
    }
    PreguntaContacto(borrador)
}

@Composable
private fun PartesDelProblema(bloque: JsonObject, borrador: BorradorReporte, ordenes: Ordenes) {
    Pregunta(t("What went wrong?") + " *") {
        Linea(borrador, "summary", t("Example: \"GPU governor stops after a few seconds\""))
    }
    Pareja(
        { Pregunta(t("Which part of the app?")) { Elegir(bloque, "areas", borrador, "area") } },
        { Pregunta(t("Error code")) { Linea(borrador, "code", "BC250-…") } },
    )
    Pareja(
        { Pregunta(t("How often does it happen?")) { Elegir(bloque, "frecuencias", borrador, "frequency") } },
        { Pregunta(t("Did it work before?")) { Elegir(bloque, "antes", borrador, "worked_before") } },
    )
    Pregunta(t("What did you see?")) {
        Marcas(bloque.objetos("vistos"), borrador.vistos)
    }
    Pregunta(t("Steps to reproduce")) {
        AreaTexto(borrador.leer("steps"), { valor -> borrador.escribir("steps", valor) }, alto = 84)
    }
    Pregunta(t("What did you expect to happen?")) {
        AreaTexto(borrador.leer("expected"), { valor -> borrador.escribir("expected", valor) }, alto = 64)
    }
    HojaSistema(bloque, borrador)
    Hoja(t("Logs")) {
        Pregunta(t("Terminal output")) {
            AreaTexto(borrador.leer("terminal"), { valor -> borrador.escribir("terminal", valor) }, alto = 84)
        }
        Pregunta(t("Screenshot or video link")) { Linea(borrador, "media", "https://…") }
    }
    HojaAutomatica(bloque, borrador, ordenes)
    Hoja(t("Contact and ideas")) {
        PreguntaContacto(borrador)
        Pregunta(t("Suggestions and ideas")) {
            AreaTexto(borrador.leer("notes"), { valor -> borrador.escribir("notes", valor) }, alto = 64)
        }
    }
}

@Composable
private fun HojaSistema(bloque: JsonObject, borrador: BorradorReporte) {
    Hoja(t("Your system")) {
        Texto(t("Filled in from this system. Change anything that is wrong."), tamano = 12, color = ColoresActuales.current.apagado)
        Pareja(
            { Pregunta(t("Distribution")) { Elegir(bloque, "distribuciones", borrador, "distribution") } },
            { Pregunta(t("Control Center version")) { Linea(borrador, "version", "") } },
        )
        Pareja(
            { Pregunta(t("How did you install it?")) { Elegir(bloque, "instalaciones", borrador, "install") } },
            { Pregunta(t("BIOS")) { Elegir(bloque, "bios", borrador, "bios") } },
        )
        Pareja(
            { Pregunta(t("CPU cores")) { Elegir(bloque, "nucleos", borrador, "cores") } },
            { Pregunta(t("GPU compute units")) { Elegir(bloque, "unidades", borrador, "cus") } },
        )
        Pregunta(t("Other BC-250 tools you used on this system")) {
            Marcas(bloque.objetos("herramientas"), borrador.herramientas)
        }
    }
}

@Composable
private fun HojaAutomatica(bloque: JsonObject, borrador: BorradorReporte, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    Hoja(t("Automatic report")) {
        Texto(t("Captured by Control Center. Nothing here needs to be written by you."), tamano = 12, color = paleta.apagado)
        Column(Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.bordeSuave, 5.dp).padding(14.dp), Arrangement.spacedBy(6.dp)) {
            for (dato in bloque.objetos("automatico")) {
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Texto(dato.texto("nombre"), 12, Modifier.width(170.dp), peso = 600, color = paleta.apagado)
                    Texto(dato.texto("valor"), 12, Modifier.weight(1f))
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            Casilla(borrador.adjuntar, { valor -> borrador.adjuntar = valor })
            Texto(t("Send the automatic report"), tamano = 13)
            Spacer(Modifier.weight(1f))
            Boton(t("See what is sent"), {
                ordenes.guardarYEjecutar("support.draft", borrador.comoParametros(), "support.preview", t("See what is sent"), "")
            }, alto = 28.dp, tamano = 12)
        }
        Texto(
            t("Linux may ask for your password once to read the kernel log for this report. If you cancel it, the report is still sent, without that log."),
            tamano = 11,
            color = paleta.sutil,
        )
    }
}

@Composable
private fun PreguntaContacto(borrador: BorradorReporte) {
    Pregunta(t("Telegram or Discord username")) {
        Texto(t("Optional. Only if you want an answer."), tamano = 12, color = ColoresActuales.current.apagado)
        Linea(borrador, "contact", "@name")
    }
}

// -- piezas del formulario ---------------------------------------------------------------------------------

@Composable
private fun Hoja(titulo: String, contenido: @Composable () -> Unit) {
    val paleta = ColoresActuales.current
    Column(
        modifier = Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, 6.dp).padding(horizontal = 17.dp, vertical = 15.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Texto(titulo, tamano = 14, peso = 800)
        contenido()
    }
}

@Composable
private fun Pregunta(titulo: String, contenido: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth(), Arrangement.spacedBy(5.dp)) {
        Texto(titulo, tamano = 13, peso = 700)
        contenido()
    }
}

@Composable
private fun Pareja(primera: @Composable () -> Unit, segunda: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < 520.dp) {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                primera()
                segunda()
            }
        } else {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(14.dp)) {
                Box(Modifier.weight(1f)) { primera() }
                Box(Modifier.weight(1f)) { segunda() }
            }
        }
    }
}

@Composable
private fun Linea(borrador: BorradorReporte, clave: String, ayuda: String) {
    CampoTexto(
        valor = borrador.leer(clave),
        alCambiar = { valor -> borrador.escribir(clave, valor) },
        modifier = Modifier.fillMaxWidth(),
        ayuda = ayuda,
        alto = 36.dp,
    )
}

/** Una lista; «otro» deja escribir la respuesta. */
@Composable
private fun Elegir(bloque: JsonObject, lista: String, borrador: BorradorReporte, clave: String) {
    val otro = bloque.texto("otro")
    val opciones = bloque.objetos(lista).map { opcion -> Eleccion(opcion.texto("valor"), opcion.texto("nombre")) }
    val valor = borrador.leer(clave)
    val conocido = opciones.any { opcion -> opcion.valor == valor }
    var escribiendo by remember { mutableStateOf(valor.isNotEmpty() && !conocido) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Desplegable(
            opciones = opciones,
            elegida = if (escribiendo) otro else valor,
            alElegir = { elegido ->
                escribiendo = elegido == otro
                borrador.escribir(clave, if (elegido == otro) "" else elegido)
            },
            vacio = t("Choose…"),
        )
        if (escribiendo) {
            Linea(borrador, clave, "")
        }
    }
}

@Composable
private fun Marcas(opciones: List<JsonObject>, marcadas: MutableList<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (opcion in opciones) {
            val valor = opcion.texto("valor")
            fun cambiar() {
                if (valor in marcadas) {
                    marcadas.remove(valor)
                } else {
                    marcadas.add(valor)
                }
            }
            Row(
                modifier = Modifier.height(18.dp).pulsable(alPulsar = ::cambiar),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CasillaChica(valor in marcadas, activa = true, alCambiar = ::cambiar)
                Texto(opcion.texto("nombre"), tamano = 13)
            }
        }
    }
}

@Composable
private fun AreaTexto(valor: String, alCambiar: (String) -> Unit, alto: Int) {
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxWidth().height(alto.dp).marco(paleta.control, paleta.borde, Medidas.radioPanel).padding(10.dp)) {
        BasicTextField(
            value = valor,
            onValueChange = alCambiar,
            textStyle = estiloTexto(13),
            cursorBrush = SolidColor(paleta.texto),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
