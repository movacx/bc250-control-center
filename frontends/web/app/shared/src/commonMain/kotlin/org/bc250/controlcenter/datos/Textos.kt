package org.bc250.controlcenter.datos

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Las traducciones: la clave es el texto en inglés, igual que en el escritorio. */
object Textos {
    private var traducciones by mutableStateOf<Map<String, String>>(emptyMap())

    fun cambiar(nuevas: Map<String, String>) {
        traducciones = nuevas
    }

    fun traducir(original: String): String {
        return traducciones[original] ?: original
    }
}

fun t(original: String): String {
    return Textos.traducir(original)
}

/** Un texto con huecos: ``t("{count} samples", "count" to "3")``. */
fun t(original: String, vararg valores: Pair<String, String>): String {
    var texto = Textos.traducir(original)
    for ((nombre, valor) in valores) {
        texto = texto.replace("{$nombre}", valor)
    }
    return texto
}
