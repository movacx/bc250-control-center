package org.bc250.controlcenter.paginas

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
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
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.bc250.controlcenter.componentes.Bloque
import org.bc250.controlcenter.componentes.Boton
import org.bc250.controlcenter.componentes.CasillaChica
import org.bc250.controlcenter.componentes.ClaseBoton
import org.bc250.controlcenter.componentes.Interruptor
import org.bc250.controlcenter.componentes.LineaDivisoria
import org.bc250.controlcenter.componentes.Ordenes
import org.bc250.controlcenter.componentes.RejillaGpuCu
import org.bc250.controlcenter.componentes.Texto
import org.bc250.controlcenter.componentes.TextoConsola
import org.bc250.controlcenter.componentes.marco
import org.bc250.controlcenter.componentes.pulsable
import org.bc250.controlcenter.componentes.recordarOrdenes
import org.bc250.controlcenter.datos.Aplicacion
import org.bc250.controlcenter.datos.ObjetoVacio
import org.bc250.controlcenter.datos.logico
import org.bc250.controlcenter.datos.objeto
import org.bc250.controlcenter.datos.objetos
import org.bc250.controlcenter.datos.t
import org.bc250.controlcenter.datos.texto
import org.bc250.controlcenter.datos.textos
import org.bc250.controlcenter.tema.ColoresActuales

private val Pasos = listOf("Language", "Appearance", "Navigation", "Dependencies", "Guided tour")
private const val PASO_DEPENDENCIAS = 3

/** La primera visita: idioma, aspecto, navegación, dependencias y el recorrido. */
@Composable
fun VentanaBienvenida(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    var paso by remember { mutableIntStateOf(0) }
    var revision by remember { mutableIntStateOf(0) }
    var datos by remember { mutableStateOf(ObjetoVacio) }
    LaunchedEffect(revision, aplicacion.revisionDeTextos) {
        datos = aplicacion.consultar("settings.welcome")
    }
    LaunchedEffect(paso) {
        if (paso == PASO_DEPENDENCIAS) {
            aplicacion.leerPagina("dashboard")
        }
    }
    val ordenes = recordarOrdenes(aplicacion, { _, _ -> }, recargar = { revision += 1 })

    fun salir(conRecorrido: Boolean) {
        aplicacion.guardarPreferencia("welcome_done", JsonPrimitive(true)) {
            if (conRecorrido) {
                aplicacion.empezarRecorrido()
            }
        }
    }

    fun seguir() {
        if (paso < Pasos.lastIndex) {
            paso += 1
        } else {
            salir(conRecorrido = true)
        }
    }

    Box(
        Modifier.fillMaxSize().background(paleta.color("scrim").copy(alpha = 0.7f)).pulsable { },
        contentAlignment = Alignment.Center,
    ) {
        BoxWithConstraints(
            Modifier.padding(12.dp).widthIn(max = 1240.dp).heightIn(max = 760.dp).fillMaxSize()
                .marco(paleta.panel, paleta.bordeFuerte, 6.dp).padding(1.dp),
        ) {
            val ancha = maxWidth >= 760.dp
            Row(Modifier.fillMaxSize()) {
                if (ancha) {
                    Carril(paso, { elegido -> paso = elegido }, { salir(conRecorrido = false) })
                }
                Column(Modifier.weight(1f).padding(start = 28.dp, top = 26.dp, end = 28.dp, bottom = 18.dp)) {
                    EncabezadoPaso(paso)
                    Box(Modifier.weight(1f).fillMaxWidth()) {
                        ContenidoPaso(aplicacion, paso, datos, ordenes)
                    }
                    Spacer(Modifier.height(12.dp))
                    LineaDivisoria(color = paleta.borde)
                    PiePaso(paso, { paso -= 1 }, ::seguir, if (ancha) null else ({ salir(conRecorrido = false) }))
                }
            }
        }
    }
}

// -- el marco ------------------------------------------------------------------------------------------

@Composable
private fun Carril(paso: Int, alElegir: (Int) -> Unit, alOmitir: () -> Unit) {
    val paleta = ColoresActuales.current
    Column(
        Modifier.width(212.dp).fillMaxHeight().background(paleta.panelAlterno).padding(start = 16.dp, top = 24.dp, end = 16.dp, bottom = 20.dp),
        Arrangement.spacedBy(6.dp),
    ) {
        Texto("BC250 Control Center", tamano = 15, peso = 800)
        Spacer(Modifier.height(16.dp))
        for ((numero, nombre) in Pasos.withIndex()) {
            FilaPaso(numero, t(nombre), paso) { alElegir(numero) }
        }
        Spacer(Modifier.weight(1f))
        val omitir = t(if (paso == Pasos.lastIndex) "Go straight in" else "Skip setup")
        Texto(omitir, 13, Modifier.pulsable(alPulsar = alOmitir).padding(horizontal = 6.dp, vertical = 8.dp), peso = 640, color = paleta.apagado)
    }
    Box(Modifier.width(1.dp).fillMaxHeight().background(paleta.bordeFuerte))
}

@Composable
private fun FilaPaso(numero: Int, nombre: String, paso: Int, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val elegido = numero == paso
    val fondo = if (elegido) paleta.acentoSuave else Color.Transparent
    val borde = if (elegido) paleta.acento else Color.Transparent
    val color = when {
        elegido -> paleta.acento
        numero < paso -> paleta.texto
        else -> paleta.apagado
    }
    Row(
        Modifier.fillMaxWidth().height(38.dp).marco(fondo, borde, 4.dp).pulsable(alPulsar = alPulsar).padding(horizontal = 11.dp),
        Arrangement.spacedBy(14.dp),
        Alignment.CenterVertically,
    ) {
        val peso = if (elegido) 780 else 640
        Texto((numero + 1).toString(), tamano = 13, peso = peso, color = color)
        Texto(nombre, tamano = 13, peso = peso, color = color)
    }
}

@Composable
private fun EncabezadoPaso(paso: Int) {
    val titulos = listOf("Choose your language", "Choose how it looks", "Navigation", "Prepare the board", "Take the guided tour?")
    val notas = listOf(
        t("The interface, its reports and its guides are all translated."),
        "",
        "",
        t("Tools the other modules need. Anything already installed is marked.") + " " +
            t("Needs internet and your password. Every command is shown in the terminal."),
        t("A short walk through the modules, pointing at the real controls."),
    )
    Texto(t(titulos[paso]), tamano = 25, peso = 800)
    if (notas[paso].isNotEmpty()) {
        Texto(notas[paso], tamano = 14, color = ColoresActuales.current.apagado)
    }
    Spacer(Modifier.height(20.dp))
}

@Composable
private fun PiePaso(paso: Int, alVolver: () -> Unit, alSeguir: () -> Unit, alOmitir: (() -> Unit)?) {
    Row(Modifier.fillMaxWidth().padding(top = 12.dp), Arrangement.spacedBy(10.dp), Alignment.CenterVertically) {
        Texto("${paso + 1} / ${Pasos.size}", tamano = 13, peso = 680, color = ColoresActuales.current.sutil)
        Spacer(Modifier.weight(1f))
        if (alOmitir != null) {
            Boton(t("Skip setup"), alOmitir, clase = ClaseBoton.CONTORNO, alto = 40.dp)
        }
        if (paso > 0) {
            Boton(t("Back"), alVolver, alto = 40.dp, tamano = 14, peso = 680)
        }
        val ultimo = paso == Pasos.lastIndex
        Boton(t(if (ultimo) "Start the tour" else "Continue"), alSeguir, clase = ClaseBoton.PRINCIPAL, alto = 40.dp, tamano = 14, peso = 760)
    }
}

@Composable
private fun ContenidoPaso(aplicacion: Aplicacion, paso: Int, datos: JsonObject, ordenes: Ordenes) {
    if (datos.isEmpty()) {
        Texto(t("Loading"), tamano = 13, color = ColoresActuales.current.apagado)
        return
    }
    when (paso) {
        0 -> PasoIdioma(datos, ordenes)
        1 -> Desplazable { PasoAspecto(datos, ordenes) }
        2 -> Desplazable { PasoNavegacion(datos, ordenes) }
        3 -> Desplazable { PasoDependencias(aplicacion) }
        else -> Desplazable { PasoRecorrido(datos) }
    }
}

@Composable
private fun Desplazable(contenido: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), Arrangement.spacedBy(14.dp), content = contenido)
}

/** Una opción de la bienvenida: un botón que queda marcado. */
@Composable
private fun Ficha(texto: String, elegida: Boolean, modifier: Modifier = Modifier, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (elegida) paleta.acentoSuave else paleta.panelElevado
    val borde = if (elegida) paleta.acento else paleta.borde
    val color = if (elegida) paleta.acento else paleta.texto
    Box(modifier.height(36.dp).marco(fondo, borde, 4.dp).pulsable(alPulsar = alPulsar).padding(horizontal = 12.dp), Alignment.Center) {
        Texto(texto, tamano = 13, peso = if (elegida) 760 else 620, color = color)
    }
}

// -- 1: idioma ------------------------------------------------------------------------------------------

@Composable
private fun PasoIdioma(datos: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    val idiomas = datos.objetos("idiomas")
    val actual = datos.texto("idioma")
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(end = 12.dp), Arrangement.spacedBy(8.dp)) {
            val automatico = idiomas.firstOrNull { idioma -> idioma.texto("valor") == "auto" }
            if (automatico != null) {
                Ficha(automatico.texto("nombre"), actual == "auto", Modifier.fillMaxWidth()) {
                    ordenes.guardar("language", JsonPrimitive("auto"))
                }
            }
            val otros = idiomas.filter { idioma -> idioma.texto("valor") != "auto" }
            RejillaGpuCu(otros.size, 3, umbral = 520.dp, separacion = 8.dp) { indice, modificador ->
                val codigo = otros[indice].texto("valor")
                Ficha(otros[indice].texto("nombre"), actual == codigo, modificador) {
                    ordenes.guardar("language", JsonPrimitive(codigo))
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(
            Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.borde, 4.dp).padding(horizontal = 16.dp, vertical = 10.dp),
            Arrangement.spacedBy(8.dp),
            Alignment.CenterVertically,
        ) {
            Texto(t("Temperature unit").uppercase(), 12, Modifier.weight(1f), peso = 760, color = paleta.apagado)
            for ((valor, simbolo) in listOf("celsius" to "°C", "fahrenheit" to "°F")) {
                Ficha(simbolo, datos.texto("unidad") == valor, Modifier.width(64.dp)) {
                    ordenes.guardar("temperature_unit", JsonPrimitive(valor))
                }
            }
        }
    }
}

// -- 2: aspecto -----------------------------------------------------------------------------------------

@Composable
private fun PasoAspecto(datos: JsonObject, ordenes: Ordenes) {
    Bloque(datos.objeto("temas"), ordenes)
    for (clave in listOf("estilo", "acento", "densidad", "escala")) {
        Bloque(datos.objeto(clave), ordenes)
    }
    Texto(t("Terminal theme").uppercase(), tamano = 12, peso = 760, color = ColoresActuales.current.apagado)
    Bloque(datos.objeto("terminal"), ordenes)
}

// -- 3: navegación ----------------------------------------------------------------------------------------

@Composable
private fun PasoNavegacion(datos: JsonObject, ordenes: Ordenes) {
    val paleta = ColoresActuales.current
    Row(
        Modifier.fillMaxWidth().marco(paleta.panelAlterno, paleta.borde, 4.dp).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Texto(t("Gamepad navigation"), tamano = 13)
            Texto(t("Detect controllers automatically and show controller hints while active."), tamano = 14, color = paleta.apagado)
        }
        Interruptor(datos.logico("mando"), { nuevo -> ordenes.guardar("gamepad_navigation", JsonPrimitive(nuevo)) })
    }
    Texto(t("Sidebar"), 13, Modifier.padding(top = 8.dp), peso = 680)
    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        for (plegada in listOf(false, true)) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                MiniaturaBarra(plegada, datos.logico("barra") == plegada) {
                    ordenes.guardar("sidebar_collapsed", JsonPrimitive(plegada))
                }
                Texto(t(if (plegada) "Collapsed" else "Expanded"), tamano = 13, peso = 680)
            }
        }
    }
}

/** La ventana en pequeño, con la barra amplia o estrecha. */
@Composable
private fun MiniaturaBarra(plegada: Boolean, elegida: Boolean, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val borde = if (elegida) paleta.acento else paleta.bordeSuave
    Row(
        Modifier.size(170.dp, 232.dp).marco(paleta.ventana, borde, 8.dp).pulsable(alPulsar = alPulsar).padding(14.dp),
        Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.width(if (plegada) 12.dp else 38.dp).fillMaxHeight().padding(vertical = 8.dp), Arrangement.SpaceBetween) {
            for (numero in 0..6) {
                val color = if (numero == 1) paleta.acento else paleta.sutil
                Row(Modifier.height(10.dp), Arrangement.spacedBy(4.dp), Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).marco(color, color, 2.dp))
                    if (!plegada) {
                        Box(Modifier.size(22.dp, 3.dp).background(color))
                    }
                }
            }
        }
        Column(Modifier.weight(1f).fillMaxHeight().marco(paleta.sutil, paleta.sutil, 4.dp).padding(6.dp), Arrangement.spacedBy(14.dp)) {
            Box(Modifier.width(52.dp).height(4.dp).background(paleta.texto))
            Box(Modifier.width(52.dp).height(4.dp).background(paleta.texto))
        }
    }
}

// -- 4: dependencias ----------------------------------------------------------------------------------------

@Composable
private fun PasoDependencias(aplicacion: Aplicacion) {
    val paleta = ColoresActuales.current
    val datos = aplicacion.lectura("dashboard")
    val componentes = datos.objetos("components")
    var elegidos by remember { mutableStateOf(setOf("runtime")) }
    val libre = aplicacion.puedeControlar && aplicacion.trabajo.terminado
    val disponibles = componentes.filter { pieza -> pieza.logico("available") }.map { pieza -> pieza.texto("key") }

    fun marcar(clave: String) {
        elegidos = conDependencias(elegidos, clave)
    }

    fun todos() {
        elegidos = if (elegidos.containsAll(disponibles)) setOf("runtime") else elegidos + disponibles
    }

    fun instalar() {
        val preparacion = datos.objeto("preparation")
        val conflicto = "governor" in elegidos && preparacion.textos("conflicts").isNotEmpty()
        val parametros = mapOf(
            "components" to JsonArray(elegidos.sorted().map { clave -> JsonPrimitive(clave) }),
            "governor" to JsonPrimitive("auto"),
            "disable_conflicts" to JsonPrimitive(conflicto),
        )
        val titulo = t(if (conflicto) "Switch GPU governor safely" else "Prepare BC250 system")
        val mensaje = if (conflicto) preparacion.texto("message") else titulo
        aplicacion.preguntarYEjecutar("panel.prepare", titulo, mensaje, parametros, peligro = conflicto)
    }

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Texto(t("Select all"), 13, Modifier.pulsable(alPulsar = ::todos), peso = 640, color = paleta.apagado)
        Spacer(Modifier.weight(1f))
        Texto(t("{count} selected", "count" to elegidos.size.toString()), tamano = 13, color = paleta.apagado)
    }
    RejillaGpuCu(componentes.size + 1, 2, umbral = 520.dp, separacion = 8.dp) { indice, modificador ->
        if (indice < componentes.size) {
            val pieza = componentes[indice]
            FilaComponente(pieza, pieza.texto("key") in elegidos, modificador) { marcar(pieza.texto("key")) }
        } else {
            val texto = t("Install {count}", "count" to elegidos.size.toString())
            Boton(texto, ::instalar, modificador, clase = ClaseBoton.PRINCIPAL, activo = libre, alto = 38.dp, peso = 760)
        }
    }
    val trabajo = aplicacion.trabajo
    if (trabajo.id > 0) {
        TextoConsola(trabajo.texto, Modifier.fillMaxWidth().height(200.dp))
    }
}

/** El administrador de CU necesita UMR, y sin UMR no puede quedarse marcado. */
private fun conDependencias(elegidos: Set<String>, clave: String): Set<String> {
    if (clave == "runtime") {
        return elegidos
    }
    var nuevos = if (clave in elegidos) elegidos - clave else elegidos + clave
    if (clave == "cu_manager" && clave in nuevos) {
        nuevos = nuevos + "umr"
    }
    if (clave == "umr" && clave !in nuevos) {
        nuevos = nuevos - "cu_manager"
    }
    return nuevos
}

@Composable
private fun FilaComponente(pieza: JsonObject, elegida: Boolean, modifier: Modifier, alMarcar: () -> Unit) {
    val paleta = ColoresActuales.current
    val obligatoria = pieza.texto("key") == "runtime"
    val puede = pieza.logico("available") && !obligatoria
    val fondo = if (elegida) paleta.acentoSuave else paleta.panelElevado
    val borde = if (elegida) paleta.acentoBorde else paleta.bordeSuave
    Row(
        modifier.height(38.dp).marco(fondo, borde, 6.dp).pulsable(puede, alPulsar = alMarcar).padding(horizontal = 12.dp),
        Arrangement.spacedBy(10.dp),
        Alignment.CenterVertically,
    ) {
        CasillaChica(elegida, puede, alMarcar)
        val color = if (pieza.logico("available")) paleta.texto else paleta.textoInactivo
        Texto(pieza.texto("title"), 13, Modifier.weight(1f), color = color)
        if (obligatoria) {
            Texto(t("Required"), tamano = 10, color = paleta.sutil)
        } else if (pieza.logico("installed")) {
            Texto(t("Installed"), tamano = 10, color = paleta.verde)
        }
    }
}

// -- 5: recorrido --------------------------------------------------------------------------------------------

@Composable
private fun PasoRecorrido(datos: JsonObject) {
    val paleta = ColoresActuales.current
    val paradas = datos.textos("paradas")
    Texto(t("It stops at each module, says what it is for and what it changes on the board. You can leave it at any point, and start it again from Settings whenever you like."), tamano = 14)
    RejillaGpuCu(paradas.size, 2, umbral = 520.dp, separacion = 10.dp) { indice, modificador ->
        Box(modificador.marco(paleta.panelElevado, paleta.bordeSuave, 4.dp).padding(horizontal = 12.dp, vertical = 8.dp)) {
            Texto(paradas[indice], tamano = 13, peso = 620, color = paleta.apagado)
        }
    }
}
