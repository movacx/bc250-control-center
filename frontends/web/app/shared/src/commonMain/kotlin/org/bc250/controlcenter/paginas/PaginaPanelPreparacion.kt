package org.bc250.controlcenter.paginas

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.*
import org.jetbrains.compose.resources.painterResource
import org.bc250.controlcenter.componentes.*
import org.bc250.controlcenter.datos.*
import org.bc250.controlcenter.recursos.*
import org.bc250.controlcenter.tema.ColoresActuales
import org.bc250.controlcenter.tema.Medidas
import org.bc250.controlcenter.tema.MedidasPanelRendimiento as M

@Composable
internal fun PreparacionPanel(aplicacion: Aplicacion, datos: JsonObject, alDialogo: (String) -> Unit) {
    val paleta = ColoresActuales.current
    var pestaña by remember { mutableStateOf("components") }
    var seleccion by remember { mutableStateOf<Set<String>?>(null) }
    val componentes = datos.objetos("components")
    val seleccionados = seleccion ?: seleccionInicialPanel(componentes)
    val libre = aplicacion.trabajo.terminado && aplicacion.puedeControlar
    Column(Modifier.fillMaxWidth().marco(paleta.panel, paleta.borde, 7.dp).padding(start = 1.dp, top = 13.dp, end = 1.dp, bottom = 11.dp), Arrangement.spacedBy(0.dp)) {
        BoxWithConstraints(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 12.dp)) {
            if (maxWidth >= M.anchoMovil) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Texto(t("Prepare BC250 system"), tamano = 14, peso = 750)
                        Leyenda(t("Detected system: {distribution}", "distribution" to t(datos.texto("system", "Not detected"))))
                    }
                    EnlacesPanel(aplicacion, datos, alDialogo)
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Texto(t("Prepare BC250 system"), tamano = 14, peso = 750)
                    Leyenda(t("Detected system: {distribution}", "distribution" to t(datos.texto("system", "Not detected"))))
                    EnlacesPanel(aplicacion, datos, alDialogo)
                }
            }
        }
        LineaDivisoria()
        Row(Modifier.fillMaxWidth().height(42.dp).padding(horizontal = 12.dp, vertical = 4.dp), Arrangement.spacedBy(6.dp)) {
            PestanaPanel(t("Components"), pestaña == "components", Modifier.weight(1f)) { pestaña = "components" }
            PestanaPanel("Decky", pestaña == "decky", Modifier.weight(1f)) { pestaña = "decky" }
        }
        LineaDivisoria()
        Column(Modifier.fillMaxWidth().padding(start = 16.dp, top = 10.dp, end = 16.dp), Arrangement.spacedBy(10.dp)) {
        if (pestaña == "components") {
            fun marcar(clave: String) {
                seleccion = marcarComponentePanel(seleccionados, clave)
            }
            fun preparar() {
                prepararPanel(aplicacion, datos, seleccionados)
            }
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                val columnas = if (maxWidth >= M.anchoColumnas) 4 else if (maxWidth >= M.anchoMovil) 2 else 1
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (inicio in componentes.indices step columnas) {
                        Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                            for (columna in 0 until columnas) {
                                val componente = componentes.getOrNull(inicio + columna)
                                if (componente != null) {
                                    ComponentePanel(componente, componente.texto("key") in seleccionados,
                                        libre, Modifier.weight(1f), { marcar(componente.texto("key")) },
                                        { alDialogo("component:${componente.texto("key")}") })
                                } else if (columnas == 4 && columna == 3) {
                                    Boton(t("Prepare selected ({count})", "count" to seleccionados.size.toString()), ::preparar,
                                        Modifier.weight(1f), ClaseBoton.PRINCIPAL, libre && "runtime" in seleccionados)
                                } else Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                    if (columnas != 4) {
                        Boton(t("Prepare selected ({count})", "count" to seleccionados.size.toString()), ::preparar,
                            Modifier.fillMaxWidth(), ClaseBoton.PRINCIPAL, libre && "runtime" in seleccionados)
                    }
                }
            }
        } else {
            val quick = datos.objeto("quick_access")
            Texto(quick.texto("title"), tamano = 14, peso = 750)
            Leyenda(quick.texto("detail"))
            if (!quick.logico("supported")) Leyenda(t("Unavailable"))
            Row(Modifier.fillMaxWidth(), Arrangement.spacedBy(8.dp)) {
                Boton(quick.texto("label"), {
                    prepararDeckyPanel(aplicacion, quick)
                }, Modifier.weight(1f), activo = libre && quick.logico("supported") && quick.logico("decky_plugin_root_safe", true))
                Boton(t("Preview"), { alDialogo("decky") })
            }
        }
    }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ComponentePanel(datos: JsonObject, elegido: Boolean, libre: Boolean, modifier: Modifier,
    alMarcar: () -> Unit, alDetalle: () -> Unit) {
    val paleta = ColoresActuales.current
    val disponible = datos.logico("available")
    Row(modifier.heightIn(min = 34.dp).combinedClickable(
        enabled = disponible && libre && datos.texto("key") != "runtime",
        onClick = alMarcar, onLongClick = alDetalle).marco(paleta.panelAlterno, paleta.bordeSuave, 6.dp).padding(horizontal = 11.dp),
        Arrangement.spacedBy(8.dp), Alignment.CenterVertically) {
        Texto(datos.texto("title"), tamano = 13, peso = 650,
            color = if (disponible) paleta.texto else paleta.textoInactivo,
            modifier = Modifier.weight(1f))
        CasillaChica(elegido, disponible && libre && datos.texto("key") != "runtime", alMarcar)
    }
}

@Composable
private fun EnlacesPanel(aplicacion: Aplicacion, datos: JsonObject, alDialogo: (String) -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        for (enlace in datos.objetos("links").filter { enlace -> enlace.texto("key") != "Ko-fi" }) {
            val titulo = enlace.texto("key")
            val icono = when (titulo) {
                "Official repositories" -> Res.drawable.github
                "Discord" -> Res.drawable.discord
                else -> Res.drawable.telegram
            }
            BotonIcono(icono, {
                if (titulo == t("Official repositories") || titulo == "Official repositories") alDialogo("repositories")
                else aplicacion.abrirEnlace(enlace.texto("url"))
            }, lado = 36.dp, tamano = 20.dp)
        }
        BotonIcono(Res.drawable.support_headset, { aplicacion.irA("settings", "support") }, lado = 36.dp, tamano = 20.dp)
        BotonIcono(Res.drawable.note_heart, { alDialogo("note") }, lado = 36.dp, tamano = 20.dp)
        val kofi = datos.objetos("links").firstOrNull { enlace -> enlace.texto("key") == "Ko-fi" }
        if (kofi != null) {
            BotonIcono(Res.drawable.panel_kofi_cup, { aplicacion.abrirEnlace(kofi.texto("url")) }, lado = 36.dp, tamano = 20.dp)
        }
        if (datos.objeto("update").logico("available")) {
            Boton(t("New update available"), { alDialogo("update") }, alto = 30.dp, tamano = 11)
        }
    }
}

@Composable
internal fun DialogosPanel(aplicacion: Aplicacion, datos: JsonObject, dialogo: String, alCerrar: () -> Unit) {
    if (dialogo.isEmpty()) return
    Dialogo(alCerrar, ancho = if (dialogo == "decky") 1200.dp else 640.dp) {
        when {
            dialogo == "decky" -> {
                Texto(t("Decky Quick Access preview"), tamano = 17, peso = 800)
                Image(painterResource(Res.drawable.panel_decky_preview), t("Decky Quick Access preview image"),
                    Modifier.fillMaxWidth())
            }
            dialogo == "repositories" -> {
                Texto(t("Official repositories"), tamano = 17, peso = 800)
                for (repo in datos.objetos("repositories")) {
                    Boton(repo.texto("title"), { aplicacion.abrirEnlace(repo.texto("url")) }, Modifier.fillMaxWidth())
                }
            }
            dialogo == "note" -> {
                val nota = datos.objeto("note")
                NotaDelAutor(aplicacion, nota, alCerrar)
            }
            dialogo == "update" -> {
                val actualizacion = datos.objeto("update")
                Texto(t("New update available"), tamano = 17, peso = 800)
                Texto(actualizacion.texto("version"), tamano = 15, peso = 750)
                Leyenda(actualizacion.texto("detail"))
                Boton(t("See what's new"), { aplicacion.abrirEnlace(actualizacion.texto("url")) })
            }
            dialogo == "telemetry" -> {
                val telemetria = datos.objeto("telemetry")
                Texto(telemetria.texto("title"), tamano = 17, peso = 800)
                Leyenda(telemetria.texto("detail"))
                Boton(t("Firmware (BIOS)"), {
                    alCerrar()
                    aplicacion.irA("firmware")
                })
            }
            dialogo == "vrm" -> {
                Texto(t("Power delivery"), tamano = 17, peso = 800)
                Leyenda(t("These readings come from the board's voltage regulator (PMIC) over I2C, which needs the physical I2C modification: two wires between I2C_HEADER1 and TPMS1. With the modification in place, open Settings › Telemetry and install the BC250-Telemetry service under Power delivery (I2C mod). The readings appear here a few seconds after it starts."))
                Boton(t("Settings"), {
                    alCerrar()
                    aplicacion.irA("settings")
                })
                Boton(t("Firmware (BIOS)"), {
                    alCerrar()
                    aplicacion.irA("firmware")
                })
            }
            dialogo.startsWith("component:") -> {
                val clave = dialogo.removePrefix("component:")
                val componente = datos.objetos("components").firstOrNull { it.texto("key") == clave } ?: ObjetoVacio
                Texto(componente.texto("title"), tamano = 17, peso = 800)
                Leyenda(componente.texto("detail"))
                Leyenda(t(if (componente.logico("installed")) "Installed" else "Not installed"))
            }
        }
        Boton(t("Close"), alCerrar, Modifier.fillMaxWidth())
    }
}

internal fun seleccionInicialPanel(componentes: List<JsonObject>): Set<String> {
    val elegidos = mutableSetOf<String>()
    for (componente in componentes) {
        if (componente.logico("selected") && componente.logico("available")) {
            elegidos.add(componente.texto("key"))
        }
    }
    return elegidos
}

/** Una pestaña de la preparación: la abierta lleva el fondo suave del acento. */
@Composable
internal fun PestanaPanel(texto: String, abierta: Boolean, modifier: Modifier, alPulsar: () -> Unit) {
    val paleta = ColoresActuales.current
    val fondo = if (abierta) paleta.acentoSuave else paleta.panel
    val color = if (abierta) paleta.acento else paleta.apagado
    Box(
        modifier = modifier
            .height(34.dp)
            .background(fondo, RoundedCornerShape(4.dp))
            .pulsable(alPulsar = alPulsar),
        contentAlignment = Alignment.Center,
    ) {
        Texto(texto, tamano = 13, peso = 700, color = color)
    }
}

internal fun prepararPanel(aplicacion: Aplicacion, datos: JsonObject, seleccionados: Set<String>) {
    val componentes = datos.objetos("components")
    val preparacion = datos.objeto("preparation")
    val conflicto = "governor" in seleccionados && preparacion.textos("conflicts").isNotEmpty()
    val parametros = mapOf("components" to JsonArray(seleccionados.sorted().map(::JsonPrimitive)),
        "governor" to JsonPrimitive("auto"), "disable_conflicts" to JsonPrimitive(conflicto))
    val titulos = mutableListOf<String>()
    for (componente in componentes) {
        if (componente.texto("key") in seleccionados) titulos.add(componente.texto("title"))
    }
    val titulo = t(if (conflicto) "Switch GPU governor safely" else "Prepare BC250 system")
    val mensaje = titulos.joinToString("\n") + if (conflicto) "\n\n" + preparacion.texto("message") else ""
    aplicacion.preguntarYEjecutar("panel.prepare", titulo, mensaje, parametros, peligro = conflicto)
}

internal fun marcarComponentePanel(seleccionados: Set<String>, clave: String): Set<String> {
    var nuevas = if (clave in seleccionados) seleccionados - clave else seleccionados + clave
    if (clave == "cu_manager" && clave in nuevas) nuevas = nuevas + "umr"
    if (clave == "umr" && clave !in nuevas) nuevas = nuevas - "cu_manager"
    return nuevas
}

internal fun prepararDeckyPanel(aplicacion: Aplicacion, quick: JsonObject) {
    aplicacion.preguntarYEjecutar("panel.decky", quick.texto("label"), quick.texto("message"), peligro = true)
}
