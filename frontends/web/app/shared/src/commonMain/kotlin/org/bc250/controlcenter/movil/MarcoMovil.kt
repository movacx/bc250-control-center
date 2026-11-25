package org.bc250.controlcenter.movil

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.GruposDeSecciones
import org.bc250.controlcenter.componentes.Icono
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Logotipo
import org.bc250.controlcenter.componentes.Seccion
import org.bc250.controlcenter.componentes.SeccionAjustes
import org.bc250.controlcenter.componentes.SeccionFirmware
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.nombreCorto
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.BotonAtras
import org.bc250.controlcenter.datos.Trabajo
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.recursos.Res
import org.bc250.controlcenter.recursos.movil_atras
import org.bc250.controlcenter.recursos.movil_consola
import org.bc250.controlcenter.recursos.movil_mas
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas

private const val SEGUNDOS_DE_AVISO = 4

/** Las cuatro páginas de la barra inferior; el resto está en el menú. */
private val PaginasDeBarra = listOf("dashboard" to "Panel", "cpu" to "CPU", "cu" to "CU", "gpu" to "GPU")

private val TodasLasSecciones = GruposDeSecciones.flatMap { grupo -> grupo.secciones } + SeccionFirmware + SeccionAjustes

/** La aplicación en un teléfono: cabecera, página, barra inferior y lo que se abre encima. */
@Composable
fun VentanaMovil(aplicacion: Aplicacion, pagina: @Composable () -> Unit) {
    val paleta = ColoresActuales.current
    val movil = remember { EstadoMovil() }
    LaunchedEffect(aplicacion.pagina, aplicacion.seccionAjustes) {
        movil.alCambiarDePagina()
    }
    DisposableEffect(aplicacion, movil) {
        BotonAtras.atender = { volverAtras(aplicacion, movil) }
        onDispose { BotonAtras.atender = { false } }
    }
    CompositionLocalProvider(LocalMovil provides movil) {
        val arriba = paleta.ventana
        Box(
            Modifier.fillMaxSize().background(paleta.panel)
                .drawBehind { drawRect(arriba, size = Size(size.width, size.height / 2)) }
                .windowInsetsPadding(WindowInsets.safeDrawing),
        ) {
            Column(Modifier.fillMaxSize().background(paleta.ventana)) {
                CabeceraMovil(aplicacion)
                Box(Modifier.fillMaxWidth().weight(1f)) {
                    key(aplicacion.pagina) {
                        pagina()
                    }
                    AvisoDeTrabajo(aplicacion, VigilanteDeClave(aplicacion), Modifier.align(Alignment.BottomCenter))
                }
                BarraInferior(aplicacion)
            }
            OrillaDelMenu()
            MenuLateral(aplicacion)
            HojaInferior()
        }
    }
}

/** Cierra lo último que se abrió; desde otra página vuelve al Panel. Dice si hizo algo. */
private fun volverAtras(aplicacion: Aplicacion, movil: EstadoMovil): Boolean {
    when {
        aplicacion.confirmacion != null || aplicacion.textoAbierto != null || aplicacion.recorridoAbierto -> aplicacion.volverAtras()
        movil.volver() -> return true
        aplicacion.seccionAjustes.isNotEmpty() -> aplicacion.cerrarAjustes()
        aplicacion.pagina != "dashboard" -> aplicacion.irA("dashboard")
        else -> return false
    }
    return true
}

// -- cabecera ------------------------------------------------------------------------------------------

@Composable
private fun CabeceraMovil(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val movil = movil()
    val enAjustes = aplicacion.seccionAjustes.isNotEmpty()
    val clave = if (enAjustes) "settings" else aplicacion.pagina
    val seccion = TodasLasSecciones.firstOrNull { opcion -> opcion.clave == clave }
    val titulo = movil.detalle.ifEmpty { t(seccion?.nombre ?: "") }
    Row(
        modifier = Modifier.fillMaxWidth().height(62.dp).background(paleta.ventana).padding(start = 18.dp, end = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (movil.detalle.isNotEmpty()) {
            Box(Modifier.offset(x = (-12).dp).width(32.dp).height(44.dp).pulsable { movil.cerrarDetalle() }, Alignment.CenterEnd) {
                Icono(Res.drawable.movil_atras, 24.dp, paleta.texto)
            }
        }
        TextoTitulo(titulo, if (movil.detalle.isEmpty()) 27 else 22, Modifier.weight(1f), lineas = 1)
        Box(Modifier.size(44.dp).pulsable { movil.abrirConsola(aplicacion) }, Alignment.Center) {
            Icono(Res.drawable.movil_consola, 24.dp, paleta.texto)
        }
    }
}

// -- página --------------------------------------------------------------------------------------------

/**
 * El cuerpo de una página: sus pestañas arriba, lo que se desplaza y, si lo hay, el botón fijo de abajo.
 * Con un detalle abierto no se ven las pestañas.
 */
@Composable
fun PaginaMovil(
    clave: String,
    pestanas: List<String> = emptyList(),
    pie: (@Composable RowScope.() -> Unit)? = null,
    contenido: @Composable ColumnScope.() -> Unit,
) {
    val movil = movil()
    val enDetalle = movil.detalle.isNotEmpty()
    SideEffect { movil.conPie = pie != null }
    Column(Modifier.fillMaxSize()) {
        if (pestanas.isNotEmpty() && !enDetalle) {
            PestanasMovil(clave, pestanas)
        }
        key(movil.pestana(clave), movil.detalle) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(start = 16.dp, end = 16.dp, top = 14.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(if (Medidas.compacta) 8.dp else 12.dp),
                content = contenido,
            )
        }
        if (pie != null) {
            val paleta = ColoresActuales.current
            LineaDivisoria(color = paleta.bordeSuave)
            Row(
                modifier = Modifier.fillMaxWidth().background(paleta.ventana).padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                content = pie,
            )
        }
    }
}

@Composable
private fun PestanasMovil(clave: String, nombres: List<String>) {
    val paleta = ColoresActuales.current
    val movil = movil()
    val elegida = movil.pestana(clave)
    Box(Modifier.fillMaxWidth().background(paleta.ventana)) {
        LineaDivisoria(Modifier.align(Alignment.BottomCenter), color = paleta.borde)
        Row(Modifier.fillMaxWidth()) {
            for ((indice, nombre) in nombres.withIndex()) {
                val esta = indice == elegida
                Box(Modifier.weight(1f).height(48.dp).pulsable { movil.elegirPestana(clave, indice) }, Alignment.Center) {
                    Texto(nombre, tamano = 15, peso = if (esta) 700 else 500, color = if (esta) paleta.texto else paleta.sutil, lineas = 1)
                    if (esta) {
                        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal = 20.dp).height(3.dp).background(paleta.acento))
                    }
                }
            }
        }
    }
}

// -- barra inferior ------------------------------------------------------------------------------------

@Composable
private fun BarraInferior(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val movil = movil()
    val enAjustes = aplicacion.seccionAjustes.isNotEmpty()
    val enBarra = !enAjustes && PaginasDeBarra.any { (clave, _) -> clave == aplicacion.pagina }
    LineaDivisoria(color = paleta.borde)
    Row(Modifier.fillMaxWidth().height(64.dp).background(paleta.panel)) {
        for ((clave, nombre) in PaginasDeBarra) {
            val seccion = TodasLasSecciones.first { opcion -> opcion.clave == clave }
            BotonInferior(seccion, t(nombre), elegido = !enAjustes && clave == aplicacion.pagina) {
                aplicacion.cerrarAjustes()
                movil.alCambiarDePagina()
                aplicacion.irA(clave)
            }
        }
        BotonInferior(null, t("More"), elegido = !enBarra) { movil.menuAbierto = true }
    }
}

@Composable
private fun RowScope.BotonInferior(seccion: Seccion?, nombre: String, elegido: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val color = if (elegido) paleta.texto else paleta.sutil
    Box(Modifier.weight(1f).fillMaxHeight().pulsable(alPulsar = alPulsar), Alignment.Center) {
        if (elegido) {
            Box(Modifier.align(Alignment.TopCenter).size(44.dp, 3.dp).background(paleta.acento))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Icono(seccion?.icono ?: Res.drawable.movil_mas, 23.dp, if (elegido) paleta.acento else color)
            Texto(nombre, tamano = 12, peso = if (elegido) 700 else 500, color = color, lineas = 1)
        }
    }
}

// -- menú lateral --------------------------------------------------------------------------------------

/** La orilla izquierda: deslizar desde ella abre el menú. */
@Composable
private fun OrillaDelMenu() {
    val movil = movil()
    Box(
        Modifier.width(14.dp).fillMaxHeight().padding(top = 110.dp, bottom = 70.dp).pointerInput(Unit) {
            detectHorizontalDragGestures { _, movimiento ->
                if (movimiento > 6f) {
                    movil.menuAbierto = true
                }
            }
        },
    )
}

@Composable
private fun MenuLateral(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val movil = movil()
    Velo(movil.menuAbierto) { movil.menuAbierto = false }
    Deslizante(movil.menuAbierto, desdeAbajo = false) {
        BoxWithConstraints(Modifier.fillMaxHeight()) {
            val ancho = minOf(316.dp, maxWidth * 0.84f)
            Row(Modifier.width(ancho).fillMaxHeight().background(paleta.panel).pulsable { }) {
                Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                    MarcaDelMenu(movil)
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 12.dp)) {
                        for (grupo in GruposDeSecciones) {
                            if (grupo.titulo.isNotEmpty()) {
                                TituloDelMenu(t(grupo.titulo))
                            }
                            for (seccion in grupo.secciones) {
                                EntradaDelMenu(aplicacion, seccion)
                            }
                        }
                        EntradaDelMenu(aplicacion, SeccionFirmware)
                    }
                    LineaDivisoria(color = paleta.borde)
                    Box(Modifier.padding(start = 12.dp, end = 12.dp, top = 8.dp)) {
                        EntradaDelMenu(aplicacion, SeccionAjustes)
                    }
                }
                Box(Modifier.width(1.dp).fillMaxHeight().background(paleta.borde))
            }
        }
    }
}

@Composable
private fun MarcaDelMenu(movil: EstadoMovil) {
    val paleta = ColoresActuales.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 20.dp, top = 14.dp, end = 8.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.clip(RoundedCornerShape(8.dp))) {
            Logotipo(40.dp)
        }
        Column(Modifier.weight(1f)) {
            TextoTitulo("BC250", 24)
            Texto(nombreCorto(), tamano = 12, peso = 700, color = paleta.apagado)
        }
        Box(Modifier.size(44.dp).pulsable { movil.menuAbierto = false }, Alignment.Center) {
            Icono(Res.drawable.movil_atras, 22.dp, paleta.apagado)
        }
    }
}

@Composable
private fun TituloDelMenu(titulo: String) {
    val color = ColoresActuales.current.sutil
    Texto(titulo, 13, Modifier.padding(start = 12.dp, top = 18.dp, bottom = 6.dp), peso = 500, color = color)
}

@Composable
private fun EntradaDelMenu(aplicacion: Aplicacion, seccion: Seccion) {
    val paleta = ColoresActuales.current
    val movil = movil()
    val enAjustes = aplicacion.seccionAjustes.isNotEmpty()
    val elegida = if (enAjustes) seccion.clave == "settings" else seccion.clave == aplicacion.pagina
    val fondo = if (elegida) paleta.panelElevado else paleta.panel
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(50.dp)
            .background(fondo, RoundedCornerShape(10.dp))
            .pulsable {
                movil.alCambiarDePagina()
                if (seccion.clave != "settings") {
                    aplicacion.cerrarAjustes()
                }
                aplicacion.irA(seccion.clave)
            },
        contentAlignment = Alignment.CenterStart,
    ) {
        Row(Modifier.padding(horizontal = 12.dp), Arrangement.spacedBy(14.dp), Alignment.CenterVertically) {
            Icono(seccion.icono, 22.dp, if (elegida) paleta.acento else paleta.apagado)
            Texto(t(seccion.nombre), tamano = 15, peso = if (elegida) 700 else 500, color = if (elegida) paleta.texto else paleta.apagado, lineas = 1)
        }
    }
}

// -- ventana inferior ------------------------------------------------------------------------------------

@Composable
private fun HojaInferior() {
    val movil = movil()
    var ultima by remember { mutableStateOf<ContenidoHoja?>(null) }
    val actual = movil.hoja
    if (actual != null) {
        ultima = actual
    }
    Velo(actual != null) { movil.cerrarHoja() }
    Deslizante(actual != null, desdeAbajo = true) {
        val contenido = ultima
        if (contenido != null) {
            CajaDeHoja(contenido = contenido)
        }
    }
}

/** La caja que sube desde abajo, con su asa y su contenido. */
@Composable
fun CajaDeHoja(modifier: Modifier = Modifier, contenido: ContenidoHoja) {
    val paleta = ColoresActuales.current
    val forma = RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp)
    BoxWithConstraints(modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .heightIn(max = maxHeight * 0.86f)
                .clip(forma)
                .background(paleta.panel)
                .pulsable { },
        ) {
            Box(
                Modifier.padding(top = 10.dp, bottom = 2.dp).size(40.dp, 4.dp)
                    .background(paleta.bordeFuerte, RoundedCornerShape(2.dp)).align(Alignment.CenterHorizontally),
            )
            Column(
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 28.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                content = contenido,
            )
        }
    }
}

// -- consola -----------------------------------------------------------------------------------------------

/** La lista de operaciones de esta visita, con lo que escribió cada una. */
fun EstadoMovil.abrirConsola(aplicacion: Aplicacion) {
    abrirHoja {
        TituloHoja(t("Console"))
        if (aplicacion.trabajos.isEmpty()) {
            TextoHoja(t("There are no operations. The console opens by itself when one needs it."))
        }
        for (trabajo in aplicacion.trabajos.reversed()) {
            TrabajoEnConsola(aplicacion, trabajo)
        }
        CerrarHoja()
    }
}

@Composable
private fun TrabajoEnConsola(aplicacion: Aplicacion, trabajo: Trabajo) {
    val paleta = ColoresActuales.current
    GrupoMovil {
        FilaLibre(altoMinimo = 40.dp) {
            TextosFila(trabajo.titulo)
            Pildora(estadoDe(trabajo), viva = trabajo.correcto)
        }
        TextoConsola(trabajo.texto.ifEmpty { "…" }, Modifier.fillMaxWidth().heightIn(max = 320.dp))
        if (trabajo.esperaClave || trabajo.esperaRespuesta) {
            RespuestaMovil(aplicacion, trabajo)
        }
        if (!trabajo.terminado) {
            TiraAcciones(AccionTira(t("Stop")) { aplicacion.interrumpirTrabajo() })
        } else if (trabajo.fallo) {
            TiraAcciones(AccionTira(t("Report this problem")) { aplicacion.abrirAjustes("support_report") })
        }
    }
    if (trabajo.esperaClave) {
        NotaMovil(t("The password goes straight to the board and is not saved."), paleta.sutil)
    }
}

private fun estadoDe(trabajo: Trabajo): String {
    return when {
        !trabajo.terminado -> t("Running")
        trabajo.correcto -> t("Completed")
        trabajo.cancelado -> t("Cancelled")
        else -> t("Failed")
    }
}

@Composable
private fun RespuestaMovil(aplicacion: Aplicacion, trabajo: Trabajo) {
    var respuesta by remember(trabajo.id, trabajo.esperaClave) { mutableStateOf("") }
    val ayuda = t(if (trabajo.esperaClave) "Linux password" else "Input")
    FilaLibre(altoMinimo = 62.dp) {
        CampoMovil(respuesta, Modifier.weight(1f), ayuda, secreto = trabajo.esperaClave) { nuevo -> respuesta = nuevo }
        BotonMovil(t("Send"), clase = ClaseBoton.PRINCIPAL) {
            aplicacion.responderTrabajo(respuesta)
            respuesta = ""
        }
    }
}

/** El aviso de que hay una operación; si pide la clave, la consola se abre sola. */
@Composable
private fun AvisoDeTrabajo(aplicacion: Aplicacion, peticion: PeticionDeClave, modifier: Modifier) {
    val paleta = ColoresActuales.current
    val movil = movil()
    val trabajo = aplicacion.trabajo
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(trabajo.id, trabajo.terminado) {
        visible = trabajo.id > 0 && !trabajo.terminado
        if (trabajo.id > 0 && trabajo.terminado && !trabajo.fallo) {
            visible = aplicacion.trabajos.any { abierto -> abierto.id == trabajo.id }
            delay(SEGUNDOS_DE_AVISO * 1000L)
            visible = false
        } else if (trabajo.fallo) {
            visible = true
        }
    }
    LaunchedEffect(trabajo.id, trabajo.esperaRespuesta) {
        if (trabajo.esperaRespuesta && !trabajo.esperaClave) {
            movil.abrirConsola(aplicacion)
        }
    }
    if (!visible) {
        return
    }
    Row(
        modifier = modifier
            .padding(start = 16.dp, end = 16.dp, bottom = if (movil.conPie) 83.dp else 16.dp)
            .fillMaxWidth()
            .marco(paleta.panelElevado, if (trabajo.fallo) paleta.rojoBorde else paleta.bordeFuerte, 12.dp)
            .padding(start = 14.dp, top = 8.dp, end = 8.dp, bottom = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (!trabajo.terminado) {
            Giro()
        }
        val texto = if (trabajo.terminado) "${trabajo.titulo}: ${estadoDe(trabajo)}" else "${trabajo.titulo}…"
        Texto(texto, tamano = 14, peso = 700, lineas = 2, modifier = Modifier.weight(1f))
        BotonMovil(t(if (trabajo.esperaClave) "Password" else "View console")) {
            visible = !trabajo.terminado
            if (trabajo.esperaClave) {
                movil.abrirClave(aplicacion, peticion)
            } else {
                movil.abrirConsola(aplicacion)
            }
        }
    }
}
