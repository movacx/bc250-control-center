package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonObject
import org.bc250.controlcenter.componentes.Bloques
import org.bc250.controlcenter.componentes.BotonIcono
import org.bc250.controlcenter.componentes.CampoTexto
import org.bc250.controlcenter.componentes.Icono
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.componentes.recordarOrdenes
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.close_gray
import org.bc250.controlcenter.recursos.dashboard_blue
import org.bc250.controlcenter.recursos.gpu_blue
import org.bc250.controlcenter.recursos.info_blue
import org.bc250.controlcenter.recursos.metrics_blue
import org.bc250.controlcenter.recursos.settings_blue
import org.bc250.controlcenter.recursos.terminal_window_gray
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.jetbrains.compose.resources.DrawableResource

/** Una sección de la Configuración en la barra de la izquierda. */
private class SeccionAjuste(val clave: String, val nombre: String, val icono: DrawableResource)

private class GrupoAjustes(val nombre: String, val secciones: List<SeccionAjuste>)

private val GruposDeAjustes = listOf(
    GrupoAjustes(
        "Interface",
        listOf(
            SeccionAjuste("general", "General", Res.drawable.settings_blue),
            SeccionAjuste("appearance", "Appearance", Res.drawable.dashboard_blue),
            SeccionAjuste("console", "Terminal and controls", Res.drawable.terminal_window_gray),
        ),
    ),
    GrupoAjustes(
        "Hardware",
        listOf(
            SeccionAjuste("hardware", "GPU governor", Res.drawable.gpu_blue),
            SeccionAjuste("telemetry", "Telemetry", Res.drawable.metrics_blue),
        ),
    ),
    GrupoAjustes("Application", listOf(SeccionAjuste("about", "About", Res.drawable.info_blue))),
)

/** Las páginas interiores marcan en la barra la sección de la que cuelgan. */
private fun seccionMadre(seccion: String): String {
    return when {
        seccion == "telemetry_guide" -> "telemetry"
        seccion.startsWith("support") || seccion == "overview" || seccion == "repositories" -> "about"
        else -> seccion
    }
}

/** La Configuración, en su propia ventana sobre la página, como en el escritorio. */
@Composable
fun VentanaConfiguracion(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    var seccion by remember { mutableStateOf(aplicacion.seccionAjustes) }
    var parametros by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var revision by remember { mutableIntStateOf(0) }
    var datos by remember { mutableStateOf(ObjetoVacio) }

    fun ir(nueva: String, nuevos: Map<String, String>) {
        if (nueva.isEmpty()) {
            parametros = parametros + nuevos
        } else {
            seccion = nueva
            parametros = nuevos
        }
    }

    LaunchedEffect(aplicacion.seccionAjustes) {
        seccion = aplicacion.seccionAjustes
        parametros = emptyMap()
    }
    LaunchedEffect(seccion, parametros, revision, aplicacion.revisionDeTextos, aplicacion.trabajo.terminado) {
        datos = aplicacion.consultar("settings", parametros + mapOf("section" to seccion))
    }
    val ordenes = recordarOrdenes(aplicacion, ::ir, recargar = { revision += 1 })

    Box(
        modifier = Modifier.fillMaxSize().background(paleta.color("scrim").copy(alpha = 0.55f)).pulsable(alPulsar = aplicacion::cerrarAjustes),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier
                .padding(8.dp)
                .widthIn(max = 1144.dp)
                .heightIn(max = 744.dp)
                .fillMaxSize()
                .marco(paleta.panel, paleta.bordeFuerte, 6.dp)
                .pulsable { }
                .padding(1.dp),
        ) {
            BarraTitulo(aplicacion)
            BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
                if (maxWidth >= 760.dp) {
                    Row(Modifier.fillMaxSize()) {
                        Navegacion(seccion, Modifier.width(207.dp).fillMaxHeight()) { clave -> ir(clave, emptyMap()) }
                        Box(Modifier.width(1.dp).fillMaxHeight().background(paleta.borde))
                        ContenidoSeccion(datos, seccion, ordenes, ::ir, Modifier.weight(1f))
                    }
                } else {
                    Column(Modifier.fillMaxSize()) {
                        NavegacionCompacta(seccion) { clave -> ir(clave, emptyMap()) }
                        ContenidoSeccion(datos, seccion, ordenes, ::ir, Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun BarraTitulo(aplicacion: Aplicacion) {
    Row(Modifier.fillMaxWidth().height(45.dp).padding(start = 18.dp, end = 11.dp), verticalAlignment = Alignment.CenterVertically) {
        Texto(t("Settings"), 14, Modifier.weight(1f), peso = 600)
        BotonIcono(Res.drawable.close_gray, aplicacion::cerrarAjustes, lado = 30.dp, tamano = 16.dp, conMarco = false)
    }
    LineaDivisoria(color = ColoresActuales.current.borde)
}

@Composable
private fun Navegacion(seccion: String, modifier: Modifier, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    var busqueda by remember { mutableStateOf("") }
    val fondo = if (paleta.esClaro) paleta.panelAlterno else paleta.ventana
    Column(modifier.background(fondo).padding(start = 12.dp, top = 12.dp, end = 11.dp, bottom = 12.dp).verticalScroll(rememberScrollState())) {
        CampoTexto(busqueda, { nueva -> busqueda = nueva }, Modifier.fillMaxWidth(), ayuda = t("Search"), alto = 32.dp)
        for (grupo in GruposDeAjustes) {
            val secciones = grupo.secciones.filter { item -> t(item.nombre).contains(busqueda.trim(), ignoreCase = true) }
            if (secciones.isNotEmpty()) {
                Box(Modifier.height(41.dp).padding(start = 8.dp, top = 14.dp)) {
                    Texto(t(grupo.nombre), tamano = 12, peso = 650, color = paleta.apagado)
                }
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (item in secciones) {
                        BotonSeccion(item, item.clave == seccionMadre(seccion), Modifier.fillMaxWidth()) { alElegir(item.clave) }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun NavegacionCompacta(seccion: String, alElegir: (String) -> Unit) {
    val paleta = ColoresActuales.current
    Column(Modifier.fillMaxWidth().background(paleta.ventana).padding(10.dp)) {
        for (pareja in GruposDeAjustes.flatMap { grupo -> grupo.secciones }.chunked(2)) {
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(6.dp)) {
                for (item in pareja) {
                    BotonSeccion(item, item.clave == seccionMadre(seccion), Modifier.weight(1f)) { alElegir(item.clave) }
                }
            }
        }
    }
    LineaDivisoria(color = paleta.borde)
}

@Composable
private fun BotonSeccion(item: SeccionAjuste, elegida: Boolean, modifier: Modifier, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (elegida) paleta.color("control_pressed") else Color.Transparent
    Row(
        modifier = modifier
            .height(34.dp)
            .background(fondo, RoundedCornerShape(Medidas.radioChico))
            .pulsable(alPulsar = alPulsar)
            .padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icono(item.icono, tamano = 16.dp, color = if (elegida) paleta.acento else paleta.apagado)
        Texto(t(item.nombre), tamano = 13, peso = 600, lineas = 1)
    }
}

@Composable
private fun ContenidoSeccion(
    datos: JsonObject,
    seccion: String,
    ordenes: org.bc250.controlcenter.componentes.Ordenes,
    alIr: (String, Map<String, String>) -> Unit,
    modifier: Modifier,
) {
    val paleta = ColoresActuales.current
    val desplazador = rememberScrollState()
    LaunchedEffect(seccion) {
        desplazador.scrollTo(0)
    }
    Box(modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(desplazador)
                .padding(start = 28.dp, top = 22.dp, end = 30.dp, bottom = 28.dp),
        ) {
            val vuelta = datos.objeto("vuelta")
            if (vuelta.isNotEmpty()) {
                val enlace = Modifier.padding(top = 18.dp).pulsable { alIr(vuelta.texto("seccion"), emptyMap()) }
                Texto("‹  " + vuelta.texto("texto"), 12, enlace, peso = 700, color = paleta.acento)
            }
            val titulo = datos.texto("titulo")
            if (titulo.isNotEmpty()) {
                val tamano = if (vuelta.isEmpty()) 17 else 18
                Texto(titulo, tamano, Modifier.padding(start = 5.dp, top = if (vuelta.isEmpty()) 0.dp else 6.dp), peso = 800)
            }
            if (datos.isEmpty()) {
                Texto(t("Loading"), 13, Modifier.padding(top = 20.dp), color = paleta.apagado)
            }
            Bloques(datos.objetos("bloques"), ordenes)
            Spacer(Modifier.height(8.dp))
        }
    }
}
