package org.bc250.controlcenter.componentes

import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.input.pointer.PointerIcon
import androidx.compose.ui.input.pointer.pointerHoverIcon
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.logo
import org.jetbrains.compose.resources.DrawableResource
import org.jetbrains.compose.resources.imageResource
import org.jetbrains.compose.resources.painterResource

/** Las clases de botón que existen en el escritorio. */
enum class ClaseBoton { PRINCIPAL, NORMAL, PELIGRO, EXITO, COMPACTO, ACENTO }

private class ColoresBoton(val fondo: Color, val borde: Color, val texto: Color)

@Composable
private fun coloresDe(clase: ClaseBoton, activo: Boolean, encima: Boolean): ColoresBoton {
    val paleta = ColoresActuales.current
    if (!activo) {
        return ColoresBoton(paleta.fondoInactivo, paleta.fondoInactivo, paleta.textoInactivo)
    }
    return when (clase) {
        ClaseBoton.PRINCIPAL -> {
            val fondo = if (encima) paleta.acentoEncima else paleta.acento
            ColoresBoton(fondo, fondo, paleta.sobreAcento)
        }
        ClaseBoton.PELIGRO -> ColoresBoton(paleta.peligroSolido, paleta.peligroSolido, Color.White)
        ClaseBoton.EXITO -> ColoresBoton(paleta.exitoSolido, paleta.exitoSolido, Color.White)
        ClaseBoton.NORMAL -> {
            val fondo = if (encima) paleta.controlEncima else paleta.panelAlterno
            val borde = if (encima) paleta.bordeFuerte else paleta.borde
            ColoresBoton(fondo, borde, paleta.texto)
        }
        ClaseBoton.ACENTO -> {
            val fondo = if (encima) paleta.controlEncima else paleta.panelAlterno
            ColoresBoton(fondo, paleta.acentoBorde, paleta.acento)
        }
        ClaseBoton.COMPACTO -> {
            val fondo = if (encima) paleta.controlEncima else paleta.panelElevado
            ColoresBoton(fondo, paleta.borde, paleta.apagado)
        }
    }
}

/** Hace de cualquier zona un botón: clic, teclado y la mano del cursor. */
@Composable
fun Modifier.pulsable(activo: Boolean = true, fuente: MutableInteractionSource? = null, alPulsar: () -> Unit): Modifier {
    val interaccion = fuente ?: remember { MutableInteractionSource() }
    val cursor = if (activo) PointerIcon.Hand else PointerIcon.Default
    return this
        .hoverable(interaccion, enabled = activo)
        .pointerHoverIcon(cursor)
        .clickable(
            interactionSource = interaccion,
            indication = null,
            enabled = activo,
            role = Role.Button,
            onClick = alPulsar,
        )
}

@Composable
fun Boton(
    texto: String,
    alPulsar: () -> Unit,
    modifier: Modifier = Modifier,
    clase: ClaseBoton = ClaseBoton.NORMAL,
    activo: Boolean = true,
    alto: Dp = 38.dp,
    tamano: Int = 13,
    peso: Int = 720,
    icono: DrawableResource? = null,
) {
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val colores = coloresDe(clase, activo, encima)
    val radio = if (clase == ClaseBoton.PRINCIPAL) Medidas.radioPanel else Medidas.radioBoton
    Row(
        modifier = modifier
            .height(alto)
            .marco(colores.fondo, colores.borde, radio)
            .pulsable(activo, interaccion, alPulsar)
            .padding(horizontal = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icono != null) {
            Icono(icono, tamano = 14.dp)
        }
        Texto(texto, tamano = tamano, peso = peso, color = colores.texto, alineado = TextAlign.Center)
    }
}

/** Un botón cuadrado con solo un icono. */
@Composable
fun BotonIcono(
    icono: DrawableResource,
    alPulsar: () -> Unit,
    modifier: Modifier = Modifier,
    lado: Dp = 24.dp,
    tamano: Dp = 16.dp,
    conMarco: Boolean = true,
    color: Color? = null,
) {
    val paleta = ColoresActuales.current
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    var caja = modifier.size(lado)
    if (conMarco) {
        val fondo = if (encima) paleta.controlEncima else paleta.control
        val borde = if (encima) paleta.acentoBorde else paleta.bordeSuave
        caja = caja.marco(fondo, borde, Medidas.radioChico)
    }
    Box(caja.pulsable(true, interaccion, alPulsar), contentAlignment = Alignment.Center) {
        Icono(icono, tamano, color)
    }
}

@Composable
fun Icono(icono: DrawableResource, tamano: Dp, color: Color? = null, modifier: Modifier = Modifier) {
    val filtro = if (color == null) null else ColorFilter.tint(color)
    Image(
        painter = painterResource(icono),
        contentDescription = null,
        modifier = modifier.size(tamano),
        colorFilter = filtro,
    )
}

/** El logotipo de la aplicación. */
@Composable
fun Logotipo(lado: Dp) {
    Image(
        bitmap = imageResource(Res.drawable.logo),
        contentDescription = null,
        modifier = Modifier.size(lado),
        filterQuality = FilterQuality.High,
    )
}
