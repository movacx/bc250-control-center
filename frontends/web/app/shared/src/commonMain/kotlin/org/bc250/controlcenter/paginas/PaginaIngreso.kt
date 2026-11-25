package org.bc250.controlcenter.paginas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.CampoTexto
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Logotipo
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoMono
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.CertificadoDelEquipo
import org.bc250.controlcenter.datos.pideDireccion
import org.bc250.controlcenter.datos.EstadoSesion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** La entrada: pide la clave que muestra el equipo. */
@Composable
fun PaginaIngreso(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            modifier = Modifier
                .padding(16.dp)
                .widthIn(max = 420.dp)
                .fillMaxWidth()
                .marco(paleta.panel, paleta.borde, Medidas.radioTarjeta)
                .padding(28.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Logotipo(48.dp)
            Texto("BC250 Control Center", tamano = 19, peso = 830)
            when (aplicacion.sesion) {
                EstadoSesion.PIDE_DIRECCION -> FormularioDireccion(aplicacion)
                EstadoSesion.PIDE_CONFIANZA -> ConfirmarEquipo(aplicacion)
                EstadoSesion.PIDE_CLAVE -> FormularioClave(aplicacion)
                EstadoSesion.SIN_CONEXION -> SinConexion(aplicacion)
                else -> Texto(t("Connecting…"), tamano = 13, color = paleta.apagado)
            }
        }
    }
}

@Composable
private fun FormularioClave(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    var clave by remember { mutableStateOf("") }
    fun entrar() {
        aplicacion.ingresar(clave)
    }
    Texto(t("Enter the access key shown in Remote access on the desktop application."), tamano = 13, color = paleta.apagado)
    CampoTexto(
        valor = clave,
        alCambiar = { nueva -> clave = nueva },
        ayuda = t("Access key"),
        secreto = true,
        alAceptar = ::entrar,
        modifier = Modifier.fillMaxWidth(),
    )
    if (aplicacion.mensajeIngreso.isNotEmpty()) {
        Texto(aplicacion.mensajeIngreso, tamano = 12, color = paleta.rojo)
    }
    Boton(
        texto = t("Sign in"),
        alPulsar = ::entrar,
        clase = ClaseBoton.PRINCIPAL,
        activo = clave.isNotBlank(),
        alto = 44.dp,
        modifier = Modifier.fillMaxWidth(),
    )
    CambiarEquipo(aplicacion)
}

@Composable
private fun SinConexion(aplicacion: Aplicacion) {
    Texto(t("Not connected"), tamano = 13, color = ColoresActuales.current.naranja)
    Boton(t("Retry"), aplicacion::iniciar, clase = ClaseBoton.PRINCIPAL, alto = 46.dp, modifier = Modifier.fillMaxWidth())
    CambiarEquipo(aplicacion)
}

/** En la aplicación del teléfono se puede apuntar a otro equipo. */
@Composable
private fun CambiarEquipo(aplicacion: Aplicacion) {
    if (pideDireccion) {
        Boton(t("Change address"), aplicacion::cambiarDireccion, alto = 46.dp, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun FormularioDireccion(aplicacion: Aplicacion) {
    var direccion by remember { mutableStateOf(aplicacion.conexion.direccion) }
    fun conectar() {
        aplicacion.conectar(direccion)
    }
    Texto(
        t("Enter the address shown in Remote access, or paste the link of its QR code."),
        tamano = 13,
        color = ColoresActuales.current.apagado,
    )
    CampoTexto(
        valor = direccion,
        alCambiar = { nueva -> direccion = nueva },
        ayuda = "https://192.168.0.10:8250",
        alAceptar = ::conectar,
        alto = 46.dp,
        modifier = Modifier.fillMaxWidth(),
    )
    Boton(
        texto = t("Connect"),
        alPulsar = ::conectar,
        clase = ClaseBoton.PRINCIPAL,
        activo = direccion.isNotBlank(),
        alto = 46.dp,
        modifier = Modifier.fillMaxWidth(),
    )
}

/** La primera vez se compara la huella del certificado con la que enseña el equipo. */
@Composable
private fun ConfirmarEquipo(aplicacion: Aplicacion) {
    val cambio = CertificadoDelEquipo.confirmada.isNotEmpty()
    val aviso = if (cambio) {
        "The board shows a different certificate than before. Continue only if you reinstalled it."
    } else {
        "This phone has not used this board before. Continue only if you typed its address yourself and you are on your own network."
    }
    Texto(t(aviso), tamano = 13, color = if (cambio) ColoresActuales.current.naranja else ColoresActuales.current.apagado)
    TextoMono(CertificadoDelEquipo.pendiente, tamano = 13, color = ColoresActuales.current.texto, lineas = 5)
    Boton(
        texto = t("It is my board"),
        alPulsar = aplicacion::confiar,
        clase = if (cambio) ClaseBoton.PELIGRO else ClaseBoton.PRINCIPAL,
        alto = 46.dp,
        modifier = Modifier.fillMaxWidth(),
    )
    CambiarEquipo(aplicacion)
}
