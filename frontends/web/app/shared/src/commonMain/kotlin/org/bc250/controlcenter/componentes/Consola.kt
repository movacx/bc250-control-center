package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.Trabajo
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

/** El texto de una consola, con la letra y los colores del escritorio. */
@Composable
fun TextoConsola(texto: String, modifier: Modifier = Modifier, color: androidx.compose.ui.graphics.Color? = null) {
    val paleta = ColoresActuales.current
    val desplazador = rememberScrollState()
    LaunchedEffect(texto) {
        desplazador.scrollTo(desplazador.maxValue)
    }
    Box(
        modifier = modifier
            .marco(paleta.color("console_bg"), paleta.color("console_border"), Medidas.radioPanel)
            .padding(horizontal = 15.dp, vertical = 14.dp),
    ) {
        SelectionContainer {
            BasicText(
                text = texto,
                style = estiloTexto(11, 400, color ?: paleta.color("console_text"), deConsola = true),
                modifier = Modifier.verticalScroll(desplazador),
            )
        }
    }
}

/** El panel que sube desde abajo mientras corre una operación. */
@Composable
fun PanelConsola(aplicacion: Aplicacion, modifier: Modifier = Modifier) {
    val paleta = ColoresActuales.current
    val trabajo = aplicacion.trabajo
    Column(
        modifier = modifier
            .fillMaxWidth()
            .height(280.dp)
            .marco(paleta.panel, paleta.borde, Medidas.radioBarra)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        EncabezadoConsola(aplicacion, trabajo)
        TextoConsola(trabajo.texto, Modifier.fillMaxWidth().weight(1f))
        if (trabajo.esperaClave || trabajo.esperaRespuesta) {
            RespuestaConsola(aplicacion, trabajo)
        }
    }
}

@Composable
private fun EncabezadoConsola(aplicacion: Aplicacion, trabajo: Trabajo) {
    val paleta = ColoresActuales.current
    val estado = when {
        !trabajo.terminado -> t("Running")
        trabajo.correcto -> t("Completed")
        trabajo.cancelado -> t("Cancelled.")
        else -> t("Failed")
    }
    val color = when {
        !trabajo.terminado -> paleta.acento
        trabajo.correcto -> paleta.verde
        trabajo.cancelado -> paleta.apagado
        else -> paleta.rojo
    }
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
        Texto(trabajo.titulo, tamano = 13, peso = 760, lineas = 1)
        Texto(estado, tamano = 12, peso = 700, color = color)
        Box(Modifier.weight(1f))
        if (!trabajo.terminado) {
            Boton(t("Stop"), aplicacion::interrumpirTrabajo, clase = ClaseBoton.PELIGRO, alto = 30.dp, tamano = 12)
        }
        Boton(t("Hide"), { aplicacion.consolaVisible = false }, alto = 30.dp, tamano = 12)
    }
}

@Composable
private fun RespuestaConsola(aplicacion: Aplicacion, trabajo: Trabajo) {
    var respuesta by remember(trabajo.id, trabajo.esperaClave) { mutableStateOf("") }
    fun enviar() {
        aplicacion.responderTrabajo(respuesta)
        respuesta = ""
    }
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
        CampoTexto(
            valor = respuesta,
            alCambiar = { nuevo -> respuesta = nuevo },
            secreto = trabajo.esperaClave,
            ayuda = if (trabajo.esperaClave) t("Linux password") else t("Send"),
            alAceptar = ::enviar,
            modifier = Modifier.weight(1f),
        )
        Boton(t("Send"), ::enviar, clase = ClaseBoton.PRINCIPAL, alto = 40.dp)
    }
}
