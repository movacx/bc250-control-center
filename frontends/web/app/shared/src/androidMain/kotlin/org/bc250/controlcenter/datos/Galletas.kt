package org.bc250.controlcenter.datos

import io.ktor.client.plugins.cookies.CookiesStorage
import io.ktor.http.Cookie
import io.ktor.http.Url

/** La sesión con el equipo, guardada para no emparejar otra vez al abrir la aplicación. */
internal class GalletasGuardadas : CookiesStorage {

    override suspend fun get(requestUrl: Url): List<Cookie> {
        val (equipo, nombre, valor) = leerGuardado(CLAVE).split("\n").takeIf { partes -> partes.size == PARTES } ?: return emptyList()
        return if (valor.isEmpty() || equipo != requestUrl.host) emptyList() else listOf(Cookie(nombre, valor))
    }

    override suspend fun addCookie(requestUrl: Url, cookie: Cookie) {
        val valor = if (cookie.maxAge == 0) "" else cookie.value
        guardarDato(CLAVE, listOf(requestUrl.host, cookie.name, valor).joinToString("\n"))
    }

    override fun close() {
    }

    private companion object {
        const val CLAVE = "sesion"
        const val PARTES = 3
    }
}
