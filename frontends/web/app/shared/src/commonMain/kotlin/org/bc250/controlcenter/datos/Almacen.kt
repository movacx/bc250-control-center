package org.bc250.controlcenter.datos

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/** Si aquí hay que escribir la dirección del equipo; en el navegador es la propia página. */
expect val pideDireccion: Boolean

/** Un dato que se recuerda entre visitas, o vacío. */
expect fun leerGuardado(clave: String): String

expect fun guardarDato(clave: String, valor: String)

const val GUARDADO_DIRECCION = "direccion"
const val GUARDADO_HUELLA = "huella"
private const val BYTES_DE_HUELLA = 32

/** El certificado del equipo: se confirma la primera vez y después tiene que ser siempre el mismo. */
object CertificadoDelEquipo {
    /** La huella que presentó el equipo y que todavía nadie confirmó. */
    var pendiente by mutableStateOf("")

    val confirmada: String get() = leerGuardado(GUARDADO_HUELLA)

    fun confirmar() {
        guardarDato(GUARDADO_HUELLA, pendiente)
        pendiente = ""
    }

    /** La huella que trae el código QR, en Base64; la enseña el propio equipo, así que no hay que compararla. */
    @OptIn(ExperimentalEncodingApi::class)
    fun confiarEn(codigo: String) {
        val bytes = try {
            Base64.UrlSafe.withPadding(Base64.PaddingOption.ABSENT_OPTIONAL).decode(codigo)
        } catch (error: IllegalArgumentException) {
            return
        }
        if (bytes.size == BYTES_DE_HUELLA) {
            val huella = bytes.joinToString(":") { parte -> (parte.toInt() and 0xFF).toString(16).padStart(2, '0').uppercase() }
            guardarDato(GUARDADO_HUELLA, huella)
        }
    }

    fun olvidar() {
        guardarDato(GUARDADO_HUELLA, "")
        pendiente = ""
    }
}

/** Los iconos de la barra del sistema cambian con el tema; lo pone la actividad. */
object BarraDelSistema {
    var alCambiarTema: (Boolean) -> Unit = {}
}

/** Lo que hace el botón Atrás del teléfono; dice si quedó atendido. */
object BotonAtras {
    var atender: () -> Boolean = { false }
}
