package org.bc250.controlcenter.componentes

import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.collapse_gray
import org.bc250.controlcenter.recursos.expand_gray
import org.bc250.controlcenter.recursos.nav_blackbox
import org.bc250.controlcenter.recursos.nav_compute
import org.bc250.controlcenter.recursos.nav_cpu
import org.bc250.controlcenter.recursos.nav_dashboard
import org.bc250.controlcenter.recursos.nav_fans
import org.bc250.controlcenter.recursos.nav_firmware
import org.bc250.controlcenter.recursos.nav_gpu
import org.bc250.controlcenter.recursos.nav_performance
import org.bc250.controlcenter.recursos.nav_processes
import org.bc250.controlcenter.recursos.nav_remote
import org.bc250.controlcenter.recursos.nav_settings
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.jetbrains.compose.resources.DrawableResource

/** Una página de la aplicación, tal como aparece en la barra. */
class Seccion(val clave: String, val nombre: String, val icono: DrawableResource)

/** Un grupo de páginas con su título. */
class GrupoSecciones(val titulo: String, val secciones: List<Seccion>)

val GruposDeSecciones = listOf(
    GrupoSecciones("", listOf(Seccion("dashboard", "Dashboard", Res.drawable.nav_dashboard))),
    GrupoSecciones(
        "Hardware",
        listOf(
            Seccion("cpu", "CPU / SMU", Res.drawable.nav_cpu),
            Seccion("cu", "Compute Units", Res.drawable.nav_compute),
            Seccion("gpu", "GPU Governor", Res.drawable.nav_gpu),
            Seccion("extras", "Additional settings", Res.drawable.nav_settings),
        ),
    ),
    GrupoSecciones(
        "Monitoring",
        listOf(
            Seccion("performance", "Performance", Res.drawable.nav_performance),
            Seccion("fans", "Fans", Res.drawable.nav_fans),
            Seccion("processes", "Processes", Res.drawable.nav_processes),
        ),
    ),
    GrupoSecciones(
        "System",
        listOf(
            Seccion("black_box", "Black box", Res.drawable.nav_blackbox),
            Seccion("remote", "Remote access", Res.drawable.nav_remote),
        ),
    ),
)

val SeccionFirmware = Seccion("firmware", "Firmware (BIOS)", Res.drawable.nav_firmware)
val SeccionAjustes = Seccion("settings", "Settings", Res.drawable.nav_settings)

@Composable
fun BarraLateral(aplicacion: Aplicacion, modifier: Modifier = Modifier) {
    val paleta = ColoresActuales.current
    val plegada = aplicacion.barraPlegada
    val ancho = if (plegada) Medidas.anchoBarraPlegada else Medidas.anchoBarra
    val lado = if (plegada) 12.dp else 11.dp
    Column(
        modifier = modifier
            .width(ancho)
            .fillMaxHeight()
            .marco(paleta.panel, paleta.borde, Medidas.radioBarra)
            .padding(start = lado, end = lado, top = 15.dp, bottom = 13.dp),
    ) {
        MarcaBarra(aplicacion)
        Spacer(Modifier.height(14.dp))
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            for (grupo in GruposDeSecciones) {
                if (grupo.titulo.isNotEmpty()) {
                    TituloGrupo(grupo.titulo, plegada)
                }
                for (seccion in grupo.secciones) {
                    BotonBarra(seccion, aplicacion)
                }
            }
        }
        BotonBarra(SeccionFirmware, aplicacion)
        Spacer(Modifier.height(6.dp))
        LineaDivisoria()
        Spacer(Modifier.height(8.dp))
        BotonBarra(SeccionAjustes, aplicacion)
    }
}

@Composable
private fun MarcaBarra(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val plegada = aplicacion.barraPlegada
    val dibujo = if (plegada) Res.drawable.expand_gray else Res.drawable.collapse_gray
    Row(
        modifier = Modifier.fillMaxWidth().height(36.dp).padding(start = if (plegada) 0.dp else 2.dp),
        horizontalArrangement = if (plegada) Arrangement.Center else Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (!plegada) {
            Logotipo(30.dp)
            Column(Modifier.weight(1f)) {
                Texto("BC250", tamano = 15, peso = 860)
                Texto(nombreCorto(), tamano = 11, peso = 620, color = paleta.apagado)
            }
        }
        BotonIcono(
            icono = dibujo,
            alPulsar = { aplicacion.barraPlegada = !plegada },
            lado = 24.dp,
            tamano = 18.dp,
            conMarco = false,
            color = paleta.apagado,
        )
    }
}

/** «Control Center» en el idioma elegido: el nombre completo sin «BC250». */
private fun nombreCorto(): String {
    val resto = t("BC250 Control Center").replace("BC250", "").trim()
    return resto.replaceFirstChar { letra -> letra.uppercase() }
}

@Composable
private fun TituloGrupo(titulo: String, plegada: Boolean) {
    val paleta = ColoresActuales.current
    Box(Modifier.fillMaxWidth().height(28.dp).padding(top = 10.dp, bottom = 4.dp)) {
        if (plegada) {
            LineaDivisoria(Modifier.width(22.dp).align(Alignment.Center))
        } else {
            Texto(
                texto = t(titulo).uppercase(),
                tamano = 10,
                peso = 820,
                color = paleta.sutil,
                espaciado = 0.9.sp,
                lineas = 1,
                modifier = Modifier.padding(start = 11.dp),
            )
        }
    }
}

@Composable
private fun BotonBarra(seccion: Seccion, aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val plegada = aplicacion.barraPlegada
    val elegida = aplicacion.pagina == seccion.clave
    val interaccion = remember { MutableInteractionSource() }
    val encima by interaccion.collectIsHoveredAsState()
    val fondo = when {
        elegida -> paleta.acentoSuave
        encima -> paleta.panelAlterno
        else -> Color.Transparent
    }
    val colorTexto = if (elegida || encima) paleta.texto else paleta.apagado
    val colorIcono = if (elegida) paleta.acento else colorTexto
    val alto = if (plegada) 42.dp else Medidas.altoBotonBarra
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(alto)
            .background(fondo, RoundedCornerShape(4.dp))
            .pulsable(true, interaccion) { aplicacion.irA(seccion.clave) },
        contentAlignment = if (plegada) Alignment.Center else Alignment.CenterStart,
    ) {
        if (elegida) {
            val marca = Modifier.align(Alignment.CenterStart).size(3.dp, 18.dp)
            Box(marca.background(paleta.acento, RoundedCornerShape(1.5.dp)))
        }
        Row(
            modifier = if (plegada) Modifier else Modifier.padding(start = 8.dp, end = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icono(seccion.icono, tamano = 18.dp, color = colorIcono)
            if (!plegada) {
                Texto(
                    texto = t(seccion.nombre),
                    tamano = 13,
                    peso = if (elegida) 760 else 640,
                    color = colorTexto,
                    lineas = 1,
                    modifier = Modifier.padding(start = 12.dp),
                )
            }
        }
    }
}
