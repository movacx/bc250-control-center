package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
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
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.EstadoSesion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.logo
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.jetbrains.compose.resources.painterResource

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
            Image(painterResource(Res.drawable.logo), contentDescription = null, modifier = Modifier.size(48.dp))
            Texto("BC250 Control Center", tamano = 19, peso = 830)
            when (aplicacion.sesion) {
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
    Texto(t("Enter the access key shown in Remote access on the board."), tamano = 13, color = paleta.apagado)
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
}

@Composable
private fun SinConexion(aplicacion: Aplicacion) {
    Texto(t("No connection"), tamano = 13, color = ColoresActuales.current.naranja)
    Boton(t("Retry"), aplicacion::iniciar, clase = ClaseBoton.PRINCIPAL, modifier = Modifier.fillMaxWidth())
}
