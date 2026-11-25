package org.bc250.controlcenter.movil

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.border
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.estiloTexto
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.Trabajo
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.tema.ColoresActuales

private const val AVISO_DE_SUDO = "BC250 Linux password:"

/** Lo que tarda sudo en contestar a una contraseña equivocada, con margen. */
private const val ESPERA_RESPUESTA = 3200L
private const val ESPERA_DE_ENTRADA = 260L

/** La contraseña que pide una operación: cuándo se enseña, si ya se envió y cuántas veces falló. */
class PeticionDeClave {
    var enviada by mutableStateOf(false)
    var fallos by mutableIntStateOf(0)
    var abierta by mutableStateOf(false)
}

/** Abre la ventana cuando la operación pide la contraseña y la cierra en cuanto el equipo la acepta. */
@Composable
fun VigilanteDeClave(aplicacion: Aplicacion): PeticionDeClave {
    val movil = movil()
    val trabajo = aplicacion.trabajo
    val peticion = remember { PeticionDeClave() }
    LaunchedEffect(trabajo.id) {
        peticion.enviada = false
        peticion.fallos = 0
    }
    LaunchedEffect(trabajo.id, trabajo.esperaClave) {
        if (trabajo.esperaClave) {
            if (peticion.enviada) {
                peticion.fallos += 1
                peticion.enviada = false
            }
            movil.abrirClave(aplicacion, peticion)
        } else if (peticion.enviada) {
            delay(ESPERA_RESPUESTA)
            movil.cerrarClave(peticion)
        }
    }
    val aceptada = peticion.enviada && !trabajo.esperaClave && contesto(trabajo)
    LaunchedEffect(aceptada, trabajo.terminado) {
        if (aceptada || trabajo.terminado) {
            movil.cerrarClave(peticion)
        }
    }
    return peticion
}

/** Si después del aviso de sudo ya se escribió algo más: la contraseña valió. */
private fun contesto(trabajo: Trabajo): Boolean {
    return trabajo.terminado || trabajo.texto.substringAfterLast(AVISO_DE_SUDO, "").isNotBlank()
}

fun EstadoMovil.abrirClave(aplicacion: Aplicacion, peticion: PeticionDeClave) {
    if (peticion.abierta) {
        return
    }
    peticion.abierta = true
    abrirHoja(alCerrar = { peticion.abierta = false }) { HojaDeClave(aplicacion, peticion) }
}

private fun EstadoMovil.cerrarClave(peticion: PeticionDeClave) {
    if (peticion.abierta) {
        cerrarHoja()
    }
}

@Composable
private fun HojaDeClave(aplicacion: Aplicacion, peticion: PeticionDeClave) {
    val paleta = ColoresActuales.current
    val movil = movil()
    var clave by remember { mutableStateOf("") }
    val foco = remember { FocusRequester() }
    LaunchedEffect(peticion.fallos) {
        delay(ESPERA_DE_ENTRADA)
        foco.requestFocus()
    }
    fun enviar() {
        if (clave.isNotEmpty() && !peticion.enviada) {
            peticion.enviada = true
            aplicacion.responderTrabajo(clave)
            clave = ""
        }
    }
    Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp), Arrangement.spacedBy(16.dp)) {
        Column(Modifier.fillMaxWidth().padding(top = 4.dp), Arrangement.spacedBy(4.dp)) {
            TextoTitulo(t("Enter your Linux password"), 24)
            Texto(aplicacion.trabajo.titulo, tamano = 15, color = paleta.apagado)
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            CampoDeClave(clave, peticion, foco, ::enviar) { nueva -> clave = nueva }
            val fallo = peticion.fallos > 0 && !peticion.enviada
            Texto(
                texto = t(if (fallo) "That password is not right. Try again." else "The password goes straight to the board and is not saved."),
                tamano = 13,
                color = if (fallo) paleta.rojo else paleta.sutil,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(10.dp)) {
            BotonMovil(t("Cancel"), Modifier.weight(1f)) {
                aplicacion.interrumpirTrabajo()
                movil.cerrarHoja()
            }
            if (peticion.enviada) {
                Row(
                    modifier = Modifier.weight(1.6f).height(50.dp).background(paleta.panelElevado, RoundedCornerShape(10.dp)),
                    horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Giro()
                    Texto(t("Checking…"), tamano = 15, peso = 700)
                }
            } else {
                BotonMovil(t("Continue"), Modifier.weight(1.6f), ClaseBoton.PRINCIPAL, clave.isNotEmpty()) { enviar() }
            }
        }
        Box(Modifier.fillMaxWidth().height(40.dp).pulsable {
            movil.cerrarHoja()
            aplicacion.abrirAjustes("general")
        }, Alignment.Center) {
            Texto(t("Stop asking for it"), tamano = 14, peso = 500, color = paleta.acento, alineado = TextAlign.Center)
        }
    }
}

@Composable
private fun CampoDeClave(clave: String, peticion: PeticionDeClave, foco: FocusRequester, alAceptar: () -> Unit, alCambiar: (String) -> Unit) {
    val paleta = ColoresActuales.current
    var visible by remember { mutableStateOf(false) }
    val interaccion = remember { MutableInteractionSource() }
    val enfocado by interaccion.collectIsFocusedAsState()
    val borde by animateColorAsState(
        when {
            peticion.fallos > 0 && !peticion.enviada -> paleta.rojo
            enfocado -> paleta.acento
            else -> paleta.borde
        },
    )
    val forma = RoundedCornerShape(14.dp)
    Row(
        modifier = Modifier.fillMaxWidth().height(58.dp).background(paleta.control, forma).border(2.dp, borde, forma).padding(start = 18.dp, end = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.weight(1f), Alignment.CenterStart) {
            if (clave.isEmpty()) {
                Texto(t("Password"), tamano = 16, color = paleta.sutil, lineas = 1)
            }
            BasicTextField(
                value = clave,
                onValueChange = alCambiar,
                enabled = !peticion.enviada,
                singleLine = true,
                textStyle = estiloTexto(17, 500),
                cursorBrush = SolidColor(paleta.acento),
                interactionSource = interaccion,
                visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { alAceptar() }),
                modifier = Modifier.fillMaxWidth().focusRequester(foco),
            )
        }
        Box(Modifier.height(46.dp).pulsable { visible = !visible }.padding(horizontal = 12.dp), Alignment.Center) {
            Texto(t(if (visible) "Hide" else "Show"), tamano = 14, peso = 700, color = paleta.apagado)
        }
    }
}
