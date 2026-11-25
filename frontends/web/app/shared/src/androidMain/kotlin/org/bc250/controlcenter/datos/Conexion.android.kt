package org.bc250.controlcenter.datos

import android.os.Build
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.UserAgent
import io.ktor.client.plugins.cookies.HttpCookies
import javax.net.ssl.SSLContext

actual fun crearClienteHttp(): HttpClient {
    return HttpClient(OkHttp) {
        engine {
            config {
                val confianza = ConfianzaDelEquipo()
                val contexto = SSLContext.getInstance("TLS")
                contexto.init(null, arrayOf(confianza), null)
                sslSocketFactory(contexto.socketFactory, confianza)
                // La autoridad confirmada ya identifica al equipo; su dirección en la red de casa cambia.
                hostnameVerifier { _, _ -> true }
            }
        }
        install(HttpCookies) {
            storage = GalletasGuardadas()
        }
        install(UserAgent) {
            agent = "BC250 Control Center (Android ${Build.VERSION.RELEASE}; ${Build.MODEL})"
        }
        install(HttpTimeout) {
            connectTimeoutMillis = 8_000
            requestTimeoutMillis = 30_000
        }
    }
}

/** La última dirección que se usó. */
actual fun direccionInicial(): String {
    return leerGuardado(GUARDADO_DIRECCION)
}

/** Quien inicia la aplicación dice cómo se abre una dirección. */
var abridorDeDirecciones: (String) -> Unit = {}

actual fun abrirDireccion(direccion: String) {
    abridorDeDirecciones(direccion)
}

actual fun paginaDeLaDireccion(): String {
    return ""
}

actual fun anotarPagina(pagina: String) {
}
