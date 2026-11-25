package org.bc250.controlcenter.componentes

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto

/** Un texto que se lee en su propia ventana. */
class TextoAbierto(val titulo: String, val contenido: String)

/**
 * Cumple las órdenes que el servidor pone en los botones de una sección.
 * Cada clase de orden hace una sola cosa; una desconocida no hace nada.
 */
class Ordenes(
    private val aplicacion: Aplicacion,
    private val alPortapapeles: (String) -> Unit,
    private val irASeccion: (String, Map<String, String>) -> Unit,
    private val recargar: () -> Unit,
    private val abrirTexto: (TextoAbierto) -> Unit,
) {
    fun cumplir(orden: JsonObject) {
        when (orden.texto("orden")) {
            "accion" -> pedirAccion(orden)
            "ajuste" -> pedirAjuste(orden)
            "seccion" -> irASeccion(orden.texto("nombre"), parametrosDeSeccion(orden))
            "enlace" -> aplicacion.abrirEnlace(orden.texto("nombre"))
            "copiar" -> copiar(orden.texto("mensaje"))
            "texto" -> abrirTexto(TextoAbierto(orden.texto("titulo"), orden.texto("mensaje")))
            "actualizar" -> aplicacion.abrirActualizacion()
            "recorrido" -> aplicacion.empezarRecorrido()
            "recargar" -> recargar()
        }
    }

    fun guardar(clave: String, valor: kotlinx.serialization.json.JsonElement) {
        aplicacion.guardarPreferencia(clave, valor, recargar)
    }

    /** Un interruptor que avisa de un riesgo antes de encenderse. */
    fun preguntarYGuardar(titulo: String, mensaje: String, clave: String) {
        aplicacion.preguntar(titulo, mensaje, peligro = true) {
            guardar(clave, kotlinx.serialization.json.JsonPrimitive(true))
        }
    }

    /** Guarda lo que la acción va a leer y luego la pide; sin mensaje, no pregunta. */
    fun guardarYEjecutar(ajuste: String, datos: JsonObject, accion: String, titulo: String, mensaje: String) {
        aplicacion.guardarYEjecutar(ajuste, datos, accion, titulo, mensaje)
    }

    fun avisar(texto: String) {
        aplicacion.avisar(texto, error = true)
    }

    fun ir(seccion: String, parametros: Map<String, String> = emptyMap()) {
        irASeccion(seccion, parametros)
    }

    private fun pedirAccion(orden: JsonObject) {
        aplicacion.preguntarYEjecutar(
            accion = orden.texto("nombre"),
            titulo = orden.texto("titulo"),
            mensaje = orden.texto("mensaje"),
            parametros = orden.objeto("parametros"),
            peligro = orden.logico("peligro"),
        )
    }

    private fun pedirAjuste(orden: JsonObject) {
        val mensaje = orden.texto("mensaje")
        if (mensaje.isEmpty()) {
            aplicacion.guardarYLuego(orden.texto("nombre"), orden.objeto("parametros"), recargar)
            return
        }
        aplicacion.preguntar(orden.texto("titulo"), mensaje, peligro = true) {
            aplicacion.guardarYLuego(orden.texto("nombre"), orden.objeto("parametros"), recargar)
        }
    }

    fun copiar(contenido: String) {
        alPortapapeles(contenido)
        aplicacion.avisar(t("Copied"))
    }

    private fun parametrosDeSeccion(orden: JsonObject): Map<String, String> {
        val identificador = orden.texto("id")
        return if (identificador.isEmpty()) emptyMap() else mapOf("id" to identificador)
    }
}

/** Las órdenes de una sección, con su ventana de texto ya puesta. */
@Composable
fun recordarOrdenes(
    aplicacion: Aplicacion,
    irASeccion: (String, Map<String, String>) -> Unit,
    recargar: () -> Unit,
): Ordenes {
    val portapapeles = LocalClipboardManager.current
    fun copiar(texto: String) {
        portapapeles.setText(AnnotatedString(texto))
    }
    fun abrir(texto: TextoAbierto) {
        aplicacion.textoAbierto = texto
    }
    return Ordenes(aplicacion, ::copiar, irASeccion, recargar, ::abrir)
}

/** La ventana donde se lee un texto largo. */
@Composable
fun DialogoTexto(texto: TextoAbierto, alCerrar: () -> Unit) {
    Dialogo(alCerrar, ancho = androidx.compose.ui.unit.Dp(760f)) {
        Texto(texto.titulo, tamano = 17, peso = 800)
        TextoConsola(texto.contenido, androidx.compose.ui.Modifier)
        Boton(t("Close"), alCerrar)
    }
}
