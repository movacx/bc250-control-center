package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales

@Composable
internal fun MenuVentiladores(aplicacion: Aplicacion, datos: JsonObject, numero: Int, borrador: JsonObject,
    perfil: String, alCerrar: () -> Unit) {
    var vista by remember { mutableStateOf("menu") }
    var documento by remember { mutableStateOf("") }
    var rutas by remember { mutableStateOf(ObjetoVacio) }
    var rutaElegida by remember { mutableStateOf("detected") }
    var descarga by remember { mutableStateOf("") }
    var titulo by remember { mutableStateOf("") }
    var nombre by remember { mutableStateOf(perfil) }
    var reemplazar by remember { mutableStateOf(false) }
    val tareas = rememberCoroutineScope()
    val disponible = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    if (vista == "paths") {
        Dialogo({ vista = "menu" }, ancho = 850.dp) {
            TituloPanel(t("PWM paths"))
            PestanasSupervision(rutas.objetos("tabs").map { Eleccion(it.texto("key"), it.texto("label")) }, rutaElegida) { rutaElegida = it }
            val texto = rutas.objetos("tabs").firstOrNull { it.texto("key") == rutaElegida }?.texto("text") ?: t("Loading")
            androidx.compose.foundation.text.selection.SelectionContainer {
                Column(Modifier.heightIn(max = 450.dp).verticalScroll(rememberScrollState())) { Texto(texto, 12) }
            }
            AccionSupervision(t("Close")) { vista = "menu" }
        }
        return
    }
    if (vista == "documento") {
        DocumentoSupervision(titulo, documento, descarga) { vista = "menu" }
        return
    }
    Dialogo(alCerrar, ancho = 600.dp) {
        TituloPanel(t(if (vista == "import") "Import fan profiles" else if (vista == "save") "Save profile as…" else "More"))
        Column(Modifier.fillMaxWidth().heightIn(max = 540.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when (vista) {
                "save" -> {
                    CampoTexto(nombre, { nombre = it.take(32) }, ayuda = t("Name"))
                    CasillaSupervision(t("Replace fan profile?"), reemplazar) { reemplazar = it }
                    AccionSupervision(t("Save as…"), disponible && nombre.isNotBlank() && !datos.logico("external")) {
                        val parametros = mutableMapOf<String, JsonElement>("operation" to JsonPrimitive("save"),
                            "name" to JsonPrimitive(nombre), "replace" to JsonPrimitive(reemplazar))
                        if (borrador.isNotEmpty() && numero > 0) parametros["draft"] = buildJsonObject {
                            put("pwm", JsonPrimitive(numero)); put("entry", borrador)
                        }
                        aplicacion.preguntarYEjecutar("fan.profile", t("Save profile as…"), parametros = parametros)
                        alCerrar()
                    }
                }
                "import" -> {
                    BasicTextField(documento, { documento = it }, Modifier.fillMaxWidth().height(260.dp)
                        .marco(ColoresActuales.current.control, ColoresActuales.current.borde, 6.dp).padding(8.dp),
                        textStyle = estiloTexto(12, 400, ColoresActuales.current.texto))
                    CasillaSupervision(t("Replace fan profile?"), reemplazar) { reemplazar = it }
                    AccionSupervision(t("Import fan profiles"), disponible && documento.isNotBlank()) {
                        aplicacion.guardar("fans.import", mapOf("text" to JsonPrimitive(documento), "replace" to JsonPrimitive(reemplazar)), "fans")
                        alCerrar()
                    }
                }
                else -> {
                    AccionSupervision(t("Save profile as…"), disponible && !datos.logico("external")) { vista = "save" }
                    AccionSupervision(t("Delete profile"), disponible && perfil in datos.objeto("profiles").textos("saved")) {
                        aplicacion.preguntarYEjecutar("fan.profile", t("Delete profile"), parametros = mapOf(
                            "operation" to JsonPrimitive("delete"), "name" to JsonPrimitive(perfil)))
                        alCerrar()
                    }
                    LineaDivisoria()
                    for ((clave, etiqueta) in listOf("export" to "Export fan profiles", "paths" to "PWM paths", "status" to "NCT fan controller status")) {
                        AccionSupervision(t(etiqueta)) {
                            descarga = if (clave == "export") aplicacion.conexion.direccion + "/api/query?name=supervision.download&file=fans" else ""
                            titulo = t(etiqueta)
                            documento = t("Loading")
                            vista = if (clave == "paths") "paths" else "documento"
                            tareas.launch {
                                val respuesta = aplicacion.consultar("fans.diagnostics", mapOf("view" to clave))
                                rutas = respuesta
                                documento = respuesta.texto("text", t("No results"))
                            }
                        }
                    }
                    AccionSupervision(t("Import fan profiles"), disponible) { documento = ""; vista = "import" }
                    AccionSupervision(t("Export to Decky"), disponible) {
                        herramientaVentilador(aplicacion, "decky", "Export to Decky")
                        alCerrar()
                    }
                    TituloPanel(t("Diagnostics"))
                    for ((clave, etiqueta) in listOf("prepare" to "Prepare PWM driver", "readonly" to "Enable read-only NCT monitoring", "disable" to "Disable nct6687 PWM setup")) {
                        AccionSupervision(t(etiqueta), disponible) {
                            herramientaVentilador(aplicacion, clave, etiqueta)
                            alCerrar()
                        }
                    }
                    LineaDivisoria()
                    val externo = datos.logico("external")
                    val etiqueta = if (externo) "Take control back" else "Hand off the fan"
                    AccionSupervision(t(etiqueta), disponible) {
                        herramientaVentilador(aplicacion, "handoff", etiqueta, mapOf("enabled" to JsonPrimitive(!externo)))
                        alCerrar()
                    }
                }
            }
        }
        if (vista != "menu") AccionSupervision(t("Back")) { vista = "menu" }
        AccionSupervision(t("Close"), alPulsar = alCerrar)
    }
}
