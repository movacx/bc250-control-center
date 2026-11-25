package org.bc250.controlcenter

import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEvent
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import org.bc250.controlcenter.componentes.BarraLateral
import org.bc250.controlcenter.componentes.DialogoConfirmacion
import org.bc250.controlcenter.componentes.DialogoTexto
import org.bc250.controlcenter.componentes.LocalPaletas
import org.bc250.controlcenter.componentes.BalizaConsola
import org.bc250.controlcenter.componentes.NavegacionMando
import org.bc250.controlcenter.componentes.PanelConsola
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.Aviso
import org.bc250.controlcenter.datos.EstadoSesion
import org.bc250.controlcenter.datos.entero
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.paginas.PaginaAccesoRemoto
import org.bc250.controlcenter.paginas.PaginaAjustesAdicionales
import org.bc250.controlcenter.paginas.PaginaCajaNegra
import org.bc250.controlcenter.paginas.VentanaActualizacion
import org.bc250.controlcenter.paginas.VentanaBienvenida
import org.bc250.controlcenter.paginas.VentanaConfiguracion
import org.bc250.controlcenter.paginas.VentanaRecorrido
import org.bc250.controlcenter.paginas.PaginaCpu
import org.bc250.controlcenter.paginas.PaginaFirmware
import org.bc250.controlcenter.paginas.PaginaGpu
import org.bc250.controlcenter.paginas.PaginaPanel
import org.bc250.controlcenter.paginas.PaginaProcesos
import org.bc250.controlcenter.paginas.PaginaRendimiento
import org.bc250.controlcenter.paginas.PaginaUnidades
import org.bc250.controlcenter.paginas.PaginaVentiladores
import org.bc250.controlcenter.paginas.PaginaIngreso
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.LetrasActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.letrasListas
import org.bc250.controlcenter.tema.cargarLetras

@Composable
fun App() {
    val tareas = rememberCoroutineScope()
    val aplicacion = remember { Aplicacion(tareas) }
    LaunchedEffect(Unit) {
        aplicacion.iniciar()
    }
    aplicacion.sistemaOscuro = isSystemInDarkTheme()
    val escala = aplicacion.preferencias.entero("scale", 100) / 100f
    val densidad = LocalDensity.current
    CompositionLocalProvider(
        ColoresActuales provides aplicacion.paleta,
        LetrasActuales provides cargarLetras(),
        LocalPaletas provides aplicacion.paletas,
        LocalDensity provides Density(densidad.density * escala, densidad.fontScale),
    ) {
        val sePuedeDibujar = letrasListas(aplicacion.idioma)
        Box(
            Modifier
                .fillMaxSize()
                .background(aplicacion.paleta.ventana)
                .onPreviewKeyEvent { evento -> atenderTecla(evento, aplicacion) },
        ) {
            if (sePuedeDibujar) {
                when (aplicacion.sesion) {
                    EstadoSesion.DENTRO -> Ventana(aplicacion)
                    else -> PaginaIngreso(aplicacion)
                }
                VentanasEncima(aplicacion)
            }
            NavegacionMando(aplicacion)
            val confirmacion = aplicacion.confirmacion
            if (confirmacion != null) {
                DialogoConfirmacion(confirmacion, aplicacion)
            }
            if (!aplicacion.consolaVisible && !aplicacion.trabajo.terminado) {
                BalizaConsola(aplicacion, Modifier.align(Alignment.CenterEnd))
            }
            val aviso = aplicacion.aviso
            if (aviso != null) {
                CuadroAviso(aviso, Modifier.align(Alignment.BottomEnd))
            }
        }
    }
}

/** Lo que se abre sobre la página: Configuración, actualización, recorrido y textos largos. */
@Composable
private fun VentanasEncima(aplicacion: Aplicacion) {
    if (aplicacion.sesion != EstadoSesion.DENTRO) {
        return
    }
    if (aplicacion.seccionAjustes.isNotEmpty()) {
        VentanaConfiguracion(aplicacion)
    }
    if (aplicacion.actualizacionAbierta) {
        VentanaActualizacion(aplicacion)
    }
    val falta = aplicacion.preferencias.isNotEmpty() && !aplicacion.preferencias.logico("welcome_done")
    if (falta && aplicacion.puedeControlar) {
        VentanaBienvenida(aplicacion)
    }
    if (aplicacion.recorridoAbierto) {
        VentanaRecorrido(aplicacion)
    }
    val texto = aplicacion.textoAbierto
    if (texto != null) {
        DialogoTexto(texto) { aplicacion.textoAbierto = null }
    }
}

/** La barra lateral y, a su lado, la página elegida. */
@Composable
private fun Ventana(aplicacion: Aplicacion) {
    Row(
        modifier = Modifier.fillMaxSize().padding(Medidas.margenVentana),
        horizontalArrangement = Arrangement.spacedBy(Medidas.margenVentana),
    ) {
        BarraLateral(aplicacion, Modifier.padding(top = 8.dp))
        Column(Modifier.weight(1f), Arrangement.spacedBy(Medidas.espacio)) {
            Box(Modifier.weight(1f)) {
                PaginaElegida(aplicacion)
            }
            if (aplicacion.consolaVisible) {
                PanelConsola(aplicacion)
            }
        }
    }
}

@Composable
private fun PaginaElegida(aplicacion: Aplicacion) {
    when (aplicacion.pagina) {
        "cpu" -> PaginaCpu(aplicacion)
        "dashboard" -> PaginaPanel(aplicacion)
        "cu" -> PaginaUnidades(aplicacion)
        "gpu" -> PaginaGpu(aplicacion)
        "extras" -> PaginaAjustesAdicionales(aplicacion)
        "performance" -> PaginaRendimiento(aplicacion)
        "fans" -> PaginaVentiladores(aplicacion)
        "processes" -> PaginaProcesos(aplicacion)
        "black_box" -> PaginaCajaNegra(aplicacion)
        "remote" -> PaginaAccesoRemoto(aplicacion)
        "firmware" -> PaginaFirmware(aplicacion)
    }
}

@Composable
private fun CuadroAviso(aviso: Aviso, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val borde = if (aviso.error) paleta.rojoBorde else paleta.acentoBorde
    Box(modifier.padding(24.dp).marco(paleta.panelElevado, borde, Medidas.radioPanel).padding(14.dp)) {
        Texto(t(aviso.texto), tamano = 13)
    }
}

/** F4 muestra u oculta la consola; sin ninguna operación no hay nada que enseñar. */
private fun atenderTecla(evento: KeyEvent, aplicacion: Aplicacion): Boolean {
    if (evento.key != Key.F4 || evento.type != KeyEventType.KeyDown) {
        return false
    }
    aplicacion.consolaVisible = !aplicacion.consolaVisible && aplicacion.trabajos.isNotEmpty()
    return true
}
