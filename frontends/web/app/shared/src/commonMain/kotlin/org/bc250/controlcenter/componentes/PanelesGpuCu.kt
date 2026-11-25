package org.bc250.controlcenter.componentes

import androidx.compose.foundation.layout.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.MedidasGpuCu

/** Reparte las celdas por filas; al estrechar la pantalla, las apila. */
@Composable
fun RejillaGpuCu(
    cantidad: Int,
    columnas: Int = 2,
    umbral: Dp = MedidasGpuCu.anchoMovil,
    contenido: @Composable (Int, Modifier) -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val columnasVisibles = if (maxWidth < umbral) 1 else columnas
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            var inicio = 0
            while (inicio < cantidad) {
                val primero = inicio
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (columna in 0 until columnasVisibles) {
                        val indice = primero + columna
                        if (indice < cantidad) contenido(indice, Modifier.weight(1f))
                        else Spacer(Modifier.weight(1f))
                    }
                }
                inicio += columnasVisibles
            }
        }
    }
}

@Composable
fun TituloGpuCu(texto: String) {
    Texto(texto, tamano = 15, peso = 700, modifier = Modifier.padding(start = 2.dp))
}

/** Una operación o una descripción y sus acciones, con espacio para el móvil. */
@Composable
fun FilaHerramientaGpuCu(titulo: String, detalle: String, tamanoTitulo: Int = 13, acciones: @Composable () -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        if (maxWidth < MedidasGpuCu.anchoMovil) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (titulo.isNotEmpty()) Texto(titulo, tamano = tamanoTitulo, peso = 700)
                if (detalle.isNotEmpty()) Texto(detalle, tamano = 12, color = ColoresActuales.current.apagado)
                acciones()
            }
        } else {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    if (titulo.isNotEmpty()) Texto(titulo, tamano = tamanoTitulo, peso = 700)
                    if (detalle.isNotEmpty()) Texto(detalle, tamano = 12, color = ColoresActuales.current.apagado)
                }
                acciones()
            }
        }
    }
}

@Composable
fun EstadoLecturaGpuCu(aplicacion: Aplicacion, error: String, cargando: Boolean, reintentar: () -> Unit) {
    if (cargando || error.isNotEmpty()) {
        SubPanel {
            Texto(if (cargando) t("Loading") else error, color = ColoresActuales.current.apagado, tamano = 13)
            if (!cargando) Boton(t("Refresh"), reintentar)
        }
    }
    if (!aplicacion.trabajo.terminado) {
        Texto(aplicacion.trabajo.titulo, color = ColoresActuales.current.naranja, tamano = 13)
    }
}

/** Ancho de las acciones del escritorio; las mismas acciones se apilan en el teléfono. */
@Composable
fun AccionesGpuCu(cantidad: Int, ancho: Dp, contenido: @Composable (Int, Modifier) -> Unit) {
    Box(Modifier.widthIn(max = ancho).fillMaxWidth()) {
        RejillaGpuCu(cantidad, cantidad, umbral = 400.dp, contenido = contenido)
    }
}
