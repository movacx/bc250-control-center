package org.bc250.controlcenter.paginas

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.BotonIcono
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.discord
import org.bc250.controlcenter.recursos.note_heart
import org.bc250.controlcenter.recursos.panel_kofi_cup
import org.bc250.controlcenter.tema.ColoresActuales
import org.jetbrains.compose.resources.painterResource

/** La nota del desarrollador: informa, lleva a Discord y ofrece Ko-fi. */
@Composable
internal fun NotaDelAutor(aplicacion: Aplicacion, nota: JsonObject, alCerrar: () -> Unit) {
    val paleta = ColoresActuales.current
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(12.dp)) {
        Image(painterResource(Res.drawable.note_heart), contentDescription = null, modifier = Modifier.size(30.dp))
        Column(Modifier.weight(1f), Arrangement.spacedBy(2.dp)) {
            Texto(t("A note from the developer"), tamano = 11, peso = 800, espaciado = 1.sp)
            Texto(t(nota.texto("title")), tamano = 16, peso = 750)
            Texto(t(nota.texto("when")), tamano = 13, peso = 500, color = paleta.apagado)
        }
    }
    for (parrafo in nota.textos("paragraphs")) {
        Texto(t(parrafo), tamano = 14, color = paleta.apagado)
    }
    ContactoDiscord(aplicacion, nota)
    Texto(t(nota.texto("thanks")), tamano = 14, color = paleta.apagado)
    Texto(nota.texto("signature"), tamano = 14, color = paleta.apagado)
    Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
        fun abrirKofi() {
            aplicacion.abrirEnlace(nota.texto("kofi"))
        }
        BotonIcono(Res.drawable.panel_kofi_cup, ::abrirKofi, lado = 38.dp, tamano = 20.dp)
        Texto("Ko-fi  ↗", 13, Modifier.pulsable(alPulsar = ::abrirKofi), color = paleta.acento)
        Spacer(Modifier.weight(1f))
        Boton(t("Close"), alCerrar, clase = ClaseBoton.PRINCIPAL)
    }
}

@Composable
private fun ContactoDiscord(aplicacion: Aplicacion, nota: JsonObject) {
    val paleta = ColoresActuales.current
    val portapapeles = LocalClipboardManager.current
    var copiado by remember { mutableStateOf(false) }
    fun copiar() {
        portapapeles.setText(AnnotatedString(nota.texto("handle")))
        copiado = true
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .marco(paleta.panelAlterno, paleta.bordeSuave, 4.dp)
            .padding(start = 12.dp, top = 8.dp, end = 8.dp, bottom = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(painterResource(Res.drawable.discord), contentDescription = null, modifier = Modifier.size(18.dp))
        Texto(nota.texto("handle"), 13, Modifier.weight(1f))
        Boton(t("Open profile"), { aplicacion.abrirEnlace(nota.texto("profile")) })
        Boton(t(if (copiado) "Copied" else "Copy"), ::copiar)
    }
}
