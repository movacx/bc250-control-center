package org.bc250.controlcenter.datos

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/** Lectores cortos para las respuestas del servidor. Un dato que falta nunca es un error. */
val LectorJson = Json { ignoreUnknownKeys = true }

val ObjetoVacio = JsonObject(emptyMap())

fun leerObjeto(texto: String): JsonObject {
    return try {
        val elemento = LectorJson.parseToJsonElement(texto)
        if (elemento is JsonObject) elemento else ObjetoVacio
    } catch (error: IllegalArgumentException) {
        ObjetoVacio
    }
}

fun JsonObject.objeto(clave: String): JsonObject {
    val valor = this[clave]
    return if (valor is JsonObject) valor else ObjetoVacio
}

fun JsonObject.lista(clave: String): List<JsonElement> {
    val valor = this[clave]
    return if (valor is JsonArray) valor else emptyList()
}

fun JsonObject.objetos(clave: String): List<JsonObject> {
    return lista(clave).filterIsInstance<JsonObject>()
}

fun JsonObject.texto(clave: String, defecto: String = ""): String {
    val valor = this[clave]
    if (valor is JsonPrimitive && valor !is JsonNull) {
        return valor.content
    }
    return defecto
}

fun JsonObject.numero(clave: String): Double? {
    val valor = this[clave]
    return if (valor is JsonPrimitive) valor.doubleOrNull else null
}

fun JsonObject.entero(clave: String, defecto: Int = 0): Int {
    val valor = numero(clave)
    return if (valor == null) defecto else valor.toInt()
}

fun JsonObject.logico(clave: String, defecto: Boolean = false): Boolean {
    val valor = this[clave]
    if (valor is JsonPrimitive) {
        return valor.booleanOrNull ?: defecto
    }
    return defecto
}

fun JsonObject.textos(clave: String): List<String> {
    return lista(clave).filterIsInstance<JsonPrimitive>().map { it.content }
}
