package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Popup
import androidx.compose.ui.window.PopupProperties
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

/** El nombre de la pestaña ofrece las otras vistas del recurso, con su explicación. */
@Composable
internal fun PestañasRendimiento(datos: JsonObject, elegida: String, vista: String,
    distribucion: String, ventana: Int, alElegir: (String) -> Unit, alVista: (String) -> Unit,
    alDistribucion: (String) -> Unit, alVentana: (Int) -> Unit) {
    val paleta = ColoresActuales.current
    var menu by remember { mutableStateOf(false) }
    val pestañas = datos.objetos("tabs")
    Box {
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), Arrangement.spacedBy(22.dp)) {
            for (pestaña in pestañas) {
                val clave = pestaña.texto("key")
                Column(Modifier.pulsable {
                    if (clave == elegida) menu = !menu else {
                        menu = false
                        alElegir(clave)
                    }
                }.height(M.altoPestana).width(IntrinsicSize.Max), Arrangement.SpaceBetween) {
                    Texto(pestaña.texto("title"), tamano = 13, peso = if (clave == elegida) 780 else 700,
                        modifier = Modifier.padding(horizontal = 2.dp, vertical = 5.dp))
                    Box(Modifier.fillMaxWidth().height(2.dp).background(if (clave == elegida) paleta.acento else paleta.panel))
                }
            }
        }
        LineaDivisoria(Modifier.align(Alignment.BottomStart).fillMaxWidth())
        if (menu) {
            Popup(alignment = Alignment.TopStart, onDismissRequest = { menu = false },
                properties = PopupProperties(focusable = true)) {
                Column(Modifier.widthIn(max = 360.dp).fillMaxWidth().heightIn(max = 500.dp)
                    .marco(paleta.panelElevado, paleta.bordeFuerte, 10.dp)
                    .verticalScroll(rememberScrollState()).padding(8.dp), Arrangement.spacedBy(4.dp)) {
                    Texto(t("Views"), tamano = 11, peso = 780)
                    val opciones = datos.objetos(if (elegida == "sensors") "layouts" else "views")
                    for (opcion in opciones) {
                        val clave = opcion.texto("key")
                        val disponible = elegida == "sensors" || opcion.logico("available")
                        val actual = clave == if (elegida == "sensors") distribucion else vista
                        Row(Modifier.fillMaxWidth().pulsable(disponible) {
                            if (elegida == "sensors") alDistribucion(clave) else alVista(clave)
                            menu = false
                        }.padding(8.dp), Arrangement.spacedBy(10.dp)) {
                            Opcion(actual, color = paleta.acento)
                            Column(Modifier.weight(1f)) {
                                Texto(opcion.texto("title"), tamano = 11, peso = 760,
                                    color = if (disponible) paleta.texto else paleta.textoInactivo)
                                Leyenda(opcion.texto("hint"))
                            }
                        }
                    }
                    VentanaRendimiento(ventana, alVentana)
                }
            }
        }
    }
}
