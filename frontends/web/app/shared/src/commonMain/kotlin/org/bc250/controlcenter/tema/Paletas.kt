package org.bc250.controlcenter.tema

import androidx.compose.ui.graphics.Color
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.texto

/** Todas las paletas que envió el servidor, por estilo, tema y acento. */
class Paletas(private val datos: JsonObject = ObjetoVacio, val estilo: String = "formal", val tema: String = "dark") {

    /** La paleta completa de una combinación, o nada si el servidor no la envió. */
    fun paleta(estilo: String, tema: String, acento: String): Paleta? {
        val colores = datos.objeto("$estilo/$tema/$acento")
        if (colores.isEmpty()) {
            return null
        }
        val valores = colores.keys.associateWith { clave -> colores.texto(clave) }
        return Paleta(valores, esClaro = tema == "light")
    }

    /** El color de un acento en el tema que se está viendo. */
    fun acento(nombre: String): Color {
        return color(tema, nombre, "blue")
    }

    fun color(tema: String, acento: String, nombre: String): Color {
        val valor = datos.objeto("$estilo/$tema/$acento").texto(nombre)
        return if (valor.isEmpty()) Color.Gray else leerColor(valor)
    }
}
