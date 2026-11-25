package org.bc250.controlcenter.datos

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.encodeURLParameter
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.JsonObject

/** Lo que contestó el servidor: el código y el contenido ya leído. */
class Respuesta(val codigo: Int, val datos: JsonObject) {
    val correcta: Boolean get() = codigo in 200..299
    val error: String get() = datos.texto("error")
}

/** Un cliente HTTP adecuado para cada plataforma. */
expect fun crearClienteHttp(): HttpClient

/** La dirección del equipo: en el navegador es la propia página. */
expect fun direccionInicial(): String

/** Abre una dirección en el navegador. */
expect fun abrirDireccion(direccion: String)

/** La página que pide la dirección (…/#cpu), o vacío. */
expect fun paginaDeLaDireccion(): String

/** Anota la página en la dirección, para volver a ella al recargar. */
expect fun anotarPagina(pagina: String)

/** Habla con el servidor web del Control Center. */
class Conexion(var direccion: String = direccionInicial()) {
    private val cliente = crearClienteHttp()

    /** El sello que acompaña a cada orden; lo entrega el servidor al entrar. */
    var sello: String = ""
    var idioma: String = "en"

    suspend fun pedir(ruta: String, parametros: Map<String, String> = emptyMap()): Respuesta {
        return try {
            val respuesta = cliente.get(direccion + ruta + consulta(parametros)) {
                header("X-BC250-Language", idioma)
            }
            convertir(respuesta)
        } catch (cancelada: CancellationException) {
            throw cancelada
        } catch (error: Exception) {
            sinConexion()
        }
    }

    suspend fun enviar(ruta: String, datos: JsonObject = ObjetoVacio): Respuesta {
        return try {
            val respuesta = cliente.post(direccion + ruta) {
                header("X-BC250-Language", idioma)
                header("X-CSRF-Token", sello)
                contentType(ContentType.Application.Json)
                setBody(datos.toString())
            }
            convertir(respuesta)
        } catch (cancelada: CancellationException) {
            throw cancelada
        } catch (error: Exception) {
            sinConexion()
        }
    }

    private suspend fun convertir(respuesta: HttpResponse): Respuesta {
        return Respuesta(respuesta.status.value, leerObjeto(respuesta.bodyAsText()))
    }

    private fun sinConexion(): Respuesta {
        return Respuesta(0, ObjetoVacio)
    }

    private fun consulta(parametros: Map<String, String>): String {
        if (parametros.isEmpty()) {
            return ""
        }
        val partes = parametros.map { (clave, valor) -> clave + "=" + valor.encodeURLParameter() }
        return "?" + partes.joinToString("&")
    }
}
