package org.bc250.controlcenter.movil

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Ordenes
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto

private val GruposConfiguracion = listOf(
    "Interface" to listOf(
        Triple("general", "General", "Language, startup and help"),
        Triple("appearance", "Appearance", "Theme, accent and density"),
        Triple("console", "Terminal and controls", "Console and gamepad"),
    ),
    "Hardware" to listOf(
        Triple("hardware", "GPU governor", "Governor selection"),
        Triple("telemetry", "Telemetry", "Sensors and daemon"),
    ),
    "Application" to listOf(
        Triple("support", "Support", "Reports and known errors"),
        Triple("about", "About", "Version and repositories"),
    ),
)

@Composable
fun PaginaConfiguracionMovil(aplicacion: Aplicacion) {
    val movil = movil()
    var seccion by remember { mutableStateOf("") }
    var parametros by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var revision by remember { mutableIntStateOf(0) }
    var datos by remember { mutableStateOf(ObjetoVacio) }
    fun ir(nueva: String, nuevos: Map<String, String>) {
        if (nueva.isEmpty()) parametros = parametros + nuevos
        else {
            seccion = nueva
            parametros = nuevos
            datos = ObjetoVacio
            val nombre = GruposConfiguracion.flatMap { it.second }.firstOrNull { it.first == nueva }?.second
            movil.abrirDetalle(t(nombre ?: "Settings"))
        }
    }
    LaunchedEffect(aplicacion.seccionAjustes) {
        // El marco cierra los detalles al cambiar la sección externa; abrir después conserva el destino solicitado.
        yield()
        val pedida = aplicacion.seccionAjustes
        if (pedida.isNotEmpty() && pedida != "general") ir(pedida, emptyMap())
    }
    val enDetalle = movil.detalle.isNotEmpty()
    LaunchedEffect(seccion, parametros, revision, aplicacion.revisionDeTextos, aplicacion.trabajo.terminado, enDetalle) {
        if (enDetalle && seccion.isNotEmpty()) {
            datos = aplicacion.consultar("settings", parametros + mapOf("section" to seccion))
        }
    }
    LaunchedEffect(datos.texto("titulo"), enDetalle) {
        if (enDetalle && datos.texto("titulo").isNotEmpty()) movil.abrirDetalle(datos.texto("titulo"))
    }
    val portapapeles = LocalClipboardManager.current
    val ordenes = Ordenes(aplicacion, { portapapeles.setText(AnnotatedString(it)) }, ::ir, { revision += 1 }) { texto ->
        movil.abrirHoja {
            TituloHoja(texto.titulo)
            TextoHoja(texto.contenido)
            CerrarHoja()
        }
    }
    PaginaMovil("settings") {
        if (!enDetalle) {
            for ((titulo, secciones) in GruposConfiguracion) {
                SeccionMovil(t(titulo)) {
                    GrupoMovil {
                        for ((clave, nombre) in secciones) {
                            FilaAbrir(t(nombre)) { ir(clave, emptyMap()) }
                        }
                    }
                }
            }
        } else {
            val vuelta = datos.objeto("vuelta")
            if (vuelta.isNotEmpty()) {
                EnlaceMovil("‹ " + vuelta.texto("texto")) { ir(vuelta.texto("seccion"), emptyMap()) }
            }
            EstadoLecturaMovil(datos)
            val bloques = datos.objetos("bloques")
            when (seccion) {
                "appearance" -> AparienciaMovil(bloques, ordenes, aplicacion)
                "general" -> GeneralMovil(bloques, ordenes, aplicacion)
                else -> BloquesMovil(bloques, ordenes, aplicacion)
            }
        }
    }
}

@Composable
private fun AparienciaMovil(bloques: List<JsonObject>, ordenes: Ordenes, aplicacion: Aplicacion) {
    val filas = bloques.flatMap { it.objetos("bloques") }
    val finales = mutableListOf<JsonObject>()
    for (fila in filas) {
        val control = fila.objeto("control")
        val clave = control.texto("clave")
        if (clave == "scale" || clave == "gpu_interface") {
            finales += if (clave == "gpu_interface") {
                JsonObject(fila + ("control" to JsonObject(control + ("tipo" to JsonPrimitive("lista")))))
            } else fila
        } else {
            val titulo = if (fila.texto("tipo") == "temas") t("Theme") else fila.texto("titulo")
            SeccionMovil(titulo) {
                BloquesMovil(listOf(fila), ordenes, aplicacion)
            }
        }
    }
    GrupoMovil { FilasDeGrupo(finales, ordenes, aplicacion) }
}

@Composable
private fun GeneralMovil(bloques: List<JsonObject>, ordenes: Ordenes, aplicacion: Aplicacion) {
    for ((indice, grupo) in bloques.withIndex()) {
        val filas = grupo.objetos("bloques")
        val visibles = when (indice) {
            1 -> filas.filter { it.objeto("control").texto("clave") != "sidebar_collapsed" }
            2 -> {
                val interruptores = filas.filter { it.objeto("control").texto("tipo") == "interruptor" }
                val botones = filas.flatMap { it.objeto("control").objetos("botones") }
                interruptores + JsonObject(mapOf("tipo" to JsonPrimitive("botones"), "botones" to JsonArray(botones)))
            }
            else -> filas
        }
        if (indice == 0) GrupoMovil { FilasDeGrupo(visibles, ordenes, aplicacion) }
        else {
            val titulo = grupo.texto("titulo")
            SeccionMovil(titulo) { GrupoMovil { FilasDeGrupo(visibles, ordenes, aplicacion) } }
        }
    }
}
