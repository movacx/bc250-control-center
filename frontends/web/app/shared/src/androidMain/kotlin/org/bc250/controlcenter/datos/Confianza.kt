package org.bc250.controlcenter.datos

import java.security.GeneralSecurityException
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.X509TrustManager

/**
 * El equipo usa su propia autoridad de certificados, que ningún teléfono conoce. La primera vez se enseña su
 * huella para compararla con la de Acceso remoto; después solo se acepta la que se confirmó.
 */
internal class ConfianzaDelEquipo : X509TrustManager {

    override fun checkServerTrusted(cadena: Array<out X509Certificate>, tipo: String?) {
        val hoja = cadena.first()
        val autoridad = cadena.last()
        try {
            hoja.checkValidity()
            if (cadena.size > 1) {
                hoja.verify(autoridad.publicKey)
            }
        } catch (error: GeneralSecurityException) {
            throw CertificateException(error)
        }
        val huella = huellaDe(autoridad)
        if (huella != CertificadoDelEquipo.confirmada) {
            CertificadoDelEquipo.pendiente = huella
            throw CertificateException("The certificate of the board is not confirmed")
        }
    }

    override fun checkClientTrusted(cadena: Array<out X509Certificate>?, tipo: String?) {
        throw CertificateException("Only servers are checked")
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> {
        return emptyArray()
    }

    private fun huellaDe(certificado: X509Certificate): String {
        val suma = MessageDigest.getInstance("SHA-256").digest(certificado.encoded)
        return suma.joinToString(":") { parte -> "%02X".format(parte) }
    }
}
